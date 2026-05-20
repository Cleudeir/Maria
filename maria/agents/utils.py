import re
from typing import List, Dict, Tuple, Any

def parse_agent_response(response_text: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Parses agent response using regex to extract thoughts and XML-like tool calls.
    """
    if not isinstance(response_text, str):
        return "", "", {}

    # Extract all text before <tool as the thought if a tool is present
    if re.search(r"<tool\s+name=", response_text, re.IGNORECASE):
        pre_tool_match = re.search(
            r"^(.*?)(?:<tool|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        thought = pre_tool_match.group(1).strip() if pre_tool_match else ""
    else:
        thought = ""

    # Find tool call name
    tool_match = re.search(
        r"<tool\s+name=[\"']([^\"']+)[\"']\s*>", response_text, re.IGNORECASE
    )
    if not tool_match:
        return thought, "", {}

    tool_name = tool_match.group(1).strip().lower()
    args = {}

    # Extract path if relevant - match until the next '<' character to handle closing tag typos
    if tool_name in ("list_dir", "read_file", "write_file", "edit_file", "find_in_files"):
        path_match = re.search(r"<path>([^<]*)", response_text, re.IGNORECASE)
        args["path"] = path_match.group(1).strip() if path_match else ""

    # Extract content if write_file - match until closing tag or end of text
    if tool_name == "write_file":
        content_match = re.search(
            r"<content>(.*?)(?:</content>|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        args["content"] = content_match.group(1) if content_match else ""

    # Extract query if find_in_files or grep_output
    if tool_name in ("find_in_files", "grep_output"):
        query_match = re.search(
            r"<query>(.*?)(?:</query>|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        args["query"] = query_match.group(1).strip() if query_match else ""

    # Extract target and replacement if edit_file
    if tool_name == "edit_file":
        target_match = re.search(
            r"<target>(.*?)(?:</target>|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        args["target"] = target_match.group(1) if target_match else ""

        replacement_match = re.search(
            r"<replacement>(.*?)(?:</replacement>|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        args["replacement"] = replacement_match.group(1) if replacement_match else ""

    # Extract command if run_command - match until next '<' character
    if tool_name == "run_command":
        command_match = re.search(r"<command>([^<]*)", response_text, re.IGNORECASE)
        args["command"] = command_match.group(1).strip() if command_match else ""

    # Extract summary if finish_task
    if tool_name == "finish_task":
        summary_match = re.search(
            r"<summary>(.*?)(?:</summary>|\Z)", response_text, re.DOTALL | re.IGNORECASE
        )
        args["summary"] = summary_match.group(1).strip() if summary_match else ""

    return thought, tool_name, args


def is_llm_response(response_text: str) -> bool:
    """Detect whether a loop response looks like an LLM assistant response."""
    if not isinstance(response_text, str) or not response_text.strip():
        return False
    if re.search(r"<tool\s+name=", response_text, re.IGNORECASE):
        return True
    return False


def parse_self_improvement_response(response_text: str) -> Tuple[str, List[Dict[str, str]], str]:
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
