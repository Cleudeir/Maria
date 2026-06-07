import json
import os
import time

TASK_FILENAME = "task.json"


def get_task_path(workspace_dir, task_id):
    return os.path.join(workspace_dir, task_id, TASK_FILENAME)


def save_checkpoint(workspace_dir, task_id, state):
    task_dir = os.path.join(workspace_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)
    path = os.path.join(task_dir, TASK_FILENAME)

    state["_checkpoint"] = time.strftime("%Y-%m-%d %H:%M:%S")

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def load_checkpoint(workspace_dir, task_id):
    path = get_task_path(workspace_dir, task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "_checkpoint" in data:
            return {
                "task_id": data.get("task_id"),
                "stage": data.get("stage"),
                "status": data.get("status"),
                "step": data.get("step", 0),
                "current_step_idx": data.get("current_step_idx", 0),
                "messages": data.get("messages", []),
                "proposed_tool": data.get("proposed_tool"),
                "completed_step_summaries": data.get("completed_step_summaries", []),
                "steps": data.get("steps", []),
                "plan": data.get("plan"),
                "improved_prompt": data.get("improved_prompt"),
                "last_tool_result": data.get("last_tool_result"),
                "last_user_intervention": data.get("last_user_intervention"),
                "last_raw_response": data.get("last_raw_response"),
                "errors_encountered": data.get("errors_encountered", []),
                "mode": data.get("mode"),
                "timestamp": data.get("_checkpoint"),
            }
        return None
    except (json.JSONDecodeError, IOError):
        return None


def restore_checkpoint_into_state(checkpoint, state):
    if not checkpoint:
        return state
    for key in (
        "stage", "current_step_idx", "messages", "proposed_tool",
        "completed_step_summaries", "steps", "plan", "improved_prompt",
        "last_tool_result", "last_user_intervention", "last_raw_response",
        "errors_encountered",
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
    return stage is not None and status in ("running", "processando")


def clear_checkpoint(workspace_dir, task_id):
    path = get_task_path(workspace_dir, task_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            state.pop("_checkpoint", None)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            pass
