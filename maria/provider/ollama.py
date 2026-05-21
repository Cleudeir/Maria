import os
import json
import requests
import threading
from typing import List, Dict, Any, Optional, Callable
from dotenv import load_dotenv

from maria.provider.base import LLMProvider, format_messages_to_prompt as shared_format
from maria.provider.opencode import strip_thinking_process


class LoopDetectedError(Exception):
    pass


_thread_local = threading.local()

load_dotenv()


def _parse_metrics(event: Dict[str, Any]) -> Dict[str, Any]:
    prompt_tokens = event.get("prompt_eval_count", 0)
    completion_tokens = event.get("eval_count", 0)
    total_tokens = prompt_tokens + completion_tokens

    eval_duration_ns = event.get("eval_duration", 0)
    eval_duration_sec = eval_duration_ns / 1e9 if eval_duration_ns else 0.0
    tokens_per_second = (
        round(completion_tokens / eval_duration_sec, 2)
        if eval_duration_sec > 0
        else 0.0
    )

    prompt_eval_duration_ns = event.get("prompt_eval_duration", 0)
    prompt_eval_duration_sec = (
        prompt_eval_duration_ns / 1e9 if prompt_eval_duration_ns else 0.0
    )
    prompt_tokens_per_second = (
        round(prompt_tokens / prompt_eval_duration_sec, 2)
        if prompt_eval_duration_sec > 0
        else 0.0
    )

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "tokens_per_second": tokens_per_second,
        "prompt_tokens_per_second": prompt_tokens_per_second,
    }


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:4b",
        model_think: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_think = model_think
        self._temperature = 0.9
        self._stop = None
        self.token = os.environ.get("OLLAMA_TOKEN", "banana")
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def last_usage(self) -> Dict[str, Any]:
        return getattr(_thread_local, "last_usage", {})

    def _set_last_usage(self, usage: Dict[str, Any]):
        _thread_local.last_usage = usage

    def format_messages_to_prompt(
        self, messages: List[Dict[str, str]]
    ) -> tuple[Optional[str], str]:
        return shared_format(messages)

    _MAX_LOOP_RETRIES = 3

    def generate(
        self,
        system_text: Optional[str],
        user_text: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        self._set_last_usage({})

        url = f"{self.base_url}/api/generate"
        for attempt in range(self._MAX_LOOP_RETRIES):
            # Fixed temperatures per attempt: 0.5 → 0.7 → 0.9
            retry_temperature = [0.5, 0.7, 0.9][attempt]

            payload = {
                "model": self.model,
                "prompt": user_text,
                "stream": True,
                "think": self.model_think,
                "options": {
                    "temperature": retry_temperature,
                    "num_ctx": 8192,
                },
            }
            if system_text:
                payload["system"] = system_text
            if self._stop:
                payload["options"]["stop"] = self._stop

            if attempt > 0:
                print(
                    f"[Ollama] Retrying step after loop detection "
                    f"(attempt {attempt + 1}/{self._MAX_LOOP_RETRIES}, temp={retry_temperature})",
                    flush=True,
                )

            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=3600,
                    stream=True,
                )
                response.raise_for_status()

                thinking_output = ""
                response_output = ""
                last_event = None

                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    try:
                        event = json.loads(raw_line)
                        last_event = event

                        if event.get("thinking"):
                            thinking_output += event["thinking"]

                            print(f"[Ollama] think: {len(thinking_output)} characters")
                            with open("maria_thinking.log", "a") as f:
                                f.write(event["thinking"])

                        if isinstance(event.get("response"), str):
                            response_output += event["response"]
                            if progress_callback:
                                progress_callback(
                                    strip_thinking_process(response_output)
                                )

                        if event.get("done") is True:
                            break

                    except ValueError:
                        continue

                if last_event:
                    self._set_last_usage(_parse_metrics(last_event))

                return strip_thinking_process(response_output)

            except requests.exceptions.ConnectionError:
                raise RuntimeError("Ollama not in use. Make sure ollama is running.")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Ollama request failed: {e}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        self._temperature = temperature
        self._stop = stop
        return super().chat(messages, temperature, stop, stream_callback)
