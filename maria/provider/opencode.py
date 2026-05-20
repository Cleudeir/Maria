import os
import json
import requests
import threading
from typing import List, Dict, Any, Optional, Callable

from maria.provider.base import LLMProvider, format_messages_to_prompt as shared_format


_thread_local = threading.local()

OPENCODE_API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
OPENCODE_MODEL = "deepseek-v4-flash"


def strip_thinking_process(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if "</think>" in text:
        parts = text.split("</think>")
        text = parts[-1]
    elif "</thought>" in text:
        parts = text.split("</thought>")
        text = parts[-1]
    return text.strip()


class OpenCodeProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = OPENCODE_API_URL,
        model: str = OPENCODE_MODEL,
        model_think: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_think = model_think
        self._temperature = 0.9
        self._stop = None
        self.api_key = os.environ.get("OPENCODE_API_KEY", "")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def last_usage(self) -> Dict[str, Any]:
        return getattr(_thread_local, "last_usage", {})

    def _set_last_usage(self, usage: Dict[str, Any]):
        _thread_local.last_usage = usage

    def format_messages_to_prompt(
        self, messages: List[Dict[str, str]]
    ) -> tuple[Optional[str], str]:
        return shared_format(messages)

    def generate(
        self,
        system_text: Optional[str],
        user_text: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        self._set_last_usage({})

        messages = []
        if system_text:
            messages.append({"role": "system", "content": system_text})
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": self._temperature,
        }

        try:
            response = requests.post(
                self.base_url,
                json=payload,
                headers=self.headers,
                timeout=3600,
                stream=True,
            )
            response.raise_for_status()

            response_output = ""
            last_usage = {}

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                data_str = None

                if line.startswith("data: "):
                    data_str = line[6:]
                else:
                    data_str = line

                if data_str == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except ValueError:
                    continue

                if "error" in event:
                    error_msg = event["error"].get("message", str(event["error"]))
                    raise RuntimeError(f"OpenCode API error: {error_msg}")

                choice = event.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content") or event.get("content") or choice.get("text")

                if isinstance(content, str):
                    response_output += content
                    if progress_callback:
                        progress_callback(strip_thinking_process(response_output))

                usage = event.get("usage")
                if usage:
                    last_usage = usage

            if not response_output:
                try:
                    body = response.text[:1000]
                    if body:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict) and "error" in parsed:
                            err_msg = parsed["error"].get("message", str(parsed["error"]))
                            raise RuntimeError(f"OpenCode API error: {err_msg}")
                except Exception:
                    pass

            if last_usage:
                self._set_last_usage({
                    "prompt_tokens": last_usage.get("prompt_tokens", 0),
                    "completion_tokens": last_usage.get("completion_tokens", 0),
                    "total_tokens": last_usage.get("total_tokens", 0),
                })

            return strip_thinking_process(response_output)

        except requests.exceptions.RequestException as e:
            error_text = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    body = e.response.text[:500]
                    if body:
                        error_text = f": {body}"
                except Exception:
                    pass
            raise RuntimeError(f"OpenCode request failed{error_text}")

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
