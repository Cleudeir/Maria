import json
import re
from typing import List, Dict, Tuple, Any


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
    
    return ""


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
    
    return ''.join(result)


def parse_agent_response(response_text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parses agent response to extract JSON tool calls.
    Expected format: {"tool": "tool_name", "args": {"param1": "value1", ...}}
    Handles markdown code blocks and common LLM formatting issues.
    Returns (tool_name, args).
    """
    if not isinstance(response_text, str):
        return "", {}

    json_match = re.search(r'\{[^{}]*"tool"\s*:', response_text, re.DOTALL)
    if not json_match:
        return "", {}

    start_idx = json_match.start()
    json_str = _extract_json_object(response_text, start_idx)
    
    if not json_str:
        return "", {}

    json_str = _sanitize_json_string(json_str)

    try:
        data = json.loads(json_str)
        tool_name = data.get("tool", "").strip().lower()
        args = data.get("args", {})
        if not tool_name:
            return "", {}
        return tool_name, args
    except json.JSONDecodeError:
        return "", {}


def is_llm_response(response_text: str) -> bool:
    """Detect whether a loop response looks like an LLM assistant response."""
    if not isinstance(response_text, str) or not response_text.strip():
        return False
    if re.search(r'\{[^{}]*"tool"\s*:', response_text, re.DOTALL):
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
