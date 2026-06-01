from typing import List, Dict, Any, Tuple, Optional, Callable
from maria.provider.base import format_messages_to_prompt
from maria.agents.utils import parse_agent_responses


def execute_steps(
    steps: List[str],
    plan: str,
    system_message: str,
    executor,
    execution_log: List[Dict[str, Any]],
    errors_encountered: List[Dict[str, Any]],
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
    complexity: str = "complex",
) -> Tuple[bool, List[str]]:
    """
    Executes the generated steps sequentially using the LLM agentic loop.
    """
    total_steps = len(steps)
    completed_step_summaries = []
    overall_success = True

    for step_idx, step_desc in enumerate(steps):
        step_num = step_idx + 1
        print(f"\n==========================================")
        print(f"🎬 EXECUTING STEP {step_num}/{total_steps}: {step_desc}")
        print(f"==========================================")

        execution_log.append(
            {
                "step": len(execution_log),
                "role": "system",
                "content": f"Starting Step {step_num}/{total_steps}: {step_desc}",
            }
        )

        # Context with previously completed steps
        completed_context = ""
        if completed_step_summaries:
            completed_context = "\nPreviously completed steps:\n"
            for idx, summary in enumerate(completed_step_summaries, 1):
                completed_context += f"Step {idx}: {summary}\n"

        step_messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": f"""We are executing a multi-stage plan.
Complete Plan:
{plan}
{completed_context}
Current Step: Step {step_num} of {total_steps}
Step Description: {step_desc}

{"Do exactly what is asked. Do NOT over-engineer. Do NOT create extra files or architecture." if complexity == "simple" else "ORGANIZATION RULE:\n- Split code into separate files by domain/responsibility\n- Each file should contain related functions with a single purpose\n- Each function must have one clear responsibility"}

