import json
import logging
from typing import List, Dict, Optional

from agentic.runaway import is_runaway_response, truncate_runaway

logger = logging.getLogger(__name__)

# Qwen3.5 tokenizer avg ~3.5 chars/token for mixed code+prose
_CHARS_PER_TOKEN = 3.5
# Max context for the model (Qwen3.5-4B loaded with --ctx-size 8192)
_MAX_CONTEXT_TOKENS = 8192
# Messages budget: 50% of context, leaving room for response
_DEFAULT_TOKEN_BUDGET = int(_MAX_CONTEXT_TOKENS * 0.5)  # 4096
_KEEP_LAST_MESSAGES = 4
_EMERGENCY_TOKEN_BUDGET = int(_MAX_CONTEXT_TOKENS * 0.35)  # ~2867


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _total_tokens(messages: List[Dict[str, str]]) -> int:
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)


_WARNING_KEYWORDS = [
    "WARNING:", "LOOP DETECTED", "analysis loop",
    "CRITICAL:", "nudging toward implementation",
    "auto-completed", "5 tool calls without writing",
    "stuck in an analysis loop",
]


def _is_warning_message(msg: Dict) -> bool:
    content = msg.get("content", "")
    for kw in _WARNING_KEYWORDS:
        if kw in content:
            return True
    return False


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
        logger.debug("compact_messages called with empty messages")
        return messages

    # Step 0: scrub any runaway/generative repetition content before compacting
    scrubbed = False
    for msg in messages:
        content = msg.get("content", "")
        if content and is_runaway_response(content):
            msg["content"] = truncate_runaway(content)
            logger.warning("detected and truncated runaway content in %s message (was %d chars)", msg.get("role"), len(content))
            scrubbed = True
    if scrubbed:
        current_tokens = _total_tokens(messages)
        if current_tokens <= token_budget:
            logger.info("after runaway scrub, messages are within budget — returning early")
            return messages

    current_tokens = _total_tokens(messages)
    if current_tokens <= token_budget:
        logger.debug(
            "compact_messages skipped (within budget): %d msgs, %d tokens, budget %d",
            len(messages), current_tokens, token_budget,
        )
        return messages

    logger.info(
        "compacting %d messages (%d tokens, budget %d, keep_last=%d)",
        len(messages), current_tokens, token_budget, keep_last,
    )

    if len(messages) <= 3:
        return _truncate_large_messages(messages, max_tokens=token_budget)

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

    # Extract warning messages to keep them intact (not compacted)
    protected = []
    filtered_middle = []
    i = 0
    while i < len(middle):
        if _is_warning_message(middle[i]):
            protected.append(middle[i])
            i += 1
        elif (i + 1 < len(middle)
              and middle[i].get("role") == "assistant"
              and middle[i + 1].get("role") == "user"
              and _is_warning_message(middle[i + 1])):
            protected.append(middle[i])
            protected.append(middle[i + 1])
            i += 2
        else:
            filtered_middle.append(middle[i])
            i += 1

    compacted_pairs = []
    i = 0
    while i < len(filtered_middle):
        if filtered_middle[i].get("role") == "assistant" and i + 1 < len(filtered_middle) and filtered_middle[i + 1].get("role") == "user":
            compacted_pairs.append(_compact_pair(filtered_middle[i], filtered_middle[i + 1]))
            i += 2
        elif filtered_middle[i].get("role") == "assistant":
            compacted_pairs.append(f"[Assistant]: {filtered_middle[i].get('content', '')[:200]}")
            i += 1
        elif filtered_middle[i].get("role") == "user":
            compacted_pairs.append(f"[User]: {filtered_middle[i].get('content', '')[:200]}")
            i += 1
        else:
            compacted_pairs.append(f"[{filtered_middle[i].get('role', 'unknown')}]: {filtered_middle[i].get('content', '')[:200]}")
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
    result.extend(protected)
    result.extend(tail)

    still_over = _total_tokens(result) > token_budget and len(result) > len(tail) + 1 + (1 if system_msg else 0) + (1 if first_user else 0)

    if still_over and tail:
        keep_fewer = max(0, keep_last - 2)
        return compact_messages(messages, token_budget, keep_fewer, max_context_tokens)

    # If still over budget after compacting middle, truncate system and first_user messages
    if still_over or _total_tokens(result) > token_budget:
        result = _truncate_large_messages(result, max_tokens=token_budget)

    # Final check: if still over, use max_context_tokens as absolute limit
    if _total_tokens(result) > token_budget and max_context_tokens:
        result = _truncate_large_messages(result, max_tokens=int(max_context_tokens * 0.35))

    logger.info(
        "compacted %d messages (%d tokens) -> %d messages (%d tokens)",
        len(messages), current_tokens, len(result), _total_tokens(result),
    )
    return result


def _truncate_large_messages(messages: List[Dict[str, str]], max_tokens: int = _DEFAULT_TOKEN_BUDGET) -> List[Dict[str, str]]:
    """Truncate very large messages (system, first user) to fit within budget."""
    if not messages:
        return messages

    result = []
    total_tokens = 0
    max_per_msg_tokens = int(max_tokens * 0.4)  # No single message should exceed 40% of budget

    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        msg_tokens = _estimate_tokens(content)

        if msg_tokens > max_per_msg_tokens and i < 2:  # Only truncate first 2 messages (system + first user)
            max_chars = int(max_per_msg_tokens * _CHARS_PER_TOKEN)
            truncated = content[:max_chars] + "\n\n[... content truncated to fit context window ...]"
            result.append({"role": msg.get("role", "user"), "content": truncated})
            total_tokens += _estimate_tokens(truncated)
        else:
            result.append(msg)
            total_tokens += msg_tokens

    return result


def estimate_tokens(text: str) -> int:
    return _estimate_tokens(text)


def total_tokens(messages: List[Dict[str, str]]) -> int:
    return _total_tokens(messages)
