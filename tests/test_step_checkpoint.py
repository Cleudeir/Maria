import json
import os
import threading
import time
from unittest.mock import patch

import server
from maria.step_checkpoint import (
    save_checkpoint,
    load_checkpoint,
    restore_checkpoint_into_state,
    can_resume_from_checkpoint,
    clear_checkpoint,
    get_checkpoint_path,
    CHECKPOINT_FILENAME,
)


def test_save_checkpoint_creates_file(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_test_save"
    state = {
        "task_id": task_id,
        "stage": "executing_steps",
        "status": "running",
        "step": 5,
        "current_step_idx": 2,
        "messages": [{"role": "user", "content": "hello"}],
        "proposed_tool": {"name": "read_file", "args": {"path": "test.py"}},
        "completed_step_summaries": ["Step 1 done"],
        "steps": ["Step 1", "Step 2", "Step 3"],
        "plan": "Some plan",
        "improved_prompt": "Improved prompt",
        "last_tool_result": "file content",
        "errors_encountered": [],
        "mode": "auto",
        "verification_report": None,
        "verification_verdict": None,
        "supervision_status": "idle",
        "supervision_reason": None,
        "supervision_review_summary": None,
        "supervision_log": [],
    }

    save_checkpoint(workspace, task_id, state)

    path = get_checkpoint_path(workspace, task_id)
    assert os.path.exists(path)

    with open(path, "r", encoding="utf-8") as f:
        cp = json.load(f)

    assert cp["task_id"] == task_id
    assert cp["stage"] == "executing_steps"
    assert cp["status"] == "running"
    assert cp["step"] == 5
    assert cp["messages"] == [{"role": "user", "content": "hello"}]
    assert cp["proposed_tool"] == {"name": "read_file", "args": {"path": "test.py"}}
    assert cp["completed_step_summaries"] == ["Step 1 done"]
    assert cp["timestamp"] is not None


def test_save_checkpoint_creates_task_dir(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_missing_dir"
    state = {"task_id": task_id, "stage": "improving_prompt", "status": "running"}

    task_dir = os.path.join(workspace, task_id)
    assert not os.path.exists(task_dir)

    save_checkpoint(workspace, task_id, state)

    assert os.path.exists(task_dir)


def test_load_checkpoint_returns_state(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_test_load"
    state = {
        "task_id": task_id,
        "stage": "generating_plan",
        "status": "running",
        "step": 3,
        "messages": [{"role": "assistant", "content": "plan..."}],
        "errors_encountered": [],
    }

    save_checkpoint(workspace, task_id, state)
    loaded = load_checkpoint(workspace, task_id)

    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["stage"] == "generating_plan"
    assert loaded["messages"] == [{"role": "assistant", "content": "plan..."}]


def test_load_checkpoint_missing_file(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_nonexistent"
    loaded = load_checkpoint(workspace, task_id)
    assert loaded is None


def test_load_checkpoint_corrupted_file(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_corrupted"
    task_dir = os.path.join(workspace, task_id)
    os.makedirs(task_dir, exist_ok=True)
    with open(os.path.join(task_dir, CHECKPOINT_FILENAME), "w") as f:
        f.write("not valid json")

    loaded = load_checkpoint(workspace, task_id)
    assert loaded is None


def test_restore_checkpoint_into_state_merges_fields(tmp_path):
    checkpoint = {
        "stage": "executing_steps",
        "current_step_idx": 2,
        "messages": [{"role": "user", "content": "continue"}],
        "proposed_tool": {"name": "write_file", "args": {"path": "x.py"}},
        "completed_step_summaries": ["Done 1", "Done 2"],
        "steps": ["Step 1", "Step 2", "Step 3"],
        "plan": "The plan",
        "improved_prompt": "Improved",
        "errors_encountered": [],
        "mode": "auto",
        "last_tool_result": "ok",
        "supervision_status": "idle",
    }
    state = {
        "task_id": "task_restore",
        "task": "original task",
        "status": "running",
        "step": 0,
        "created_at": "2026-01-01",
    }

    result = restore_checkpoint_into_state(checkpoint, state)

    assert result["stage"] == "executing_steps"
    assert result["current_step_idx"] == 2
    assert result["messages"] == [{"role": "user", "content": "continue"}]
    assert result["proposed_tool"] == {"name": "write_file", "args": {"path": "x.py"}}
    assert result["completed_step_summaries"] == ["Done 1", "Done 2"]
    assert result["task_id"] == "task_restore"  # preserved from state
    assert result["task"] == "original task"  # preserved from state


def test_restore_checkpoint_overwrites_existing_fields(tmp_path):
    checkpoint = {
        "stage": "verifying",
        "messages": [{"role": "system", "content": "verify"}],
    }
    state = {
        "task_id": "task_overwrite",
        "stage": "executing_steps",
        "messages": [{"role": "user", "content": "old"}],
    }

    result = restore_checkpoint_into_state(checkpoint, state)

    assert result["stage"] == "verifying"
    assert result["messages"] == [{"role": "system", "content": "verify"}]


def test_restore_checkpoint_none_returns_state_unchanged(tmp_path):
    state = {"task_id": "task_no_cp", "status": "running"}
    result = restore_checkpoint_into_state(None, state)
    assert result["status"] == "running"


def test_can_resume_from_checkpoint_true(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_can_resume"
    state = {"task_id": task_id, "stage": "executing_steps", "status": "running"}
    save_checkpoint(workspace, task_id, state)

    assert can_resume_from_checkpoint(workspace, task_id) is True


def test_can_resume_from_checkpoint_false_for_completed(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_completed"
    state = {"task_id": task_id, "stage": "supervisor_review", "status": "completed"}
    save_checkpoint(workspace, task_id, state)

    assert can_resume_from_checkpoint(workspace, task_id) is False


def test_can_resume_from_checkpoint_false_for_failed(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_failed"
    state = {"task_id": task_id, "stage": "improving_prompt", "status": "failed"}
    save_checkpoint(workspace, task_id, state)

    assert can_resume_from_checkpoint(workspace, task_id) is False


def test_can_resume_no_checkpoint(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_no_cp"
    assert can_resume_from_checkpoint(workspace, task_id) is False


def test_clear_checkpoint_removes_file(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_clear"
    state = {"task_id": task_id, "stage": "executing_steps", "status": "running"}
    save_checkpoint(workspace, task_id, state)

    path = get_checkpoint_path(workspace, task_id)
    assert os.path.exists(path)

    clear_checkpoint(workspace, task_id)
    assert not os.path.exists(path)


def test_clear_checkpoint_no_file_does_not_error(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_no_file"
    clear_checkpoint(workspace, task_id)  # should not raise


def test_save_checkpoint_uses_atomic_write(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_atomic"
    state = {"task_id": task_id, "stage": "creating_steps", "status": "running"}

    save_checkpoint(workspace, task_id, state)

    task_dir = os.path.join(workspace, task_id)
    # Ensure no .tmp file remains after save
    tmp_files = [f for f in os.listdir(task_dir) if f.endswith(".tmp")]
    assert len(tmp_files) == 0


def test_save_checkpoint_updates_existing(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_update"
    state1 = {"task_id": task_id, "stage": "improving_prompt", "status": "running"}
    save_checkpoint(workspace, task_id, state1)

    state2 = {"task_id": task_id, "stage": "generating_plan", "status": "running"}
    save_checkpoint(workspace, task_id, state2)

    loaded = load_checkpoint(workspace, task_id)
    assert loaded["stage"] == "generating_plan"


def test_restore_checkpoint_preserves_none_fields(tmp_path):
    """Fields not in checkpoint should not overwrite existing state values."""
    checkpoint = {"stage": "executing_steps"}
    state = {
        "task_id": "task_none_fields",
        "task": "my task",
        "status": "running",
        "messages": [],
    }

    result = restore_checkpoint_into_state(checkpoint, state)

    assert result["task_id"] == "task_none_fields"
    assert result["task"] == "my task"
    assert result["status"] == "running"
    assert result["stage"] == "executing_steps"
    assert result["messages"] == []


def test_checkpoint_contains_execution_context(tmp_path):
    workspace = str(tmp_path)
    task_id = "task_context"
    state = {
        "task_id": task_id,
        "stage": "executing_steps",
        "status": "running",
        "step": 10,
        "current_step_idx": 3,
        "messages": [
            {"role": "system", "content": "sys msg"},
            {"role": "user", "content": "user msg"},
        ],
        "proposed_tool": {"name": "edit_file", "args": {"path": "x.py", "target": "foo", "replacement": "bar"}},
        "completed_step_summaries": ["Step 1 finished", "Step 2 finished", "Step 3 finished"],
        "steps": ["Step 1", "Step 2", "Step 3", "Step 4", "Step 5"],
        "plan": "Full plan here...",
        "improved_prompt": "Improved prompt here...",
        "last_tool_result": "some output",
        "last_user_intervention": "use python instead",
        "errors_encountered": [
            {"step": 2, "type": "format_error", "message": "bad format"}
        ],
        "mode": "step",
        "verification_report": "report...",
        "verification_verdict": "SUCCESS",
        "supervision_status": "idle",
        "supervision_reason": None,
        "supervision_review_summary": None,
        "supervision_log": [],
    }

    save_checkpoint(workspace, task_id, state)
    cp = load_checkpoint(workspace, task_id)

    assert cp["step"] == 10
    assert cp["current_step_idx"] == 3
    assert len(cp["messages"]) == 2
    assert cp["proposed_tool"]["name"] == "edit_file"
    assert len(cp["completed_step_summaries"]) == 3
    assert len(cp["steps"]) == 5
    assert cp["plan"] == "Full plan here..."
    assert cp["improved_prompt"] == "Improved prompt here..."
    assert cp["last_tool_result"] == "some output"
    assert cp["last_user_intervention"] == "use python instead"
    assert len(cp["errors_encountered"]) == 1
    assert cp["mode"] == "step"
    assert cp["verification_verdict"] == "SUCCESS"
    assert "timestamp" in cp


# --- Integration tests with server module ---


def test_resume_action_restores_checkpoint_and_resets_proposed_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))
    os.makedirs(str(tmp_path / "memory"), exist_ok=True)

    task_id = "task_resume_action"
    task_path = tmp_path / task_id
    task_path.mkdir()
    os.makedirs(task_path / "output", exist_ok=True)

    # Create a task state that was mid-execution
    state = {
        "task_id": task_id,
        "task": "Test task",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "step",
        "status": "processando",
        "stage": "executing_steps",
        "step": 5,
        "max_steps": 20,
        "model_think": True,
        "provider_type": "ollama",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "Plan..."},
            {"role": "assistant", "content": "Let me read the file..."},
            {"role": "user", "content": "TOOL RESULT:\nfile content"},
        ],
        "execution_log": [],
        "errors_encountered": [],
        "proposed_tool": {"name": "read_file", "args": {"path": "test.py"}},
        "last_raw_response": None,
        "step_summaries": [],
        "last_tool_result": "file content",
        "last_user_intervention": None,
        "improved_prompt": "Improved description",
        "plan": "Full implementation plan",
        "steps": ["Step 1", "Step 2", "Step 3"],
        "current_step_idx": 1,
        "completed_step_summaries": ["Step 1 done"],
        "current_streaming_response": "",
        "is_streaming": False,
        "verification_report": None,
        "verification_verdict": None,
        "supervision_review_summary": None,
        "supervision_status": "idle",
        "supervision_reason": None,
        "supervision_last_review": None,
        "supervision_log": [],
    }

    # Save state and checkpoint
    server.save_task_state(task_id, state)
    save_checkpoint(str(tmp_path), task_id, state)
    checkpoint_path = get_checkpoint_path(str(tmp_path), task_id)
    assert os.path.exists(checkpoint_path)

    # Simulate restart: mark_incomplete_task_after_restart
    server.mark_incomplete_task_after_restart(task_id, state)

    # Checkpoint should have been cleared after restore
    assert not os.path.exists(checkpoint_path)

    # State should be restored with proposed_tool cleared
    restored = server.load_task_state(task_id)
    assert restored["status"] == "awaiting_intervention"
    assert restored["stage"] == "executing_steps"
    assert restored["current_step_idx"] == 1
    assert restored["messages"] == state["messages"]
    assert restored["proposed_tool"] is None  # cleared for safe resume
    assert restored["details"] is not None


def test_mark_incomplete_auto_task_with_checkpoint_resumes(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))
    os.makedirs(str(tmp_path / "memory"), exist_ok=True)

    task_id = "task_auto_resume"
    task_path = tmp_path / task_id
    task_path.mkdir()
    os.makedirs(task_path / "output", exist_ok=True)

    state = {
        "task_id": task_id,
        "task": "Auto task",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "auto",
        "status": "running",
        "stage": "generating_plan",
        "step": 2,
        "max_steps": 20,
        "messages": [],
        "execution_log": [],
        "errors_encountered": [],
        "proposed_tool": None,
        "improved_prompt": "Improved",
        "plan": None,
        "steps": [],
        "is_streaming": False,
    }

    server.save_task_state(task_id, state)
    save_checkpoint(str(tmp_path), task_id, state)

    # Mark as incomplete
    server.mark_incomplete_task_after_restart(task_id, state)

    restored = server.load_task_state(task_id)
    assert restored["status"] == "running"
    assert restored["stage"] == "generating_plan"
    assert restored["details"] is not None
    assert "checkpoint" in restored["details"].lower()


def test_mark_incomplete_auto_task_without_checkpoint_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))
    os.makedirs(str(tmp_path / "memory"), exist_ok=True)

    task_id = "task_no_cp_fail"
    task_path = tmp_path / task_id
    task_path.mkdir()

    state = {
        "task_id": task_id,
        "mode": "auto",
        "status": "running",
        "task": "Task without checkpoint",
    }

    server.save_task_state(task_id, state)
    server.mark_incomplete_task_after_restart(task_id, state)

    restored = server.load_task_state(task_id)
    assert restored["status"] == "failed"


def test_mark_incomplete_step_task_without_checkpoint_awaits(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))
    os.makedirs(str(tmp_path / "memory"), exist_ok=True)

    task_id = "task_step_no_cp"
    task_path = tmp_path / task_id
    task_path.mkdir()

    state = {
        "task_id": task_id,
        "mode": "step",
        "status": "processando",
        "task": "Step task without checkpoint",
    }

    server.save_task_state(task_id, state)
    server.mark_incomplete_task_after_restart(task_id, state)

    restored = server.load_task_state(task_id)
    assert restored["status"] == "awaiting_intervention"


def test_resume_incomplete_tasks_scans_and_recovers(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))
    # Disable background thread start for this test (no real LLM)
    monkeypatch.setattr(server, "_start_background_thread", lambda _: None)
    os.makedirs(str(tmp_path / "memory"), exist_ok=True)

    # Task 1: auto mode with checkpoint → should be set to running
    task1_id = "task_auto_with_cp"
    task1_path = tmp_path / task1_id
    task1_path.mkdir()
    os.makedirs(task1_path / "output", exist_ok=True)
    state1 = {
        "task_id": task1_id,
        "mode": "auto",
        "status": "running",
        "task": "Auto task with CP",
        "stage": "executing_steps",
        "current_step_idx": 0,
        "messages": [{"role": "user", "content": "hello"}],
        "proposed_tool": {"name": "read_file", "args": {"path": "x.py"}},
        "steps": ["Step 1"],
    }
    server.save_task_state(task1_id, state1)
    save_checkpoint(str(tmp_path), task1_id, state1)

    # Task 2: step mode without checkpoint → should be awaiting_intervention
    task2_id = "task_step_no_cp"
    task2_path = tmp_path / task2_id
    task2_path.mkdir()
    state2 = {
        "task_id": task2_id,
        "mode": "step",
        "status": "processando",
        "task": "Step task no CP",
    }
    server.save_task_state(task2_id, state2)

    # Task 3: completed → should be left alone
    task3_id = "task_completed"
    task3_path = tmp_path / task3_id
    task3_path.mkdir()
    state3 = {
        "task_id": task3_id,
        "mode": "auto",
        "status": "completed",
        "task": "Completed task",
    }
    server.save_task_state(task3_id, state3)

    # Run resume
    server.resume_incomplete_tasks()

    t1 = server.load_task_state(task1_id)
    assert t1["status"] == "running"
    assert t1["stage"] == "executing_steps"

    t2 = server.load_task_state(task2_id)
    assert t2["status"] == "awaiting_intervention"

    t3 = server.load_task_state(task3_id)
    assert t3["status"] == "completed"  # unchanged


def test_resume_incomplete_auto_task_calls_background_thread(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))
    os.makedirs(str(tmp_path / "memory"), exist_ok=True)

    task_id = "task_auto_thread"
    task_path = tmp_path / task_id
    task_path.mkdir()
    os.makedirs(task_path / "output", exist_ok=True)

    state = {
        "task_id": task_id,
        "mode": "auto",
        "status": "running",
        "task": "Auto task for thread test",
        "stage": "executing_steps",
        "current_step_idx": 0,
        "messages": [{"role": "user", "content": "hello"}],
        "proposed_tool": None,
        "steps": ["Step 1"],
    }
    server.save_task_state(task_id, state)
    save_checkpoint(str(tmp_path), task_id, state)

    thread_started = {"started": False}

    original_start = threading.Thread.start

    def tracking_start(self):
        thread_started["started"] = True
        return original_start(self)

    monkeypatch.setattr(threading.Thread, "start", tracking_start)

    server.resume_incomplete_tasks()
    # Allow a tiny moment for the thread to start
    import time as _time
    _time.sleep(0.05)
    assert thread_started["started"] is True

    # Clean up active threads dict
    if task_id in server.active_threads:
        try:
            server.active_threads[task_id].join(timeout=0.1)
        except Exception:
            pass
        del server.active_threads[task_id]
