import os
import re
from typing import List, Tuple, Optional, Callable

from maria.tools import is_binary_file


MAX_FILE_CHARS = 8000
MAX_TOTAL_CHARS = 40000

def verify_execution(
    workspace_dir: str,
    plan: str,
    steps: List[str],
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str]:
    # Gather all files in workspace
    workspace_files_content = ""
    for root, dirs, files in os.walk(workspace_dir):
        # Prune directories in-place to avoid traversing them
        dirs[:] = [
            d
            for d in dirs
            if d not in (".git", ".venv", "__pycache__", ".pytest_cache", "plan", "logs")
        ]
        for file in files:
            if file in ("task_state.json", "task_info.html", "checkpoint.json"):
                continue
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, workspace_dir)
            if is_binary_file(file_path):
                workspace_files_content += (
                    f"\n--- FILE: {rel_path} (binary file, skipped) ---\n"
                )
                continue
            # Stop reading more files if we've hit the total budget
            if len(workspace_files_content) >= MAX_TOTAL_CHARS:
                workspace_files_content += (
                    f"\n--- (remaining files omitted, total content limit reached) ---\n"
                )
                break
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if len(content) > MAX_FILE_CHARS:
                    half = MAX_FILE_CHARS // 2
                    content = content[:half] + "\n\n... [truncated] ...\n\n" + content[-half:]
                workspace_files_content += (
                    f"\n--- FILE: {rel_path} ---\n{content}\n"
                )
            except Exception as e:
                workspace_files_content += (
                    f"\n--- FILE: {rel_path} (Failed to read: {e}) ---\n"
                )
        if len(workspace_files_content) >= MAX_TOTAL_CHARS:
            break

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

Output your response as a JSON object:
{{"analysis": "Your detailed analysis and auditing findings", "verdict": "SUCCESS or FAILED"}}
"""
    response = get_generate_fn(
        system_text="You are a code verification quality control assistant.",
        user_text=prompt,
        progress_callback=stream_callback,
    )

    try:
        import json
        data = json.loads(response)
        analysis = data.get("analysis", response.strip())
        verdict = data.get("verdict", "FAILED").strip().upper()
    except (json.JSONDecodeError, Exception):
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
