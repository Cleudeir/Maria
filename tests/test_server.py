import json
import os
import threading
from unittest.mock import MagicMock

import server


def test_resume_auto_starts_background_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    task_id = "task_test"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = {
        "task_id": task_id,
        "mode": "auto",
        "status": "awaiting_intervention",
        "stage": "executing_steps",
        "proposed_tool": None,
    }
    with open(task_path / "task_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f)

    thread_started = {"started": False}

    class DummyThread:
        def __init__(self, target, args=()):
            self.target = target
            self.args = args
            self.daemon = False

        def start(self):
            thread_started["started"] = True

        def is_alive(self):
            return False

    monkeypatch.setattr(server.threading, "Thread", DummyThread)

    client = server.app.test_client()
    response = client.post(
        f"/api/tasks/{task_id}/action", json={"action": "resume_auto"}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "running"
    assert thread_started["started"] is True
    assert task_id in server.active_threads


def test_resume_auto_rejects_non_auto_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    task_id = "task_step"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = {
        "task_id": task_id,
        "mode": "step",
        "status": "awaiting_intervention",
        "stage": "executing_steps",
        "proposed_tool": None,
    }
    with open(task_path / "task_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f)

    client = server.app.test_client()
    response = client.post(
        f"/api/tasks/{task_id}/action", json={"action": "resume_auto"}
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Task is not in auto mode"


def test_background_execution_loop_supervises_and_reroutes(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    task_id = "task_supervise"
    task_path = tmp_path / task_id
    task_path.mkdir()

    state = {
        "task_id": task_id,
        "task": "Build a safe agent",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "auto",
        "status": "running",
        "stage": "executing_steps",
        "step": 0,
        "max_steps": 20,
        "ollama_url": server.OLLAMA_URL,
        "messages": [],
        "execution_log": [],
        "errors_encountered": [],
        "proposed_tool": {
            "name": "write_file",
            "args": {"path": "danger.py", "content": "print('unsafe')"},
            "thought": "I will write the file next.",
        },
        "last_raw_response": None,
        "step_summaries": [],
        "last_tool_result": None,
        "last_user_intervention": None,
        "plan": "Create a safer implementation.",
        "steps": ["Write a dangerous file"],
        "current_step_idx": 0,
        "completed_step_summaries": [],
        "supervision_status": "idle",
        "supervision_reason": None,
        "supervision_last_review": None,
        "supervision_log": [],
    }
    server.save_task_state(task_id, state)

    def fake_supervise_proposed_tool(*args, **kwargs):
        return {
            "action": "reroute",
            "reason": "The current step is unsafe and should be rewritten.",
            "new_step_description": "Create a secure application structure instead.",
            "thought": "The proposed action is misaligned with the plan.",
            "raw_response": "",
            "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def fake_run_agent_step_sync(task_id_arg, action="approve", modified_tool=None, user_prompt=None):
        current = server.load_task_state(task_id_arg)
        current["status"] = "completed"
        server.save_task_state(task_id_arg, current)
        return current

    monkeypatch.setattr(server, "supervise_proposed_tool", fake_supervise_proposed_tool)
    monkeypatch.setattr(server, "run_agent_step_sync", fake_run_agent_step_sync)
    monkeypatch.setattr(server, "time.sleep", lambda _: None)

    server.background_execution_loop(task_id)
    new_state = server.load_task_state(task_id)

    assert new_state["supervision_status"] == "reroute"
    assert new_state["steps"][0] == "Create a secure application structure instead."
    assert new_state["status"] == "completed"


def test_delete_task_stops_background_thread_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})
    monkeypatch.setattr(server, "task_stop_events", {})

    task_id = "task_test"
    task_path = tmp_path / task_id
    task_path.mkdir()
    with open(task_path / "task_state.json", "w", encoding="utf-8") as f:
        json.dump({"task_id": task_id}, f)

    terminated = {"called": False}

    def fake_terminate(task_id_arg):
        terminated["called"] = task_id_arg == task_id

    monkeypatch.setattr(server, "terminate_task_process_groups", fake_terminate)

    event = server.get_task_stop_event(task_id)

    class DummyThread:
        def __init__(self):
            self.joined = False

        def join(self, timeout=None):
            self.joined = True

        def is_alive(self):
            return False

    server.active_threads[task_id] = DummyThread()

    client = server.app.test_client()
    response = client.delete(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert terminated["called"] is True
    assert event.is_set()
    assert task_id not in server.active_threads
    assert task_id not in server.task_stop_events
    assert not os.path.exists(task_path)


def test_save_task_state_creates_missing_task_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    task_id = "task_missing_dir"
    state = {"task_id": task_id, "mode": "auto", "status": "running"}

    task_path = tmp_path / task_id
    assert not task_path.exists()

    server.save_task_state(task_id, state)

    assert task_path.exists()
    assert (task_path / "task_state.json").exists()
    with open(task_path / "task_state.json", "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["task_id"] == task_id


def test_run_llm_for_tool_pauses_on_invalid_tool_format(monkeypatch):
    state = {
        "step": 1,
        "mode": "auto",
        "messages": [],
        "errors_encountered": [],
        "execution_log": [],
    }

    class DummyClient:
        def __init__(self):
            self.base_url = "http://localhost:11434"
            self.model = "qwen3.5:4b"

    client = DummyClient()

    mock_get_generate = MagicMock(return_value="No valid tool output")
    monkeypatch.setattr(server, "getGenerate", mock_get_generate)
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "awaiting_intervention"
    assert new_state["proposed_tool"] is None
    assert any(err["type"] == "format_error" for err in new_state["errors_encountered"])

    mock_get_generate.return_value = "<think>Thinking through the next step.</think>"
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "awaiting_intervention"
    assert new_state["proposed_tool"] is None
    assert any(err["type"] == "format_error" for err in new_state["errors_encountered"])
    assert mock_get_generate.call_count == 22


def test_run_llm_for_tool_retries_and_succeeds(monkeypatch):
    state = {
        "step": 1,
        "mode": "auto",
        "messages": [],
        "errors_encountered": [],
        "execution_log": [],
    }

    class DummyClient:
        def __init__(self):
            self.base_url = "http://localhost:11434"
            self.model = "qwen3.5:4b"

    client = DummyClient()

    # First returns invalid, second returns valid list_dir tool call
    responses = ["Invalid output first", "<think>Second attempt reasoning</think><tool name=\"list_dir\"><path>.</path></tool>"]
    call_idx = 0

    def mock_get_generate(system, user):
        nonlocal call_idx
        res = responses[call_idx]
        call_idx += 1
        return res

    monkeypatch.setattr(server, "getGenerate", mock_get_generate)
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "running"
    assert new_state["proposed_tool"] == {"name": "list_dir", "args": {"path": "."}, "thought": "<think>Second attempt reasoning</think>"}
    assert len(new_state["errors_encountered"]) == 1
    assert new_state["errors_encountered"][0]["type"] == "format_error"
    assert call_idx == 2


def test_get_legacy_task_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    task_id = "task_20260520_074803"
    task_path = tmp_path / task_id
    task_path.mkdir()

    # Create only task_info.html (without task_state.json)
    html_content = """<!DOCTYPE html>
<html>
<body>
    <div class="task-description">create snake game</div>
</body>
</html>"""
    with open(task_path / "task_info.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    client = server.app.test_client()
    response = client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["task_id"] == task_id
    assert data["task"] == "create snake game"
    assert data["status"] == "legacy"
    assert "file_tree" in data


def test_create_task_with_model_think(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    client = server.app.test_client()
    
    # 1. Create a task with model_think = False
    response = client.post(
        "/api/tasks",
        json={"task": "Test task with think disabled", "mode": "step", "model_think": False}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["model_think"] is False

    task_id = data["task_id"]
    assert (tmp_path / task_id / "output").is_dir()

    # 2. Create a task with model_think = True
    response = client.post(
        "/api/tasks",
        json={"task": "Test task with think enabled", "mode": "step", "model_think": True}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["model_think"] is True

    # 3. Create a task without model_think (should default to True)
    response = client.post(
        "/api/tasks",
        json={"task": "Test task with default think", "mode": "step"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["model_think"] is True
