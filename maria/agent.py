import os
import json
import re
from typing import Callable, List, Dict, Tuple, Any, Optional
from maria.llm import LLMClient
from maria.memory import load_system_prompt, load_lessons, add_task_history
from maria.tools import ToolExecutor, is_binary_file


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

    results = []
    text = response_text.strip()

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
                            args = item.get("args", {})
                            if tool_name:
                                results.append((tool_name, args))
            except json.JSONDecodeError:
                pass

    # If array format didn't yield results, try sequential JSON objects
    if not results:
        pos = 0
        while True:
            json_match = re.search(r'\{[^{}]*"tool"\s*:', text[pos:], re.DOTALL)
            if not json_match:
                break

            start_idx = pos + json_match.start()
            json_str = _extract_json_object(text, start_idx)
            if not json_str:
                pos = start_idx + 1
                continue

            json_str = _sanitize_json_string(json_str)
            try:
                data = json.loads(json_str)
                tool_name = data.get("tool", "").strip().lower()
                args = data.get("args", {})
                if tool_name:
                    results.append((tool_name, args))
            except json.JSONDecodeError:
                pass

            pos = start_idx + len(json_str)

    return results


class MariaAgent:
    def __init__(
        self,
        workspace_dir: str,
        memory_dir: str,
        ollama_url: str = "http://localhost:11434",
        provider_type: str = "ollama",
        model_think: bool = False,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.memory_dir = os.path.abspath(memory_dir)
        self.client = LLMClient(
            base_url=ollama_url,
            provider_type=provider_type,
            model_think=model_think,
        )
        self.executor = ToolExecutor(self.workspace_dir)
        self.execution_log = []
        self.errors_encountered = []

    def improve_prompt(
        self,
        task: str,
        lessons: List[Dict[str, str]],
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        prompt = f"""You are an expert prompt engineer. Your job is to improve the user's prompt to be extremely clear, detailed, precise, and structured. 
Ensure all requirements, edge cases, and testing strategies are explicit. Keep the original intent intact.

Original User Task:
---
{task}
---

Response Format:
Provide only the improved task prompt. Do not add any preamble (like "Here is the improved prompt:") or XML tags. Just the refined, detailed prompt.
"""
        response = self.client.chat(
            [
                {"role": "system", "content": "You are a prompt optimizer assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            stream_callback=stream_callback,
        )
        return response.strip()

    def generate_plan(
        self,
        improved_prompt: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        prompt = f"""You are a senior software architect. Based on the following detailed task description, generate a complete, comprehensive implementation plan.
The plan must describe:
1. Architecture & Design Choices
2. Target File Structure (files to create, files to modify)
3. Step-by-step implementation strategy
4. Testing strategy (how to verify each component)

Important: The plan should be descriptive only. Do not include code snippets, pseudocode, or direct implementation commands. Explain what to do, but do not write the code itself.

Detailed Task Description:
---
{improved_prompt}
---

Response Format:
Provide the complete plan in clear Markdown. No conversational preamble.
"""
        response = self.client.chat(
            [
                {
                    "role": "system",
                    "content": "You are a software architect assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            stream_callback=stream_callback,
        )
        return response.strip()

    def create_steps(
        self,
        plan: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> List[str]:
        prompt = f"""You are a technical project manager. Read the implementation plan below and break it down into a list of specific, sequential, actionable steps.
Each step must:
- Be clear and focus on a single objective (e.g. "Create folder structure", "Implement factorial function in math_utils.py", "Create unit tests in test_math.py", "Run pytest and fix errors").
- Be numbered sequentially (e.g., 1., 2., 3.).

CRITICAL REQUIREMENT:
The list of steps must be extremely concise and contain at most 3 to 5 high-level sequential milestones. Do not create micro-steps (like editing a single line, styling a button, or writing individual files). Group related activities together into broad phases (for example: Phase 1: Implement HTML/CSS structure and core JavaScript logic; Phase 2: Run verification and fix bugs; Phase 3: Finalize). Fewer steps are highly preferred to minimize transitions.

Implementation Plan:
---
{plan}
---

Response Format:
Provide ONLY the numbered list of steps (e.g. "1. Step description\n2. Step description\n..."). No preamble, no other text.
"""
        response = self.client.chat(
            [
                {"role": "system", "content": "You are a project manager assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            stream_callback=stream_callback,
        )

        # Parse numbered list
        steps = []
        for line in response.strip().splitlines():
            line = line.strip()
            # Match lines starting with a number followed by a dot or parenthesis, e.g., 1. or 1)
            match = re.match(r"^\d+[\.\)]\s*(.*)", line)
            if match:
                step_desc = match.group(1).strip()
                if step_desc:
                    steps.append(step_desc)
            elif line and not line.startswith(("#", "-", "*")):
                # Fallback if no numbers but has text
                steps.append(line)
        return steps

    def verify_execution(
        self,
        plan: str,
        steps: List[str],
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[str, str]:
        # Gather all files in workspace
        workspace_files_content = ""
        for root, dirs, files in os.walk(self.workspace_dir):
            # Prune directories in-place to avoid traversing them
            dirs[:] = [
                d
                for d in dirs
                if d not in (".git", ".venv", "__pycache__", ".pytest_cache", "plan")
            ]
            for file in files:
                if file in ("task_state.json", "task_info.html"):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.workspace_dir)
                if is_binary_file(file_path):
                    workspace_files_content += (
                        f"\n--- FILE: {rel_path} (binary file, skipped) ---\n"
                    )
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    workspace_files_content += (
                        f"\n--- FILE: {rel_path} ---\n{content}\n"
                    )
                except Exception as e:
                    workspace_files_content += (
                        f"\n--- FILE: {rel_path} (Failed to read: {e}) ---\n"
                    )

        steps_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))

        prompt = f"""You are a QA engineer and code auditor. Your task is to verify if the implementation matches the plan and all execution steps were fully completed.
Analyze the implementation plan, the execution steps, and the generated workspace files.

Implementation Plan:
---
{plan}
---

Execution Steps:
---
{steps_str}
---

Generated Workspace Files & Content:
---
{workspace_files_content}
---

MISSION:
1. Audit the generated files against the plan and execution steps.
2. Determine if anything is missing, incomplete, or contains obvious bugs.
3. Conclude with a clear verdict: "VERDICT: SUCCESS" if all steps were executed successfully and code is complete, or "VERDICT: FAILED" if there are missing parts, errors, or uncompleted steps. Provide detailed feedback.

Output your response using these XML tags:
<analysis>Your detailed analysis and auditing findings</analysis>
<verdict>SUCCESS or FAILED</verdict>
"""
        response = self.client.chat(
            [
                {
                    "role": "system",
                    "content": "You are a code verification quality control assistant.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            stream_callback=stream_callback,
        )

        analysis_match = re.search(
            r"<analysis>(.*?)</analysis>", response, re.DOTALL | re.IGNORECASE
        )
        verdict_match = re.search(
            r"<verdict>(.*?)</verdict>", response, re.DOTALL | re.IGNORECASE
        )

        analysis = (
            analysis_match.group(1).strip() if analysis_match else response.strip()
        )
        verdict = verdict_match.group(1).strip().upper() if verdict_match else "FAILED"
        if "SUCCESS" in verdict:
            verdict = "SUCCESS"
        else:
            verdict = "FAILED"

        return verdict, analysis

    def run(self, task: str, max_steps: int = 20) -> bool:
        """
        Runs the agentic loop to solve a task.
        """
        print(f"🚀 Starting Maria Agent...")
        print(f"📂 Workspace: {self.workspace_dir}")
        print(f"🧠 Memory: {self.memory_dir}")
        print(f"📋 Task: {task}\n")

        self.execution_log = []
        self.errors_encountered = []

        # 1. Load memories
        try:
            base_prompt = load_system_prompt(self.memory_dir)
        except Exception as e:
            print(f"⚠️ Error loading system prompt, using fallback. Error: {e}")
            base_prompt = "You are Maria, an agentic coding assistant. Use TDD."

        lessons = load_lessons(self.memory_dir)
        lessons_prompt = ""
        if lessons:
            lessons_prompt = "\n\nCRITICAL: Lessons learned from previous runs to prevent repeating mistakes:\n"
            for i, l in enumerate(lessons, 1):
                lessons_prompt += f"Lesson {i}: {l['title']}\n"
                if l.get("error"):
                    lessons_prompt += f"  Previous Error: {l['error']}\n"
                lessons_prompt += f"  Correction/Resolution: {l['resolution']}\n"

        system_message = base_prompt + lessons_prompt

        # --- Stage 1: Improve Prompt ---
        print("💡 Stage 1: Improving user prompt...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 1: Improving user prompt...",
            }
        )
        improved_prompt = self.improve_prompt(task, lessons)
        print(f"Improved Prompt:\n{improved_prompt}\n")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": f"Improved Prompt:\n{improved_prompt}",
            }
        )

        # --- Stage 2: Generate Plan ---
        print("📋 Stage 2: Generating complete plan...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 2: Generating complete plan...",
            }
        )
        plan = self.generate_plan(improved_prompt)
        print(f"Complete Plan:\n{plan}\n")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"Complete Plan:\n{plan}"}
        )

        # Save plan overview to file for compatibility
        try:
            plan_dir = os.path.join(self.workspace_dir, "plan")
            os.makedirs(plan_dir, exist_ok=True)
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as f:
                f.write(plan)
        except Exception as e:
            print(f"⚠️ Warning: Could not write plan.md: {e}")

        # --- Stage 3: Create Steps ---
        print("🛠️ Stage 3: Creating execution steps...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 3: Creating execution steps...",
            }
        )
        steps = self.create_steps(plan)
        steps_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
        print(f"Execution Steps:\n{steps_str}\n")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"Execution Steps:\n{steps_str}"}
        )

        if not steps:
            print("❌ No execution steps generated. Aborting.")
            return False

        # --- Stage 4: Execute Steps ---
        total_steps = len(steps)
        completed_step_summaries = []
        overall_success = True

        for step_idx, step_desc in enumerate(steps):
            step_num = step_idx + 1
            print(f"\n==========================================")
            print(f"🎬 EXECUTING STEP {step_num}/{total_steps}: {step_desc}")
            print(f"==========================================")

            self.execution_log.append(
                {
                    "step": len(self.execution_log),
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
You may call multiple tools in a single response by providing them sequentially:
{"tool": "run_command", "args": {"command": "mkdir -p output"}}
{"tool": "write_file", "args": {"path": "output/file.txt", "content": "..."}}
Or as a JSON array:
[{"tool": "tool1", "args": {...}}, {"tool": "tool2", "args": {...}}]
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
                    response_text = self.client.chat(step_messages, temperature=0.1)
                except Exception as e:
                    err_msg = f"LLM error: {e}"
                    print(f"❌ {err_msg}")
                    self.errors_encountered.append(
                        {"step": step_num, "type": "llm_error", "message": err_msg}
                    )
                    overall_success = False
                    break

                self.execution_log.append(
                    {
                        "step": len(self.execution_log),
                        "role": "assistant",
                        "content": response_text,
                    }
                )
                tool_calls = parse_agent_responses(response_text)

                if not tool_calls:
                    print(
                        "⚠️ Formatting error: The model did not output a valid tool call tag structure."
                    )
                    err_msg = 'Format error: You must output your reasoning followed by one or more JSON tool calls: {"tool": "tool_name", "args": {}} or [{"tool": "a", "args": {}}, {"tool": "b", "args": {}}]. Do not ask questions or request input.'
                    self.errors_encountered.append(
                        {"step": step_num, "type": "format_error", "message": err_msg}
                    )
                    step_messages.append(
                        {"role": "assistant", "content": response_text}
                    )
                    step_messages.append(
                        {"role": "user", "content": f"ERROR:\n{err_msg}"}
                    )
                    self.execution_log.append(
                        {
                            "step": len(self.execution_log),
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
                        all_results.append(f"[finish_task] {summary}")
                        break

                    # Execute tool
                    tool_result = ""
                    if tool_name == "list_dir":
                        tool_result = self.executor.list_dir(args.get("path", "."))
                    elif tool_name == "read_file":
                        tool_result = self.executor.read_file(args.get("path", ""))
                    elif tool_name == "write_file":
                        tool_result = self.executor.write_file(
                            args.get("path", ""), args.get("content", "")
                        )
                    elif tool_name == "run_command":
                        tool_result = self.executor.run_command(args.get("command", ""))
                    else:
                        tool_result = f"Error: Tool '{tool_name}' is not supported."

                    if tool_result.startswith("Error:"):
                        print(f"❌ Tool Execution Error:\n{tool_result}")
                        self.errors_encountered.append(
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
                self.execution_log.append(
                    {
                        "step": len(self.execution_log),
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

        if not overall_success:
            print("❌ Execution interrupted due to step failure.")
            # Record final status
            try:
                add_task_history(
                    self.memory_dir,
                    task,
                    "FAILED",
                    f"Step execution failed at step {len(completed_step_summaries) + 1}",
                )
            except Exception:
                pass
            return False

        # --- Stage 5: Final Verification ---
        print("\n🔍 Stage 5: Verifying all plan was executed...")
        self.execution_log.append(
            {
                "step": len(self.execution_log),
                "role": "system",
                "content": "Stage 5: Verifying all plan was executed...",
            }
        )

        verdict, analysis_report = self.verify_execution(plan, steps)
        print(f"Analysis Report:\n{analysis_report}\n")
        print(f"Final Verdict: {verdict}")

        self.execution_log.append(
            {
                "step": len(self.execution_log),
                "role": "system",
                "content": f"Analysis Report:\n{analysis_report}\n\nFinal Verdict: {verdict}",
            }
        )

        # Save verification report
        try:
            with open(
                os.path.join(self.workspace_dir, "verification_report.md"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    f"# Verification Report\n\nVerdict: {verdict}\n\n{analysis_report}"
                )
        except Exception as e:
            print(f"⚠️ Warning: Could not write verification_report.md: {e}")

        success = verdict == "SUCCESS"

        # 5. Record final task status in HTML memory
        status_str = "SUCCESS" if success else "FAILED"
        details_str = (
            analysis_report if success else f"Verification failed. Verdict: {verdict}"
        )
        try:
            add_task_history(self.memory_dir, task, status_str, details_str[:200])
        except Exception as e:
            print(f"⚠️ Failed to write task history: {e}")

        return success
