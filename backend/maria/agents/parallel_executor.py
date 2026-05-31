import threading
import time
from typing import List, Dict, Any, Tuple, Optional, Callable
from maria.provider import create_provider, PROVIDER_URLS
from maria.agents.utils import parse_agent_response
from maria.provider.base import format_messages_to_prompt


def execute_single_step(
    step_idx: int,
    step_desc: str,
    plan: str,
    completed_context: str,
    system_message: str,
    workspace_path: str,
    provider_type: str,
    base_url: str,
    model_think: bool,
    complexity: str,
    on_log: Optional[Callable] = None,
) -> Tuple[bool, str]:
    """Execute a single step using its own LLM client and tool executor."""
    from maria.tools import ToolExecutor

    executor = ToolExecutor(workspace_path)
    provider = create_provider(provider_type, base_url=base_url, model_think=model_think)

    messages = [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": f"""We are executing a multi-stage plan.
Complete Plan:
{plan}
{completed_context}
Step Description: {step_desc}

{"Do exactly what is asked. Do NOT over-engineer." if complexity == "simple" else "ORGANIZATION RULE:\n- Split code into separate files\n- Each file should contain related functions"}

Your objective is to complete ONLY this step using your tools.
When you believe this step is fully complete, call the 'finish_task' tool with a summary.
""",
        },
    ]

    step_turns = 0
    max_turns = 15
    final_summary = ""
    success = False

    while step_turns < max_turns:
        step_turns += 1
        system_text, user_text = format_messages_to_prompt(messages)
        try:
            response_text = provider.generate(
                system_text=system_text,
                user_text=user_text,
            )
        except Exception as e:
            final_summary = f"Error: {e}"
            break

        tool_name, args = parse_agent_response(response_text)
        if not tool_name:
            messages.append({"role": "user", "content": "Please output a valid JSON tool call."})
            continue

        if tool_name == "finish_task":
            final_summary = args.get("summary", "Step completed.")
            success = True
            break

        # Execute tool
        try:
            if tool_name == "list_dir":       result = executor.list_dir(args.get("path", "."))
            elif tool_name == "read_file":    result = executor.read_file(args.get("path", ""))
            elif tool_name == "write_file":   result = executor.write_file(args.get("path", ""), args.get("content", ""))
            elif tool_name == "edit_file":    result = executor.edit_file(args.get("path", ""), args.get("old_text", ""), args.get("new_text", ""))
            elif tool_name == "edit_lines":   result = executor.edit_lines(args.get("path", ""), args.get("start_line", 1), args.get("end_line", 1), args.get("new_text", ""))
            elif tool_name == "grep":         result = executor.grep(args.get("pattern", ""), args.get("path", "."))
            elif tool_name == "find_in_files": result = executor.find_in_files(args.get("pattern", ""), args.get("path", "."))
            elif tool_name == "grep_output":  result = executor.grep_output(args.get("pattern", ""), args.get("path", "."))
            elif tool_name == "run_command":  result = executor.run_command(args.get("command", ""))
            else: result = f"Error: Unknown tool '{tool_name}'"
        except Exception as e:
            result = f"Error: {e}"

        messages.append({"role": "assistant", "content": response_text})
        tool_content = f"TOOL RESULT:\n{result}"
        if result.startswith("Error:") and "exited with code 127" in result:
            tool_content += (
                f"\n\nADVICE: The command was not found (exit code 127). "
                f"This means the executable is not installed or not in PATH.\n"
                f"SOLUTIONS:\n"
                f"1. Use npx to run local packages: e.g., 'npx jest' instead of 'jest'\n"
                f"2. Install dependencies first: 'npm install' or 'npm ci'\n"
                f"3. Check if the command name is correct\n"
                f"4. For test runners, always use npx: 'npx jest', 'npx vitest', etc.\n"
                f"Do NOT retry the same command - it will fail again. Try a different approach."
            )
        messages.append({"role": "user", "content": tool_content})

    return success, final_summary


def run_parallel_group(
    group: List[int],
    steps: List[str],
    plan: str,
    completed_context: str,
    system_message: str,
    workspace_path: str,
    primary_provider: str,
    model_think: bool,
    complexity: str,
    on_log: Optional[Callable] = None,
) -> List[Tuple[int, bool, str]]:
    """
    Run a group of steps in parallel on different providers.
    Returns list of (step_idx, success, summary) tuples.
    """
    # Distribute steps across available providers
    provider_list = ["llamacpp", "llamacpp_2"]

    results = [None] * len(group)
    threads = []

    def _worker(i, step_idx):
        provider_type = provider_list[i % len(provider_list)]
        base_url = PROVIDER_URLS.get(provider_type, PROVIDER_URLS["llamacpp"])
        success, summary = execute_single_step(
            step_idx=step_idx,
            step_desc=steps[step_idx],
            plan=plan,
            completed_context=completed_context,
            system_message=system_message,
            workspace_path=workspace_path,
            provider_type=provider_type,
            base_url=base_url,
            model_think=model_think,
            complexity=complexity,
            on_log=on_log,
        )
        results[i] = (step_idx, success, summary)

    for i, step_idx in enumerate(group):
        t = threading.Thread(target=_worker, args=(i, step_idx))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=600)  # 10 min timeout per parallel group

    return [r for r in results if r is not None]
