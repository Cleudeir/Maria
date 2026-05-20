import os
import re
from typing import List, Dict, Any, Optional, Callable
from maria.ollama import (
    getGenerate,
    get_last_usage,
    format_messages_to_prompt,
    strip_thinking_process,
)


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:4b",
        model_think: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_think = model_think
        self.token = os.environ.get("OLLAMA_TOKEN", "banana")
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

        # Synchronize module globals in maria.ollama
        import maria.ollama

        maria.ollama.BASE_URL = self.base_url
        maria.ollama.MODEL = self.model
        maria.ollama.MODEL_THINK = self.model_think

    @property
    def last_usage(self) -> Dict[str, Any]:
        return get_last_usage()

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
        stream: bool = True,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        system_text, user_text = format_messages_to_prompt(messages)

        import maria.ollama

        maria.ollama.TEMPERATURE = temperature
        maria.ollama.STOP = stop

        return getGenerate(system_text, user_text, progress_callback=stream_callback)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        stream: bool = True,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        import maria.ollama

        maria.ollama.TEMPERATURE = temperature

        return getGenerate(system, prompt, progress_callback=stream_callback)
