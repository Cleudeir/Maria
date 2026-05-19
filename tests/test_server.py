import json
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
    response = client.post(f"/api/tasks/{task_id}/action", json={"action": "resume_auto"})

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
    response = client.post(f"/api/tasks/{task_id}/action", json={"action": "resume_auto"})

    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Task is not in auto mode"


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
        def __init__(self, response_text):
            self.chat = MagicMock(return_value=response_text)

    client = DummyClient("No valid tool output")
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "awaiting_intervention"
    assert new_state["proposed_tool"] is None
    assert any(err["type"] == "format_error" for err in new_state["errors_encountered"])

    client = DummyClient("<thought>Thinking through the next step.</thought>")
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "awaiting_intervention"
    assert new_state["proposed_tool"]["name"] is None
