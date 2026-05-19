import os
import requests
import threading
from typing import List, Dict, Any, Optional

class OllamaClient:
    # Class-level lock to serialize all Ollama requests (acting as a FIFO-like execution queue)
    _lock = threading.Lock()

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3.5:4b"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.token = os.environ.get("OLLAMA_TOKEN", "banana")
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2, stop: Optional[List[str]] = None) -> str:
        """
        Sends a chat request to Ollama.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192
            }
        }
        print(f"[Ollama Queue] Sending request to {url} with model {self.model}")
        print(f"Chat Message: {len(messages)} caractéres")

        if stop:
            payload["options"]["stop"] = stop

        thread_id = threading.get_ident()
        print(f"[Ollama Queue] Thread {thread_id} waiting for lock...")
        with self._lock:
            print(f"[Ollama Queue] Thread {thread_id} acquired lock. Sending request...")
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=3600)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Ollama request failed: {e}")
            finally:
                print(f"[Ollama Queue] Thread {thread_id} released lock.")

    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.2) -> str:
        """
        Sends a raw generation request to Ollama.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192
            }
        }
        if system:
            payload["system"] = system

        thread_id = threading.get_ident()
        print(f"[Ollama Queue] Thread {thread_id} waiting for lock...")
        with self._lock:
            print(f"[Ollama Queue] Thread {thread_id} acquired lock. Sending request...")
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=3600)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Ollama request failed: {e}")
            finally:
                print(f"[Ollama Queue] Thread {thread_id} released lock.")

