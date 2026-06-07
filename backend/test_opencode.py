"""Smoke test for the OpenCode provider wired through LLMClient.

Loads OPENCODE_API_KEY from backend/.env and exercises:
  1. Direct POST to https://opencode.ai/zen/go/v1/chat/completions
  2. Streaming POST to the same endpoint
  3. agentic.llm.LLMClient with provider_type="opencode" (default model: deepseek-v4-flash)

Exit code 0 on success, non-zero on any failure.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import requests

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

BASE_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4-flash"


def _check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}", file=sys.stderr)
        sys.exit(1)
    print(f"  ok: {message}")


def test_basic_post(api_key: str) -> None:
    print("\n[1/3] Basic POST to OpenCode Zen endpoint")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with the single word: PONG"},
        ],
        "stream": False,
        "temperature": 0.0,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=60)
    _check(resp.status_code == 200, f"status=200 (got {resp.status_code})")
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    _check("PONG" in content, f"response contains PONG (got {content!r})")
    _check("usage" in data, "usage block present")
    print(f"      usage={data['usage']}")


def test_streaming(api_key: str) -> None:
    print("\n[2/3] Streaming POST to OpenCode Zen endpoint")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Count from 1 to 3, separated by commas."}],
        "stream": True,
        "temperature": 0.0,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.post(BASE_URL, json=payload, headers=headers, timeout=60, stream=True)
    _check(resp.status_code == 200, f"status=200 (got {resp.status_code})")
    chunks = 0
    content = ""
    done = False
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        line = raw.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[len("data: "):]
        if data_str == "[DONE]":
            done = True
            break
        event = json.loads(data_str)
        chunks += 1
        delta = event.get("choices", [{}])[0].get("delta", {}) or {}
        c = delta.get("content")
        if isinstance(c, str) and c:
            content += c
    _check(done, "received [DONE] marker")
    _check(chunks > 0, f"received {chunks} chunks")
    _check("1" in content and "3" in content, f"content contains expected output (got {content!r})")


def test_llm_client() -> None:
    print("\n[3/3] LLMClient(provider_type='opencode') end-to-end")
    from agentic.llm import LLMClient

    client = LLMClient(provider_type="opencode")
    _check(client.provider.name == "opencode", f"provider.name == 'opencode' (got {client.provider.name!r})")
    _check(client.provider.model == MODEL, f"provider.model == {MODEL!r} (got {client.provider.model!r})")
    _check(client.provider.base_url == BASE_URL, f"provider.base_url matches (got {client.provider.base_url!r})")

    chunks: list[str] = []
    text = client.chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with the single word: PONG"},
        ],
        temperature=0.0,
        stream_callback=lambda s: chunks.append(s),
    )
    _check("PONG" in text, f"final text contains PONG (got {text!r})")
    _check(len(chunks) > 0, f"stream_callback invoked {len(chunks)} times")
    _check(bool(client.last_usage), f"last_usage populated ({client.last_usage})")


def main() -> int:
    load_dotenv(dotenv_path=BACKEND_DIR / ".env")
    api_key = os.environ.get("OPENCODE_API_KEY", "").strip()
    _check(api_key, "OPENCODE_API_KEY loaded from .env")

    test_basic_post(api_key)
    test_streaming(api_key)
    test_llm_client()

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
