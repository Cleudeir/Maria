import json
import os
import time
import requests
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from maria.provider.base import LLMProvider, format_messages_to_prompt as shared_format


_thread_local = threading.local()

LLAMACPP_URL = "https://api.apps.tec.br/llamacpp/v1/chat/completions"
LLAMACPP_MODEL = "Qwen3.5-4B-Q4_K_M.gguf"
LLAMACPP_API_KEY = os.environ.get("LLAMACPP_API_KEY", "")
GENERATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "generations")
GENERATIONS_LIMIT = 50


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


def _ensure_generations_dir():
    os.makedirs(GENERATIONS_DIR, exist_ok=True)


def _cleanup_generations():
    try:
        files = sorted(
            [f for f in os.listdir(GENERATIONS_DIR) if f.startswith("gen_") and f.endswith(".json")],
            key=lambda f: os.path.getmtime(os.path.join(GENERATIONS_DIR, f)),
        )
        while len(files) > GENERATIONS_LIMIT:
            oldest = files.pop(0)
            os.remove(os.path.join(GENERATIONS_DIR, oldest))
    except Exception as e:
        print(f"[llamacpp] Failed to cleanup generations: {e}", flush=True)


def _save_generation_log(system_text, messages, response_output, usage_data, finish_reason, error=None, reasoning=None):
    _ensure_generations_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "model": LLAMACPP_MODEL,
    }

    if system_text:
        log_entry["system_prompt_length"] = len(system_text)
        log_entry["system_prompt_preview"] = system_text[:200]

    log_entry["messages"] = []
    for m in messages:
        log_entry["messages"].append({
            "role": m.get("role"),
            "content_length": len(str(m.get("content", ""))),
            "content_preview": str(m.get("content", ""))[:200],
        })

    log_entry["response_length"] = len(response_output)
    log_entry["response_preview"] = response_output[:500]
    if reasoning:
        log_entry["reasoning"] = reasoning
    log_entry["finish_reason"] = finish_reason
    log_entry["usage"] = usage_data
    log_entry["error"] = error

    filename = f"gen_{timestamp}.json"
    filepath = os.path.join(GENERATIONS_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)
        _cleanup_generations()
    except Exception as e:
        print(f"[llamacpp] Failed to save generation log: {e}", flush=True)


class LlamaCppProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = LLAMACPP_URL,
        model: str = LLAMACPP_MODEL,
        model_think: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_think = model_think
        self._temperature = 0.9
        self._stop = None
        api_key = LLAMACPP_API_KEY
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    @property
    def name(self) -> str:
        return "llamacpp"

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

        total_prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        print(f"[llamacpp] Generating... prompt_chars={total_prompt_chars}, messages={len(messages)}", flush=True)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": self._temperature,
        }

        finish_reason = None
        response_output = ""
        last_usage = {}
        last_timings = None

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

                choice = event.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content") or event.get("content") or choice.get("text")

                if isinstance(content, str):
                    response_output += content
                    if progress_callback:
                        progress_callback(strip_thinking_process(response_output))

                if choice.get("finish_reason"):
                    finish_reason = choice.get("finish_reason")

                usage = event.get("usage")
                if usage:
                    last_usage = usage

                timings = event.get("timings")
                if timings:
                    last_timings = timings

            if not response_output:
                try:
                    body = response.text[:1000]
                    if body:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict) and "error" in parsed:
                            err_msg = parsed["error"].get("message", str(parsed["error"]))
                            _save_generation_log(system_text, messages, "", {}, finish_reason, error=err_msg)
                            raise RuntimeError(f"llamacpp error: {err_msg}")
                except Exception:
                    pass

            if last_usage:
                usage_data = {
                    "prompt_tokens": last_usage.get("prompt_tokens", 0),
                    "completion_tokens": last_usage.get("completion_tokens", 0),
                    "total_tokens": last_usage.get("total_tokens", 0),
                }
                self._set_last_usage(usage_data)
            elif last_timings:
                prompt_n = last_timings.get("prompt_n", 0)
                predicted_n = last_timings.get("predicted_n", 0)
                usage_data = {
                    "prompt_tokens": prompt_n,
                    "completion_tokens": predicted_n,
                    "total_tokens": prompt_n + predicted_n,
                }
                self._set_last_usage(usage_data)
            else:
                usage_data = {}

            if finish_reason == "length":
                print(f"[llamacpp] WARNING: Generation truncated (got {len(response_output)} chars)", flush=True)

            print(f"[llamacpp] Done: chars={len(response_output)}, finish_reason={finish_reason}, usage={self.last_usage}", flush=True)

            reasoning = extract_reasoning(response_output)
            _save_generation_log(system_text, messages, response_output, usage_data, finish_reason, reasoning=reasoning)

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
            full_msg = f"llamacpp request failed{error_text}"
            print(f"[llamacpp] ERROR: {full_msg}", flush=True)
            _save_generation_log(system_text, messages, response_output, {}, finish_reason, error=full_msg)
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
