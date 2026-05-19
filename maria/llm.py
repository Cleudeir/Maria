import os
import json
import requests
import threading
from typing import List, Dict, Any, Optional


class OllamaClient:
    # Class-level lock to serialize all Ollama requests (acting as a FIFO-like execution queue)
    _lock = threading.Lock()

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "qwen3.5:4b"
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.token = os.environ.get("OLLAMA_TOKEN", "banana")
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _find_usage(self, data: Any) -> Optional[Dict[str, int]]:
        if isinstance(data, dict):
            keys = ["prompt_tokens", "completion_tokens", "total_tokens"]
            if any(k in data for k in keys):
                return {
                    k: data[k] for k in keys if isinstance(data.get(k), int)
                } or None
            for value in data.values():
                found = self._find_usage(value)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = self._find_usage(item)
                if found:
                    return found
        return None

    @staticmethod
    def is_llm_stream_chunk(data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        message = data.get("message")
        return isinstance(message, dict) and message.get("role") == "assistant"

    def _iter_stream_lines(self, response: requests.Response):
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            try:
                yield json.loads(raw_line)
            except ValueError:
                continue

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        stop: Optional[List[str]] = None,
        stream: bool = True,
    ) -> str:
        """
        Sends a chat request to Ollama, optionally streaming the assistant response.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
            },
        }
        print(f"[Ollama Queue] Sending request to {url} with model {self.model}")
        print(f"Chat Message: {len(messages)} caractéres")

        if stop:
            payload["options"]["stop"] = stop

        thread_id = threading.get_ident()
        print(f"[Ollama Queue] Thread {thread_id} waiting for lock...")
        with self._lock:
            print(
                f"[Ollama Queue] Thread {thread_id} acquired lock. Sending request..."
            )
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=3600,
                    stream=stream,
                )
                response.raise_for_status()
                if stream:
                    output = ""
                    usage = None
                    for event in self._iter_stream_lines(response):
                        if self.is_llm_stream_chunk(event):
                            message = event.get("message", {})
                            if isinstance(message.get("thinking"), str):
                                output += message["thinking"]
                            elif isinstance(message.get("content"), str):
                                output += message["content"]
                        usage = self._find_usage(event) or usage
                        if event.get("done") is True:
                            break
                    self.last_usage = usage
                    return output
                data = response.json()
                self.last_usage = self._find_usage(data)
                return data.get("message", {}).get("content", "")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Ollama request failed: {e}")
            finally:
                print(f"[Ollama Queue] Thread {thread_id} released lock.")

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        stream: bool = True,
    ) -> str:
        """
        Sends a raw generation request to Ollama.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
            },
        }
        if system:
            payload["system"] = system

        thread_id = threading.get_ident()
        print(f"[Ollama Queue] Thread {thread_id} waiting for lock...")
        with self._lock:
            print(
                f"[Ollama Queue] Thread {thread_id} acquired lock. Sending request..."
            )
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=3600,
                    stream=stream,
                )
                response.raise_for_status()
                if stream:
                    output = ""
                    usage = None
                    for event in self._iter_stream_lines(response):
                        usage = self._find_usage(event) or usage
                        if isinstance(event.get("response"), str):
                            output += event["response"]
                        if event.get("done") is True:
                            break
                    self.last_usage = usage
                    return output
                data = response.json()
                self.last_usage = self._find_usage(data)
                return data.get("response", "")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Ollama request failed: {e}")
            finally:
                print(f"[Ollama Queue] Thread {thread_id} released lock.")
