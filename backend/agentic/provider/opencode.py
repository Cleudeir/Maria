import json
import os
import threading
from typing import List, Dict, Any, Optional, Callable

import requests

from agentic.provider.base import (
    LLMProvider,
    format_messages_to_prompt as shared_format,
    strip_thinking_process,
    extract_reasoning,
    ContextExceededError,
    RetryableError,
)


_thread_local = threading.local()

OPENCODE_URL = "https://opencode.ai/zen/go/v1/chat/completions"
OPENCODE_DEFAULT_MODEL = "deepseek-v4-flash"
OPENCODE_DEFAULT_MAX_CONTEXT = 128000


class OpenCodeProvider(LLMProvider):
    """OpenCode Zen chat-completions provider.

    API reference: https://opencode.ai/zen/go/v1/chat/completions
    Auth: Bearer token from env OPENCODE_API_KEY (or `api_key` kwarg).
    Uses OpenAI-compatible SSE streaming. DeepSeek-style models on this
    endpoint return a `reasoning_content` field on each delta alongside
    the regular `content`.
    """

    def __init__(
        self,
        base_url: str = OPENCODE_URL,
        model: str = OPENCODE_DEFAULT_MODEL,
        model_think: bool = False,
        api_key: Optional[str] = None,
        max_context_window: Optional[int] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_think = model_think
        self._temperature = 0.2
        self._stop: Optional[List[str]] = None
        self._max_context_window = max_context_window or OPENCODE_DEFAULT_MAX_CONTEXT

        self.api_key = (api_key or os.environ.get("OPENCODE_API_KEY", "")).strip()
        if not self.api_key:
            raise RuntimeError(
                "OpenCodeProvider requires OPENCODE_API_KEY (set in env or pass api_key=...)"
            )
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def max_context_window(self) -> int:
        return self._max_context_window

    @property
    def last_usage(self) -> Dict[str, Any]:
        return getattr(_thread_local, "last_usage", {})

    def _set_last_usage(self, usage: Dict[str, Any]) -> None:
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

        messages: List[Dict[str, str]] = []
        if system_text:
            messages.append({"role": "system", "content": system_text})
        messages.append({"role": "user", "content": user_text})

        total_prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        print(
            f"[opencode] Generating... model={self.model} prompt_chars={total_prompt_chars} messages={len(messages)}",
            flush=True,
        )

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": self._temperature,
        }
        if self._stop:
            payload["stop"] = self._stop

        response_output = ""
        reasoning_output = ""
        last_usage: Dict[str, Any] = {}
        finish_reason: Optional[str] = None
        error_msg: Optional[str] = None

        try:
            response = requests.post(
                self.base_url,
                json=payload,
                headers=self.headers,
                timeout=3600,
                stream=True,
            )
            response.raise_for_status()

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                else:
                    data_str = line
                if data_str == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                except ValueError:
                    continue

                choice = event.get("choices", [{}])[0] or {}
                delta = choice.get("delta") or {}
                content = delta.get("content")
                reasoning = delta.get("reasoning_content")

                if isinstance(content, str) and content:
                    response_output += content
                if isinstance(reasoning, str) and reasoning:
                    reasoning_output += reasoning

                if progress_callback is not None:
                    if self.model_think:
                        combined = (reasoning_output + response_output).strip()
                        progress_callback(combined)
                    else:
                        progress_callback(strip_thinking_process(response_output))

                if choice.get("finish_reason"):
                    finish_reason = choice.get("finish_reason")

                usage = event.get("usage")
                if isinstance(usage, dict) and usage:
                    last_usage = usage

            if not response_output and not reasoning_output:
                try:
                    body = response.text[:2000]
                    if body:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict) and "error" in parsed:
                            err = parsed["error"]
                            error_msg = (
                                err.get("message", str(err))
                                if isinstance(err, dict)
                                else str(err)
                            )
                except Exception:
                    pass
                if error_msg:
                    print(f"[opencode] ERROR: {error_msg}", flush=True)
                    lower = error_msg.lower()
                    if "context" in lower and ("exceed" in lower or "limit" in lower):
                        raise ContextExceededError(f"opencode error: {error_msg}")
                    raise RetryableError(f"opencode error: {error_msg}")

            if last_usage:
                usage_data = {
                    "prompt_tokens": int(last_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(last_usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(last_usage.get("total_tokens", 0) or 0),
                }
                self._set_last_usage(usage_data)
            else:
                self._set_last_usage({})

            if finish_reason == "length":
                print(
                    f"[opencode] WARNING: Generation truncated (got {len(response_output)} chars)",
                    flush=True,
                )

            if self.model_think:
                full_output = (
                    f"<think>{reasoning_output}</think>\n{response_output}".strip()
                    if reasoning_output
                    else response_output
                )
            else:
                full_output = strip_thinking_process(response_output)

            print(
                f"[opencode] Done: chars={len(full_output)}, reasoning_chars={len(reasoning_output)}, "
                f"finish_reason={finish_reason}, usage={self.last_usage}",
                flush=True,
            )

            return full_output

        except requests.exceptions.RequestException as e:
            status_code = None
            body_text = ""
            if getattr(e, "response", None) is not None:
                status_code = e.response.status_code
                try:
                    body_text = e.response.text[:500]
                except Exception:
                    pass
            full_msg = f"opencode request failed: {body_text or str(e)}"
            print(f"[opencode] ERROR: {full_msg}", flush=True)
            lower = body_text.lower()
            if status_code in (400,) and ("context" in lower and ("exceed" in lower or "limit" in lower)):
                raise ContextExceededError(full_msg)
            if status_code in (401, 403):
                raise RuntimeError(f"opencode auth error: {full_msg}")
            if status_code in (429, 503) or isinstance(e, requests.exceptions.Timeout):
                raise RetryableError(full_msg)
            raise RuntimeError(full_msg)

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
