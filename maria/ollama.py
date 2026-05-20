import os
import json
import requests
import threading
import re
from typing import List, Dict, Any, Optional, Tuple

_lock = threading.Lock()
_thread_local = threading.local()

# Fixed/Global parameters (can be mutated by client classes or env)
BASE_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:2b")
TEMPERATURE = 0.9
STOP = None
MODEL_THINK = True


def strip_thinking_process(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # If the response contains </think> or </thought>, return only the text after the last occurrence
    if "</think>" in text:
        parts = text.split("</think>")
        text = parts[-1]
    elif "</thought>" in text:
        parts = text.split("</thought>")
        text = parts[-1]

    # Strip any open <think> or <thought> tag at the start if it wasn't closed or is dangling
    text = re.sub(r"^<(think|thought)>.*$", "", text, flags=re.MULTILINE)
    return text.strip()


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


def get_last_usage() -> Dict[str, Any]:
    return getattr(_thread_local, "last_usage", {})


def set_last_usage(usage: Dict[str, Any]):
    _thread_local.last_usage = usage


def getGenerate(system_text: Optional[str], user_text: str) -> str:
    """
    Sends a generation request to Ollama using streaming, and returns the complete generated response.
    """
    set_last_usage({})

    # Resolve parameters from module globals
    base_url = BASE_URL
    model = MODEL
    temperature = TEMPERATURE
    stop = STOP
    model_think = MODEL_THINK

    url = f"{base_url.rstrip('/')}/api/generate"

    payload = {
        "model": model,
        "prompt": user_text,
        "stream": True,
        "think": model_think,
        "options": {
            "temperature": temperature,
            "num_ctx": 8192,
        },
    }
    if system_text:
        payload["system"] = system_text
    if stop:
        payload["options"]["stop"] = stop

    token = os.environ.get("OLLAMA_TOKEN", "banana")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    thread_id = threading.get_ident()
    print(f"[Ollama Queue] Thread {thread_id} waiting for lock...")
    with _lock:
        print(f"[Ollama Queue] Thread {thread_id} acquired lock. Sending request...")
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
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
                    if isinstance(event.get("thinking"), str):
                        print(f"[Ollama Queue think] {len(thinking_output) } chars")
                        thinking_output += event["thinking"]
                    if isinstance(event.get("response"), str):
                        print(f"[Ollama Queue response] {len(response_output) } chars")
                        response_output += event["response"]
                    if event.get("done") is True:
                        break
                except ValueError:
                    continue

            if last_event:
                set_last_usage(_parse_metrics(last_event))
            print(
                f"[Ollama Queue] Thread {thread_id} received response. Releasing lock..."
            )
            print(
                f"[Ollama Queue] Thread {thread_id} output: {strip_thinking_process(response_output)}"
            )
            return strip_thinking_process(response_output)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama request failed: {e}")
        finally:
            print(f"[Ollama Queue] Thread {thread_id} released lock.")


def format_messages_to_prompt(
    messages: List[Dict[str, str]],
) -> Tuple[Optional[str], str]:
    system_text = None
    user_text_parts = []

    # Check if there is only one non-system message
    non_system_messages = [m for m in messages if m.get("role") != "system"]
    if len(non_system_messages) == 1:
        for msg in messages:
            if msg.get("role") == "system":
                system_text = msg.get("content")
        return system_text, non_system_messages[0].get("content", "")

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            system_text = content
        elif role == "user":
            user_text_parts.append(f"User: {content}")
        elif role == "assistant":
            user_text_parts.append(f"Assistant: {content}")
    user_text = "\n\n".join(user_text_parts)
    return system_text, user_text
