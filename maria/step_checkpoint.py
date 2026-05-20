import json
import os
import time

CHECKPOINT_FILENAME = "checkpoint.json"


def get_checkpoint_path(workspace_dir, task_id):
    return os.path.join(workspace_dir, task_id, CHECKPOINT_FILENAME)


def save_checkpoint(workspace_dir, task_id, state):
    task_dir = os.path.join(workspace_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)
    path = os.path.join(task_dir, CHECKPOINT_FILENAME)

    checkpoint = {
        "task_id": task_id,
        "stage": state.get("stage"),
        "status": state.get("status"),
        "step": state.get("step", 0),
        "current_step_idx": state.get("current_step_idx", 0),
        "messages": state.get("messages", []),
        "proposed_tool": state.get("proposed_tool"),
        "completed_step_summaries": state.get("completed_step_summaries", []),
        "steps": state.get("steps", []),
        "plan": state.get("plan"),
        "improved_prompt": state.get("improved_prompt"),
        "last_tool_result": state.get("last_tool_result"),
        "last_user_intervention": state.get("last_user_intervention"),
        "last_raw_response": state.get("last_raw_response"),
        "errors_encountered": state.get("errors_encountered", []),
        "mode": state.get("mode"),
        "verification_report": state.get("verification_report"),
        "verification_verdict": state.get("verification_verdict"),
        "supervision_status": state.get("supervision_status", "idle"),
        "supervision_reason": state.get("supervision_reason"),
        "supervision_review_summary": state.get("supervision_review_summary"),
        "supervision_log": state.get("supervision_log", []),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_checkpoint(workspace_dir, task_id):
    path = get_checkpoint_path(workspace_dir, task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def restore_checkpoint_into_state(checkpoint, state):
    if not checkpoint:
        return state
    for key in (
        "stage", "current_step_idx", "messages", "proposed_tool",
        "completed_step_summaries", "steps", "plan", "improved_prompt",
        "last_tool_result", "last_user_intervention", "last_raw_response",
        "errors_encountered", "verification_report", "verification_verdict",
        "supervision_status", "supervision_reason", "supervision_review_summary",
        "supervision_log",
    ):
        if key in checkpoint and checkpoint[key] is not None:
            state[key] = checkpoint[key]
    if "step" in checkpoint:
        state["step"] = checkpoint["step"]
    return state


def can_resume_from_checkpoint(workspace_dir, task_id):
    cp = load_checkpoint(workspace_dir, task_id)
    if not cp:
        return False
    stage = cp.get("stage")
    status = cp.get("status")
    return stage is not None and status in ("running", "processando", "awaiting_intervention")


def clear_checkpoint(workspace_dir, task_id):
    path = get_checkpoint_path(workspace_dir, task_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
