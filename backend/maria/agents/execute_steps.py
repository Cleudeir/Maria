import json
from typing import List, Dict, Any, Tuple, Optional, Callable
from maria.provider.base import format_messages_to_prompt
from maria.agents.utils import parse_agent_responses
from maria.runaway import is_runaway_response, truncate_runaway, has_text_loop


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
    on_file_created: Optional[Callable[[str, int], None]] = None,
) -> Tuple[bool, List[str]]:
    """
    Executes the generated steps sequentially using the LLM agentic loop.
    """
    total_steps = len(steps)
    completed_step_summaries = []
    overall_success = True

    # Scan existing files so the agent knows what already exists
    existing_files = executor.list_dir(".")
    existing_files_context = ""
    if existing_files and existing_files != "(Empty directory)":
        existing_files_context = "\nExisting project files before this step:\n" + existing_files + "\n"

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
{existing_files_context if step_idx == 0 else ""}
{"Do exactly what is asked. Do NOT over-engineer. Do NOT create extra files or architecture." if complexity == "simple" else "ORGANIZATION RULE:\n- Split code into separate files by domain/responsibility\n- Each file should contain related functions with a single purpose\n- Each function must have one clear responsibility"}

Your objective is to complete ONLY this step using your tools.
You may call multiple tools in a single response by providing them sequentially:
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
        recent_tool_calls = []  # track tool calls for loop detection
        step_vars = {}  # per-step mutable state (e.g., analysis nudge count)
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

            # Cap and sanitize runaway responses before storing
            if is_runaway_response(response_text):
                response_text = truncate_runaway(response_text)
                execution_log.append({
                    "step": len(execution_log),
                    "role": "system",
                    "content": "⚠️ Runaway generation detected and truncated.",
                })

            # Text loop detection: 20-char segment repeated 3+ times
            if has_text_loop(response_text):
                loop_msg = (
                    f"CRITICAL LOOP DETECTED: Your response contains a repeating text pattern "
                    f"(the same 20-character segment repeated 3+ times). This is an LLM loop.\n\n"
                    f"You MUST stop repeating yourself and immediately call finish_task:\n"
                    f'{{"tool": "finish_task", "args": {{"summary": "Completed step: {step_desc}"}}}}\n\n'
                    f"Call finish_task NOW."
                )
                step_messages.append({"role": "assistant", "content": response_text})
                step_messages.append({"role": "user", "content": loop_msg})
                execution_log.append({
                    "step": len(execution_log),
                    "role": "tool_result",
                    "content": "LOOP DETECTED: Text-level loop (repeating 20-char segment 3+ times).",
                })
                recent_tool_calls.clear()
                continue

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
                        f"Do NOT output anything else. Do NOT add explanation. Just write the file.\n"
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
                        f"Available tools: list_dir, read_file, write_file, edit_file, edit_lines, grep, find_in_files, grep_output, start_http_server, stop_http_server, list_http_servers, run_lint, finish_task\n\n"
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
                elif tool_name == "run_lint":
                    tool_result = executor.run_lint(
                        args.get("language", "python"),
                        args.get("path", "."),
                    )
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
                    # Track created/edited files
                    if tool_name in ("write_file", "edit_file", "edit_lines") and on_file_created:
                        file_path = args.get("path", "")
                        if file_path:
                            on_file_created(file_path, step_num)

                all_results.append(f"[{tool_name}] {tool_result}")

                # Track tool calls for loop detection
                call_signature = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                recent_tool_calls.append(call_signature)
                if len(recent_tool_calls) > 8:
                    recent_tool_calls.pop(0)

            # Loop detection: check for repeated patterns
            if recent_tool_calls:
                # Check for 3+ identical consecutive calls
                if len(recent_tool_calls) >= 3:
                    last_three = recent_tool_calls[-3:]
                    if last_three[0] == last_three[1] == last_three[2]:
                        loop_msg = (
                            f"CRITICAL LOOP DETECTED: You have called the same tool with identical arguments "
                            f"3 times in a row without making progress. This is a loop.\n\n"
                            f"You MUST stop making tool calls and immediately call finish_task:\n"
                            f'{{"tool": "finish_task", "args": {{"summary": "Completed step: {step_desc}"}}}}\n\n'
                            f"Call finish_task NOW."
                        )
                        step_messages.append({"role": "assistant", "content": response_text})
                        step_messages.append({"role": "user", "content": loop_msg})
                        execution_log.append({
                            "step": len(execution_log),
                            "role": "tool_result",
                            "content": "LOOP DETECTED: Identical consecutive calls detected.",
                        })
                        recent_tool_calls.clear()
                        continue

                # Check for alternating file write pattern (same 1-2 files rewritten repeatedly)
                write_file_calls = [c for c in recent_tool_calls if c.startswith("write_file:")]
                if len(write_file_calls) >= 4:
                    written_paths = set()
                    for call in write_file_calls:
                        try:
                            args_str = call[len("write_file:"):]
                            call_args = json.loads(args_str)
                            path = call_args.get("path", "")
                            written_paths.add(path)
                        except (json.JSONDecodeError, KeyError):
                            pass
                    if len(written_paths) <= 2:
                        paths_str = ", ".join(sorted(written_paths))
                        loop_msg = (
                            f"CRITICAL LOOP DETECTED: You have written the same file(s) repeatedly "
                            f"({paths_str}) {len(write_file_calls)} times without making progress. "
                            f"This is a loop.\n\n"
                            f"You MUST stop making tool calls and immediately call finish_task:\n"
                            f'{{"tool": "finish_task", "args": {{"summary": "Completed step: {step_desc}"}}}}\n\n'
                            f"Call finish_task NOW."
                        )
                        step_messages.append({"role": "assistant", "content": response_text})
                        step_messages.append({"role": "user", "content": loop_msg})
                        execution_log.append({
                            "step": len(execution_log),
                            "role": "tool_result",
                            "content": "LOOP DETECTED: Alternating file write pattern detected.",
                        })
                        recent_tool_calls.clear()
                        continue

                # Analysis loop nudging: 2+ read-only tool calls without writing
                non_finish_calls = [c for c in recent_tool_calls if not c.startswith("finish_task:")]
                if len(non_finish_calls) >= 2:
                    write_calls = [c for c in non_finish_calls if c.startswith("write_file:") or c.startswith("edit_file:") or c.startswith("edit_lines:")]
                    if len(write_calls) == 0:
                        if "_analysis_nudge_count" not in step_vars:
                            step_vars["_analysis_nudge_count"] = 0
                        step_vars["_analysis_nudge_count"] += 1
                        nudge_count = step_vars["_analysis_nudge_count"]

                        if nudge_count >= 2:
                            # Force-finish the step
                            summary = f"Step auto-completed after {nudge_count} analysis loop nudges: {step_desc}"
                            completed_step_summaries.append(f"{step_desc} -> {summary}")
                            execution_log.append({
                                "step": len(execution_log),
                                "role": "system",
                                "content": f"✅ Step {step_num} Auto-Completed (analysis loop): {summary}",
                            })
                            print(f"✅ Auto-completed step {step_num} due to analysis loop ({nudge_count} nudges)")
                            step_success = True
                            stop_after_tools = True
                            step_messages.append({"role": "assistant", "content": response_text})
                            step_messages.append({"role": "user", "content": (
                                f"CRITICAL: You were stuck in an analysis loop after {nudge_count} warnings. "
                                f"The step has been auto-completed. Call finish_task to proceed."
                            )})
                            recent_tool_calls.clear()
                            break
                        else:
                            nudge_msg = (
                                f"WARNING: You have made {len(non_finish_calls)} tool calls without writing any files "
                                f"or calling finish_task. You are likely stuck in an analysis loop.\n\n"
                                f"CURRENT STEP: {step_desc}\n\n"
                                f"Warning {nudge_count}/2. After 2 warnings, the step will be auto-completed.\n\n"
                                f"IMPORTANT: 'write_file' automatically creates parent directories. Do NOT list_dir first - just write files directly.\n\n"
                                f"Your current tool calls have been discarded. If you have enough information, "
                                f"start implementing by calling write_file or edit_file. "
                                f"If the step is already complete, call finish_task immediately."
                            )
                            step_messages.append({"role": "assistant", "content": response_text})
                            step_messages.append({"role": "user", "content": nudge_msg})
                            execution_log.append({
                                "step": len(execution_log),
                                "role": "tool_result",
                                "content": f"WARNING: Analysis loop detected - nudging toward implementation (nudge {nudge_count}/2).",
                            })
                            recent_tool_calls.clear()
                            continue

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
