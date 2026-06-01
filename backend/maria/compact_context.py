import json
from typing import List, Dict, Optional

# Conservative estimate: 1 token ≈ 2.5 characters for code-heavy content
# (GPT/Qwen tokenizers avg ~3.5 chars/token for prose, but code is denser)
_CHARS_PER_TOKEN = 2.5
# Compact when context exceeds 16k tokens to keep requests lean
_MAX_CONTEXT_TOKENS = 16384
_DEFAULT_TOKEN_BUDGET = _MAX_CONTEXT_TOKENS
_DEFAULT_CONTEXT_SAFETY_MARGIN = int(_MAX_CONTEXT_TOKENS * 0.15)  # ~2457
_KEEP_LAST_MESSAGES = 6
_EMERGENCY_TOKEN_BUDGET = int(_MAX_CONTEXT_TOKENS * 0.5)  # ~8192


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _total_tokens(messages: List[Dict[str, str]]) -> int:
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)


def _compact_pair(assistant_msg: Dict, user_msg: Dict) -> str:
    tool_content = user_msg.get("content", "")
    tool_name = _extract_tool_name(assistant_msg.get("content", ""))
    summary = tool_content.strip()[:300]
    if len(tool_content) > 300:
        summary += "..."
    if tool_name:
        return f"[Tool: {tool_name}] → {summary}"
    return summary


def _extract_tool_name(text: str) -> str:
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "tool" in data:
            return data["tool"]
    except (json.JSONDecodeError, TypeError):
        pass
    for line in text.split("\n"):
        line = line.strip()
        if '"tool"' in line or "'tool'" in line:
            try:
                cleaned = line.strip().rstrip(",")
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and "tool" in parsed:
                    return parsed["tool"]
            except (json.JSONDecodeError, TypeError):
                pass
    return ""


def compact_messages(
    messages: List[Dict[str, str]],
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    keep_last: int = _KEEP_LAST_MESSAGES,
    max_context_tokens: int = _MAX_CONTEXT_TOKENS,
) -> List[Dict[str, str]]:
    if not messages:
        return messages

    current_tokens = _total_tokens(messages)
    if current_tokens <= token_budget:
        return messages

    if len(messages) <= 3:
        return messages

    system_msg = None
    if messages[0].get("role") == "system":
        system_msg = messages[0]

    first_user = None
    start_idx = 0
    if system_msg is not None:
        if len(messages) > 1 and messages[1].get("role") == "user":
            first_user = messages[1]
            start_idx = 2

    if start_idx >= len(messages):
        return messages

    middle = messages[start_idx:-keep_last] if keep_last > 0 else messages[start_idx:]
    tail = messages[-keep_last:] if keep_last > 0 else []

    if not middle:
        return messages

    compacted_pairs = []
    i = 0
    while i < len(middle):
        if middle[i].get("role") == "assistant" and i + 1 < len(middle) and middle[i + 1].get("role") == "user":
            compacted_pairs.append(_compact_pair(middle[i], middle[i + 1]))
            i += 2
        elif middle[i].get("role") == "assistant":
            compacted_pairs.append(f"[Assistant]: {middle[i].get('content', '')[:200]}")
            i += 1
        elif middle[i].get("role") == "user":
            compacted_pairs.append(f"[User]: {middle[i].get('content', '')[:200]}")
            i += 1
        else:
            compacted_pairs.append(f"[{middle[i].get('role', 'unknown')}]: {middle[i].get('content', '')[:200]}")
            i += 1

    compact_text = "PAST TOOL INTERACTIONS (compacted to save context):\n" + "\n".join(
        f"- {p}" for p in compacted_pairs
    )

    result = []
    if system_msg is not None:
        result.append(system_msg)
    if first_user is not None:
        result.append(first_user)

    result.append({"role": "user", "content": compact_text})
    result.extend(tail)

    still_over = _total_tokens(result) > token_budget and len(result) > len(tail) + 1 + (1 if system_msg else 0) + (1 if first_user else 0)

    if still_over and tail:
        keep_fewer = max(2, keep_last - 2)
        return compact_messages(messages, token_budget, keep_fewer, max_context_tokens)

    return result


def estimate_tokens(text: str) -> int:
    return _estimate_tokens(text)


def total_tokens(messages: List[Dict[str, str]]) -> int:
    return _total_tokens(messages)
