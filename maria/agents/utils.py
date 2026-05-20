import re
from typing import List, Dict, Tuple, Any


def parse_agent_response(response_text: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Parses agent response using regex to extract thoughts and XML-like tool calls.
    Supports both nested XML tags and tag attributes (including self-closing tags).
    """
    if not isinstance(response_text, str):
        return "", "", {}

    # Extract all text before <tool as the thought if a tool is present
    if re.search(r"<tool\b", response_text, re.IGNORECASE):
        pre_tool_match = re.search(
            r"^(.*?)(?:<tool\b|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        thought = pre_tool_match.group(1).strip() if pre_tool_match else ""
    else:
        thought = ""

    if thought:
        thought = re.sub(
            r"^<(think|thought)>(.*)</(think|thought)>$",
            r"\2",
            thought,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()

    # Find the tool tag
    tool_tag_match = re.search(r"<tool\b[^>]*>", response_text, re.IGNORECASE)
    if not tool_tag_match:
        return thought, "", {}

    tag_content = tool_tag_match.group(0)

    # Extract tool name from tool tag attributes
    name_match = re.search(
        r"\bname\s*=\s*(?:[\"']([^\"']*)[\"']|([^\"'\s>]+))", tag_content, re.IGNORECASE
    )
    if not name_match:
        return thought, "", {}

    tool_name = (name_match.group(1) or name_match.group(2)).strip().lower()
    args = {}

    # Helper function to extract a parameter value
    def get_param(param_name: str, is_line_matching: bool = False) -> str:
        # 1. Try nested tag first
        if is_line_matching:
            nested_match = re.search(
                rf"<{param_name}>([^<]*)", response_text, re.IGNORECASE
            )
        else:
            nested_match = re.search(
                rf"<{param_name}>(.*?)(?:</{param_name}>|\Z)",
                response_text,
                re.DOTALL | re.IGNORECASE,
            )
        if nested_match and nested_match.group(1).strip():
            val = nested_match.group(1)
            return (
                val
                if param_name in ("content", "target", "replacement")
                else val.strip()
            )

        # 2. Try attribute in the tool tag
        attr_match = re.search(
            rf"\b{param_name}\s*=\s*(?:[\"']([^\"']*)[\"']|([^\"'\s>]+))",
            tag_content,
            re.IGNORECASE,
        )
        if attr_match:
            val = attr_match.group(1) or attr_match.group(2)
            return val
        return ""

    # Extract path if relevant
    if tool_name in (
        "list_dir",
        "read_file",
        "write_file",
        "edit_file",
        "find_in_files",
    ):
        args["path"] = get_param("path", is_line_matching=True)

    # Extract content if write_file
    if tool_name == "write_file":
        args["content"] = get_param("content")

    # Extract query if find_in_files or grep_output
    if tool_name in ("find_in_files", "grep_output"):
        args["query"] = get_param("query")

    # Extract target and replacement if edit_file
    if tool_name == "edit_file":
        args["target"] = get_param("target")
        args["replacement"] = get_param("replacement")

    # Extract command if run_command
    if tool_name == "run_command":
        args["command"] = get_param("command", is_line_matching=True)

    # Extract summary if finish_task
    if tool_name == "finish_task":
        args["summary"] = get_param("summary")

    # Extract additional supervision or generic arguments
    for param_name in (
        "reason",
        "new_step_description",
        "path",
        "query",
        "target",
        "replacement",
        "content",
        "command",
        "summary",
    ):
        if param_name not in args:
            value = get_param(
                param_name, is_line_matching=(param_name in ("path", "command"))
            )
            if value:
                args[param_name] = value

    return thought, tool_name, args


def is_llm_response(response_text: str) -> bool:
    """Detect whether a loop response looks like an LLM assistant response."""
    if not isinstance(response_text, str) or not response_text.strip():
        return False
    if re.search(r"<tool\b", response_text, re.IGNORECASE):
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
