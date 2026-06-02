import json
import re
from typing import List, Dict, Tuple, Any

from maria.runaway import is_runaway_response


def _extract_json_object(text: str, start_idx: int) -> str:
    """Extract a JSON object starting at start_idx by tracking balanced braces, accounting for strings."""
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            continue
            
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
            
        if in_string:
            continue
            
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[start_idx:i+1]
    
    # If we reached the end without closing all braces, try to recover
    # by adding a closing quote for unclosed strings and missing braces
    fixed = text[start_idx:]
    if in_string:
        while fixed.endswith('`'):
            fixed = fixed[:-1]
        fixed += '"'
    for _ in range(brace_count):
        fixed += '}'
    return fixed


def _sanitize_json_string(json_str: str) -> str:
    """Fix common JSON issues from LLM output, like literal newlines in strings."""
    result = []
    in_string = False
    escape_next = False
    
    for i, char in enumerate(json_str):
        if escape_next:
            result.append(char)
            escape_next = False
            continue
            
        if char == '\\':
            result.append(char)
            escape_next = True
            continue
            
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
            
        if in_string and char in ('\n', '\r', '\t'):
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            continue
            
        result.append(char)
    
    sanitized = ''.join(result)
    
    # Strip trailing markdown code fences that got included due to unclosed JSON strings
    if sanitized.endswith('```'):
        sanitized = sanitized[:-3]
    if sanitized.endswith('``'):
        sanitized = sanitized[:-2]
    
    return sanitized


def parse_agent_response(response_text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parses agent response to extract a single JSON tool call.
    Expected format: {"tool": "tool_name", "args": {"param1": "value1", ...}}
    Handles markdown code blocks and common LLM formatting issues.
    Returns (tool_name, args).
    """
    calls = parse_agent_responses(response_text)
    if calls:
        return calls[0]
    return "", {}


def parse_agent_responses(response_text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Parses agent response to extract ALL JSON tool calls.
    Supports both formats:
      1. Sequential JSON objects: {"tool": "a", ...} {"tool": "b", ...}
      2. JSON array: [{"tool": "a", ...}, {"tool": "b", ...}]
    Handles markdown code blocks and common LLM formatting issues.
    Returns a list of (tool_name, args) tuples.
    """
    if not isinstance(response_text, str):
        return []

    if is_runaway_response(response_text):
        return []

    results = []
    text = response_text.strip()

    # Strip markdown code fences that LLMs commonly wrap around JSON
    text = re.sub(r'^```(?:json|JSON)?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Try JSON array format first
    array_match = re.search(r'\[\s*\{', text, re.DOTALL)
    if array_match:
        array_start = array_match.start()
        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False
        end_idx = -1
        for i in range(array_start, len(text)):
            char = text[i]
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    end_idx = i + 1
                    break
            elif char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1

        if end_idx > 0:
            array_str = text[array_start:end_idx]
            try:
                data_list = json.loads(array_str)
                if isinstance(data_list, list):
                    for item in data_list:
                        if isinstance(item, dict):
                            tool_name = item.get("tool", "").strip().lower()
                            if "args" not in item:
                                args = {k: v for k, v in item.items() if k != "tool"}
                            else:
                                args = item.get("args", {})
                            if tool_name:
                                results.append((tool_name, args))
            except json.JSONDecodeError:
                pass

    # If array format didn't yield results, try sequential JSON objects
    if not results:
        pos = 0
        while True:
            json_match = re.search(r'"tool"\s*:', text[pos:], re.DOTALL)
            if not json_match:
                break

            # Find the opening brace before "tool"
            tool_pos = pos + json_match.start()
            start_idx = text.rfind('{', 0, tool_pos + 1)
            if start_idx < 0:
                pos = tool_pos + 1
                continue

            json_str = _extract_json_object(text, start_idx)
            if not json_str:
                pos = start_idx + 1
                continue

            json_str = _sanitize_json_string(json_str)
            try:
                data = json.loads(json_str)
                tool_name = data.get("tool", "").strip().lower()
                if "args" not in data:
                    args = {k: v for k, v in data.items() if k != "tool"}
                else:
                    args = data.get("args", {})
                if tool_name:
                    results.append((tool_name, args))
            except json.JSONDecodeError:
                pass

            pos = start_idx + len(json_str)

    return results


def is_llm_response(response_text: str) -> bool:
    """Detect whether a loop response looks like an LLM assistant response."""
    if not isinstance(response_text, str) or not response_text.strip():
        return False
    if re.search(r'"tool"\s*:', response_text, re.DOTALL):
        return True
    return False


def parse_self_improvement_response(
    response_text: str,
) -> Tuple[str, List[Dict[str, str]], str]:
    """
    Parses the self-improvement output from the meta-agent.
    """
    analysis_match = re.search(
        r"<analysis>(.*?)</analysis>", response_text, re.DOTALL | re.IGNORECASE
    )
    analysis = analysis_match.group(1).strip() if analysis_match else ""

    lessons = []
    lesson_blocks = re.findall(
        r"<lesson>(.*?)</lesson>", response_text, re.DOTALL | re.IGNORECASE
    )
    for block in lesson_blocks:
        title_match = re.search(
            r"<title>(.*?)</title>", block, re.DOTALL | re.IGNORECASE
        )
        error_match = re.search(
            r"<error>(.*?)</error>", block, re.DOTALL | re.IGNORECASE
        )
        resolution_match = re.search(
            r"<resolution>(.*?)</resolution>", block, re.DOTALL | re.IGNORECASE
        )

        if title_match and resolution_match:
            lessons.append(
                {
                    "title": title_match.group(1).strip(),
                    "error": error_match.group(1).strip() if error_match else "",
                    "resolution": resolution_match.group(1).strip(),
                }
            )

    prompt_match = re.search(
        r"<improved_system_prompt>(.*?)</improved_system_prompt>",
        response_text,
        re.DOTALL | re.IGNORECASE,
    )
    improved_prompt = prompt_match.group(1).strip() if prompt_match else ""

    return analysis, lessons, improved_prompt


def parse_compacted_lessons_response(response_text: str) -> List[Dict[str, str]]:
    """
    Parses the consolidated lessons from LLM.
    """
    lessons = []
    lesson_blocks = re.findall(
        r"<lesson>(.*?)</lesson>", response_text, re.DOTALL | re.IGNORECASE
    )
    for block in lesson_blocks:
        title_match = re.search(
            r"<title>(.*?)</title>", block, re.DOTALL | re.IGNORECASE
        )
        error_match = re.search(
            r"<error>(.*?)</error>", block, re.DOTALL | re.IGNORECASE
        )
        resolution_match = re.search(
            r"<resolution>(.*?)</resolution>", block, re.DOTALL | re.IGNORECASE
        )

        if title_match and resolution_match:
            lessons.append(
                {
                    "title": title_match.group(1).strip(),
                    "error": error_match.group(1).strip() if error_match else "",
                    "resolution": resolution_match.group(1).strip(),
                }
            )
    return lessons
