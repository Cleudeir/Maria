import os
from typing import List, Dict, Any, Optional, Callable

from maria.provider import create_provider, LLMProvider
from maria.provider.opencode import strip_thinking_process


class LLMClient:
    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:4b",
        model_think: bool = False,
        provider_type: str = "ollama",
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