Your objective is to complete ONLY this step using your tools.
You may call multiple tools in a single response by providing them sequentially:
{{"tool": "run_command", "args": {{"command": "mkdir -p output"}}}}
{{"tool": "write_file", "args": {{"path": "output/file.txt", "content": "..."}}}}
Or as a JSON array:
[{{"tool": "tool1", "args": {{...}}}}, {{"tool": "tool2", "args": {{...}}}}]
When you believe this step is fully complete, call the 'finish_task' tool with a summary of what you did.
""",
            },
        ]

        step_turns = 0
        format_error_retries = 0
        step_success = False
        while step_turns < 15:  # Max 15 turns per step
            step_turns += 1
            print(f"\n--- Step {step_num} - Turn {step_turns} ---")

            try:
                system_text, user_text = format_messages_to_prompt(step_messages)
                response_text = get_generate_fn(
                    system_text=system_text,
                    user_text=user_text,
                    progress_callback=stream_callback,
                )
            except Exception as e:
                err_msg = f"LLM error: {e}"
                print(f"❌ {err_msg}")
                errors_encountered.append(
                    {"step": step_num, "type": "llm_error", "message": err_msg}
                )
                overall_success = False
                break

            execution_log.append(
                {
                    "step": len(execution_log),
                    "role": "assistant",
                    "content": response_text,
                }
            )
            tool_calls = parse_agent_responses(response_text)

            if not tool_calls:
                print(
                    "⚠️ Formatting error: The model did not output a valid tool call tag structure."
                )
                format_error_retries += 1

                if format_error_retries >= 8:
                    err_msg = (
                        f"CRITICAL: You have failed to output a valid tool call {format_error_retries} times.\n\n"
                        f"You MUST write the code directly using write_file now. Do NOT try any other tools.\n"
                        f'Use exactly this format: {{"tool": "write_file", "args": {{"path": "output/filename", "content": "your code here"}}}}\n\n'
                        f"Do NOT output anything else. Do NOT add explanation. Do NOT try run_command, do NOT list_dir.\n"
                        f"Just write the file. If the step is already done, call finish_task.\n\n"
                        f"CURRENT STEP: {step_desc}"
                    )
                elif format_error_retries >= 5:
                    err_msg = (
                        f"ERROR: Format error (attempt {format_error_retries}). Your response could not be parsed into a valid tool call.\n\n"
                        f"You are repeating the same mistake. STOP and simplify drastically.\n"
                        f'Use ONLY this exact format: {{"tool": "write_file", "args": {{"path": "output/filename", "content": "code"}}}}\n\n'
                        f"Do NOT use any other tool. Do NOT add explanation before/after.\n"
                        f"CURRENT STEP: {step_desc}"
                    )
                else:
                    err_msg = (
                        f"ERROR: Format error - Your response could not be parsed into a valid tool call.\n\n"
                        f"CORRECT FORMAT:\n"
                        f'{{"tool": "tool_name", "args": {{"parameter_name": "value"}}}}\n\n'
                        f"Available tools: list_dir, read_file, write_file, edit_file, edit_lines, grep, find_in_files, grep_output, run_command, start_http_server, stop_http_server, list_http_servers, finish_task\n\n"
                        f"CURRENT STEP: {step_desc}\n\n"
                        f"Output ONLY a valid JSON tool call. No explanations. No markdown."
                    )
                errors_encountered.append(
                    {"step": step_num, "type": "format_error", "message": err_msg}
                )
                step_messages.append({"role": "assistant", "content": response_text})
                step_messages.append({"role": "user", "content": f"ERROR:\n{err_msg}"})
                execution_log.append(
                    {
                        "step": len(execution_log),
                        "role": "tool_result",
                        "content": f"ERROR: {err_msg}",
                    }
                )
                continue

            # Execute all tool calls sequentially
            all_results = []
            stop_after_tools = False
            for tool_name, args in tool_calls:
                print(f"🛠️ Tool Call: {tool_name} with args: {args}")

                if tool_name == "finish_task":
                    step_success = True
                    summary = args.get("summary", "Step completed.")
                    completed_step_summaries.append(f"{step_desc} -> {summary}")
                    print(f"✅ Step {step_num} finished: {summary}")
                    stop_after_tools = True
                    break

                # Execute tool
                tool_result = ""
                if tool_name == "list_dir":
                    tool_result = executor.list_dir(args.get("path", "."))
                elif tool_name == "read_file":
                    tool_result = executor.read_file(args.get("path", ""))
                elif tool_name == "write_file":
                    tool_result = executor.write_file(
                        args.get("path", ""), args.get("content", "")
                    )
                elif tool_name == "find_in_files":
                    tool_result = executor.find_in_files(
                        args.get("query", ""), args.get("path", ".")
                    )
                elif tool_name == "grep_output":
                    tool_result = executor.grep_output(args.get("query", ""))
                elif tool_name == "edit_file":
                    tool_result = executor.edit_file(
                        args.get("path", ""),
                        args.get("target", ""),
                        args.get("replacement", ""),
                    )
                elif tool_name == "edit_lines":
                    tool_result = executor.edit_lines(
                        args.get("path", ""),
                        args.get("start_line", 1),
                        args.get("end_line", 1),
                        args.get("replacement", ""),
                    )
                elif tool_name == "grep":
                    tool_result = executor.grep(
                        args.get("path", ""),
                        args.get("pattern", ""),
                    )
                elif tool_name == "run_command":
                    tool_result = executor.run_command(args.get("command", ""))
                elif tool_name == "start_http_server":
                    tool_result = executor.start_http_server(
                        args.get("port", 10010),
                        args.get("path", "."),
                    )
                elif tool_name == "stop_http_server":
                    tool_result = executor.stop_http_server(
                        args.get("server_id", ""),
                    )
                elif tool_name == "list_http_servers":
                    tool_result = executor.list_http_servers()
                else:
                    tool_result = f"Error: Tool '{tool_name}' is not supported."

                if tool_result.startswith("Error:"):
                    print(f"❌ Tool Execution Error:\n{tool_result}")
                    errors_encountered.append(
                        {
                            "step": step_num,
                            "tool": tool_name,
                            "args": args,
                            "error": tool_result,
                        }
                    )
                    if "Invalid path. Please specify a file path under the output directory" in tool_result:
                        tool_result = (
                            f"{tool_result}\n\n"
                            f"⚠️ CRITICAL: Do NOT repeat this mistake! "
                            f"You called '{tool_name}' with an empty or invalid path (path='{args.get('path', '')}'). "
                            f"Always specify a valid file path like 'output/filename.ext' or just 'filename.ext'. "
                            f"Never use empty string, '.', or './' as the path.\n\n"
                            f"Current Step {step_num} instruction: {step_desc}"
                        )
                    elif "exited with code 127" in tool_result:
                        tool_result += (
                            f"\n\nADVICE: The command was not found (exit code 127). "
                            f"This means the executable is not installed or not in PATH.\n"
                            f"SOLUTIONS:\n"
                            f"1. Use npx to run local packages: e.g., 'npx jest' instead of 'jest'\n"
                            f"2. Install dependencies first: 'npm install' or 'npm ci'\n"
                            f"3. Check if the command name is correct\n"
                            f"4. For test runners, always use npx: 'npx jest', 'npx vitest', etc.\n"
                            f"Do NOT retry the same command - it will fail again. Try a different approach."
                        )
                    else:
                        tool_result += (
                            f"\n\nADVICE: The tool execution failed. "
                            f"Check the error and path and try a different approach. "
                            f"If a file does not exist, create it first with write_file (parent dirs are auto-created). "
                            f"Review what went wrong and correct your approach."
                        )
                else:
                    print(
                        f"🔍 Tool Result:\n{tool_result[:300] + '...' if len(tool_result) > 300 else tool_result}"
                    )

                all_results.append(f"[{tool_name}] {tool_result}")

            combined_result = "\n---\n".join(all_results)
            step_messages.append({"role": "assistant", "content": response_text})
            step_messages.append(
                {"role": "user", "content": f"TOOL RESULTS:\n{combined_result}"}
            )
            execution_log.append(
                {
                    "step": len(execution_log),
                    "role": "tool_result",
                    "content": combined_result,
                }
            )

            if stop_after_tools:
                break

        if not step_success:
            print(f"⚠️ Step {step_num} did not finish successfully or timed out.")
            overall_success = False
            break

    return overall_success, completed_step_summaries
