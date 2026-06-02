import os
import logging
from typing import List, Dict, Any, Optional, Callable

from maria.provider import create_provider, LLMProvider
from maria.compact_context import compact_messages, total_tokens

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:4b",
        model_think: bool = False,
        provider_type: str = "llamacpp",
    ):
        if provider is not None:
            self.provider = provider
        else:
            self.provider = create_provider(
                provider_type,
                base_url=base_url,
                model=model,
                model_think=model_think,
            )

    @property
    def last_usage(self) -> Dict[str, Any]:
        return self.provider.last_usage

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
        stream: bool = True,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        max_ctx = getattr(self.provider, 'max_context_window', 8192)
        if total_tokens(messages) > int(max_ctx * 0.5):
            compacted = compact_messages(
                messages,
                token_budget=int(max_ctx * 0.5),
                max_context_tokens=max_ctx,
            )
            if compacted is not messages:
                logger.info("llm: compacted %d messages -> %d", len(messages), len(compacted))
                messages = compacted
        return self.provider.chat(
            messages,
            temperature=temperature,
            stop=stop,
            stream_callback=stream_callback,
        )

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        stream: bool = True,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        return self.provider.generate(
            system_text=system,
            user_text=prompt,
            progress_callback=stream_callback,
        )
