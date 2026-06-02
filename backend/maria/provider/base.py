from abc import ABC, abstractmethod
import logging
from typing import List, Dict, Any, Optional, Callable

from maria.compact_context import compact_messages, total_tokens

logger = logging.getLogger(__name__)


class LoopDetectedError(Exception):
    pass


class ContextExceededError(Exception):
    pass


class RetryableError(Exception):
    pass


def strip_thinking_process(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if "</think>" in text:
        parts = text.split("</think>")
        text = parts[-1]
    return text.strip()


def extract_reasoning(text: str) -> Optional[str]:
    if not isinstance(text, str) or "<think>" not in text or "</think>" not in text:
        return None
    start = text.find("<think>") + len("<think>")
    end = text.find("</think>")
    if start >= end:
        return None
    return text[start:end].strip()


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return str(content)


def format_messages_to_prompt(
    messages: List[Dict[str, str]],
) -> tuple[Optional[str], str]:
    system_text = None
    user_text_parts = []

    non_system_messages = [m for m in messages if m.get("role") != "system"]
    if len(non_system_messages) == 1:
        for msg in messages:
            if msg.get("role") == "system":
                system_text = extract_text(msg.get("content", ""))
        return system_text, extract_text(non_system_messages[0].get("content", ""))

    for msg in messages:
        role = msg.get("role")
        content = extract_text(msg.get("content", ""))
        if role == "system":
            system_text = content
        elif role == "user":
            user_text_parts.append(f"User: {content}")
        elif role == "assistant":
            user_text_parts.append(f"Assistant: {content}")
    user_text = "\n\n".join(user_text_parts)
    return system_text, user_text


class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def last_usage(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def generate(
        self,
        system_text: Optional[str],
        user_text: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        ...

    @property
    def max_context_window(self) -> int:
        return 32768

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        if total_tokens(messages) > int(self.max_context_window * 0.5):
            compacted = compact_messages(
                messages,
                token_budget=int(self.max_context_window * 0.5),
                max_context_tokens=self.max_context_window,
            )
            if compacted is not messages:
                logger.info("provider: compacted %d messages -> %d", len(messages), len(compacted))
                messages = compacted
        system_text, user_text = self._format_messages(messages)
        return self.generate(system_text, user_text, progress_callback=stream_callback)

    def format_messages_to_prompt(
        self, messages: List[Dict[str, str]]
    ) -> tuple[Optional[str], str]:
        return format_messages_to_prompt(messages)

    def _format_messages(self, messages: List[Dict[str, str]]) -> tuple[Optional[str], str]:
        return self.format_messages_to_prompt(messages)
