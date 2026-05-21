from datetime import datetime
from typing import Any, Dict, List, Optional

from maria.provider.opencode import OpenCodeProvider
from maria.agents.utils import parse_agent_response

_default_supervision_provider = OpenCodeProvider()


def _default_generate(system_text, user_text, progress_callback=None):
    return _default_supervision_provider.generate(system_text, user_text, progress_callback)


def build_supervision_prompt(
    task: str,
    stage: str,
    plan: str,
    steps: List[str],
    current_step_idx: int,
    proposed_tool: Dict[str, Any],
    completed_summaries: List[str],
    last_tool_result: Optional[str] = None,
    last_user_intervention: Optional[str] = None,
) -> str:
    prompt_lines = [
        "You are a supervisor for an autonomous coding agent.",
        "Your role is to make an independent judgment about the next proposed action.",
        "Do not ask the user for help or intervention unless the command is critical.",
        "If the proposed action is unsafe or not aligned, reroute the step instead of pausing.",
        "Only respond with one of the following JSON-formatted tool calls:",
        '{"tool": "approve", "args": {"reason": "..."}}',
        '{"tool": "reroute", "args": {"new_step_description": "...", "reason": "..."}}',
        '{"tool": "pause", "args": {"reason": "..."}}',
        "",
        f"Task: {task}",
        f"Current Stage: {stage}",
    ]

    if plan:
        prompt_lines.append("\nComplete Plan:")
        prompt_lines.append(plan)

    if stage == "executing_steps" and steps:
        step_num = current_step_idx + 1
        prompt_lines.extend(
            [
                "",
                f"Current Step: {step_num} of {len(steps)}",
                f"Step Description: {steps[current_step_idx]}",
            ]
        )

    prompt_lines.extend(
        [
            "",
            "Proposed Action:",
            f"Tool Name: {proposed_tool.get('name')}",
            f"Tool Args: {proposed_tool.get('args', {})}",
        ]
    )

    if completed_summaries:
        prompt_lines.extend(["", "Previously completed steps:"])
        for idx, summary in enumerate(completed_summaries, 1):
            prompt_lines.append(f"{idx}. {summary}")

    if last_tool_result:
        prompt_lines.extend(["", "Last tool result:", last_tool_result])

    if last_user_intervention:
        prompt_lines.extend(["", "Last user instruction:", last_user_intervention])

    prompt_lines.extend(
        [
            "",
            "Your job is to determine whether the proposed action is the right next move.",
            '- Use {"tool": "approve", "args": {"reason": "..."}} when the proposed action is aligned and safe.',
            '- Use {"tool": "reroute", "args": {"new_step_description": "...", "reason": "..."}} when the current step or plan should be rewritten before proceeding.',
            '- Use {"tool": "pause", "args": {"reason": "..."}} when you need a human or higher-level review to continue.',
            "Only one tool call may be returned.",
        ]
    )

    return "\n".join(prompt_lines)


def supervise_proposed_tool(
    task: str,
    stage: str,
    plan: str,
    steps: List[str],
    current_step_idx: int,
    proposed_tool: Dict[str, Any],
    completed_summaries: List[str],
    last_tool_result: Optional[str] = None,
    last_user_intervention: Optional[str] = None,
    get_generate_fn=_default_generate,
) -> Dict[str, Any]:
    prompt = build_supervision_prompt(
        task=task,
        stage=stage,
        plan=plan,
        steps=steps,
        current_step_idx=current_step_idx,
        proposed_tool=proposed_tool,
        completed_summaries=completed_summaries,
        last_tool_result=last_tool_result,
        last_user_intervention=last_user_intervention,
    )

    try:
        response_text = get_generate_fn(system_text=None, user_text=prompt)
        if not response_text or not response_text.strip():
            return {
                "action": "approve",
                "reason": "Supervisor returned empty response - auto-approved to continue execution.",
                "new_step_description": "",
                "raw_response": "",
                "reviewed_at": datetime.now().isoformat(),
            }
        tool_name, args = parse_agent_response(response_text)
    except Exception as e:
        return {
            "action": "approve",
            "reason": f"Supervisor failed to read response - auto-approved to continue. Error: {e}",
            "new_step_description": "",
            "raw_response": "",
            "reviewed_at": datetime.now().isoformat(),
        }

    action = tool_name.lower() if tool_name else "pause"
    if action not in ("approve", "reroute", "pause"):
        action = "pause"

    return {
        "action": action,
        "reason": args.get("reason", "No reason provided."),
        "new_step_description": args.get("new_step_description", ""),
        "raw_response": response_text,
        "reviewed_at": datetime.now().isoformat(),
    }


def build_result_supervision_prompt(
    task: str,
    plan: str,
    steps: List[str],
    completed_summaries: List[str],
    verification_report: str,
    verdict: str,
) -> str:
    prompt_lines = [
        "You are an autonomous supervisor that only reviews the final completed task result.",
        "Do not interrupt or change execution now. Your job is to analyze the completed work, the verification report, and explain whether the result is strong, weak, or requires a retry.",
        "Answer with a single JSON tool call:",
        '{"tool": "review", "args": {"reason": "...", "summary": "..."}}',
        "",
        f"Task: {task}",
        "",
        "Complete Plan:",
        plan,
        "",
        "Steps:",
    ]

    for idx, step in enumerate(steps, 1):
        prompt_lines.append(f"{idx}. {step}")

    if completed_summaries:
        prompt_lines.extend(["", "Completed Step Summaries:"])
        for idx, summary in enumerate(completed_summaries, 1):
            prompt_lines.append(f"{idx}. {summary}")

    prompt_lines.extend(
        [
            "",
            "Verification Report:",
            verification_report,
            "",
            f"Verification Verdict: {verdict}",
            "",
            "Provide a clear final analysis of the result and whether the task should be considered complete.",
        ]
    )

    return "\n".join(prompt_lines)


def supervise_task_result(
    task: str,
    plan: str,
    steps: List[str],
    completed_summaries: List[str],
    verification_report: str,
    verdict: str,
    get_generate_fn=_default_generate,
) -> Dict[str, Any]:
    prompt = build_result_supervision_prompt(
        task=task,
        plan=plan,
        steps=steps,
        completed_summaries=completed_summaries,
        verification_report=verification_report,
        verdict=verdict,
    )

    try:
        response_text = get_generate_fn(system_text=None, user_text=prompt)
        if not response_text or not response_text.strip():
            return {
                "action": "review",
                "reason": "Supervisor returned empty response - auto-reviewed based on verification verdict.",
                "summary": f"Verification verdict: {verdict}",
                "raw_response": "",
                "reviewed_at": datetime.now().isoformat(),
            }
        tool_name, args = parse_agent_response(response_text)
    except Exception as e:
        return {
            "action": "review",
            "reason": f"Supervisor failed to read response - auto-reviewed based on verification verdict. Error: {e}",
            "summary": f"Verification verdict: {verdict}",
            "raw_response": "",
            "reviewed_at": datetime.now().isoformat(),
        }

    if tool_name.lower() not in ("review", "approve", "pause"):
        tool_name = "review"

    return {
        "action": "review",
        "reason": args.get("reason", "No reason provided."),
        "summary": args.get("summary", ""),
        "raw_response": response_text,
        "reviewed_at": datetime.now().isoformat(),
    }
