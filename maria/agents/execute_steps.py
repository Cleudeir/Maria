from typing import List, Dict, Any, Tuple, Optional, Callable
from maria.provider.base import format_messages_to_prompt
from maria.agents.utils import parse_agent_response


def execute_steps(
    steps: List[str],
    plan: str,
    system_message: str,
    executor,
    execution_log: List[Dict[str, Any]],
    errors_encountered: List[Dict[str, Any]],
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
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

Your objective is to complete ONLY this step using your tools.
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
            thought, tool_name, args = parse_agent_response(response_text)

            if thought:
                print(f"💭 Thought:\n{thought}")
            else:
                print("💭 Thought: (none expressed)")

            if not tool_name:
                print(
                    "⚠️ Formatting error: The model did not output a valid tool call tag structure."
                )
                err_msg = "Format error: You must output your thoughts followed by exactly one <tool name='...'>...</tool>."
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
                format_error_retries += 1
                if format_error_retries >= 10:
                    print(
                        "⚠️ Reached maximum format-error retry attempts for this step."
                    )
                    overall_success = False
                    break
                continue

            print(f"🛠️ Tool Call: {tool_name} with args: {args}")

            if tool_name == "finish_task":
                step_success = True
                summary = args.get("summary", "Step completed.")
                completed_step_summaries.append(f"{step_desc} -> {summary}")
                print(f"✅ Step {step_num} finished: {summary}")
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
            elif tool_name == "run_command":
                tool_result = executor.run_command(args.get("command", ""))
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
            else:
                print(
                    f"🔍 Tool Result:\n{tool_result[:300] + '...' if len(tool_result) > 300 else tool_result}"
                )

            step_messages.append({"role": "assistant", "content": response_text})
            step_messages.append(
                {"role": "user", "content": f"TOOL RESULT:\n{tool_result}"}
            )
            execution_log.append(
                {
                    "step": len(execution_log),
                    "role": "tool_result",
                    "content": tool_result,
                }
            )

        if not step_success:
            print(f"⚠️ Step {step_num} did not finish successfully or timed out.")
            overall_success = False
            break

    return overall_success, completed_step_summaries
