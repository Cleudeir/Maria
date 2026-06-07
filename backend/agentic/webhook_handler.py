import json
import time
import threading
from typing import Optional


_pending_asks = {}
_lock = threading.Lock()


def register_pending_ask(ask_id: str, task_id: str, ask_type: str, options: list, context: dict = None):
    with _lock:
        _pending_asks[ask_id] = {
            "task_id": task_id,
            "ask_type": ask_type,
            "options": options,
            "context": context or {},
            "created_at": time.time(),
        }


def get_pending_ask(ask_id: str) -> Optional[dict]:
    with _lock:
        return _pending_asks.get(ask_id)


def resolve_pending_ask(ask_id: str) -> Optional[dict]:
    with _lock:
        return _pending_asks.pop(ask_id, None)


def interpret_response(option_index: int, options: list) -> str:
    if 0 <= option_index < len(options):
        return options[option_index]
    return "unknown"


def cleanup_stale_asks(max_age: int = 1800):
    now = time.time()
    with _lock:
        stale = [k for k, v in _pending_asks.items() if now - v["created_at"] > max_age]
        for k in stale:
            del _pending_asks[k]
