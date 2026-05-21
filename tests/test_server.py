import json
import os
import threading
import time
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


def test_background_execution_loop_runs_supervisor_review_after_completion(
    monkeypatch, tmp_path
):
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
        "stage": "supervisor_review",
        "step": 0,
        "max_steps": 20,
        "ollama_url": server.OLLAMA_URL,
        "messages": [],
        "execution_log": [],
        "errors_encountered": [],
        "proposed_tool": None,
        "last_raw_response": None,
        "step_summaries": [],
        "last_tool_result": None,
        "last_user_intervention": None,
        "plan": "Create a safer implementation.",
        "steps": ["Write a dangerous file"],
        "current_step_idx": 0,
        "completed_step_summaries": ["Wrote initial file"],
        "verification_report": "All files were created, but tests are missing.",
        "verification_verdict": "FAILED",
        "supervision_status": "idle",
        "supervision_reason": None,
        "supervision_last_review": None,
        "supervision_log": [],
    }
    server.save_task_state(task_id, state)

    def fake_supervise_task_result(*args, **kwargs):
        return {
            "action": "review",
            "reason": "The final result is incomplete because tests are missing.",
            "summary": "The code is mostly there, but the task is not fully complete without tests.",
            "raw_response": "",
            "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    monkeypatch.setattr(server, "supervise_task_result", fake_supervise_task_result)
    monkeypatch.setattr(server.time, "sleep", lambda _: None)

    server.background_execution_loop(task_id)
    new_state = server.load_task_state(task_id)

    assert new_state["supervision_status"] == "reviewed"
    assert (
        new_state["supervision_review_summary"]
        == "The code is mostly there, but the task is not fully complete without tests."
    )
    assert new_state["status"] == "failed"


def test_delete_task_stops_background_thread_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    task_id = "task_test"
    task_path = tmp_path / task_id
    task_path.mkdir()
    with open(task_path / "task_state.json", "w", encoding="utf-8") as f:
        json.dump({"task_id": task_id}, f)

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
    assert task_id not in server.active_threads
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


def test_resume_incomplete_auto_task_is_marked_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    task_id = "task_auto_incomplete"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = {
        "task_id": task_id,
        "mode": "auto",
        "status": "running",
        "task": "Run auto task",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    server.save_task_state(task_id, state)

    server.resume_incomplete_tasks()

    new_state = server.load_task_state(task_id)
    assert new_state["status"] == "failed"
    assert "interrupted by application restart" in new_state["details"].lower()


def test_resume_incomplete_step_task_is_reset_to_awaiting_intervention(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    task_id = "task_step_incomplete"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = {
        "task_id": task_id,
        "mode": "step",
        "status": "processando",
        "task": "Run step task",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    server.save_task_state(task_id, state)

    server.resume_incomplete_tasks()

    new_state = server.load_task_state(task_id)
    assert new_state["status"] == "awaiting_intervention"
    assert "interrupted by application restart" in new_state["details"].lower()


def test_save_execution_plan_steps_creates_markdown_file(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    task_id = "task_plan_steps"
    task_path = tmp_path / task_id
    task_path.mkdir()
    steps = ["Create file", "Run tests", "Refactor code"]

    execution_steps_path = server.save_execution_plan_steps(str(task_path), steps)

    assert os.path.exists(execution_steps_path)
    with open(execution_steps_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# Execution Plan Steps" in content
    assert "1. Create file" in content
    assert "2. Run tests" in content
    assert "3. Refactor code" in content


def test_run_llm_for_tool_pauses_on_invalid_tool_format(monkeypatch):
    state = {
        "task_id": "task_dummy",
        "step": 1,
        "mode": "auto",
        "messages": [],
        "errors_encountered": [],
        "execution_log": [],
    }

    monkeypatch.setattr(server, "save_task_state", lambda *a: None)

    class DummyClient:
        def __init__(self):
            self.base_url = "http://localhost:11434"
            self.model = "qwen3.5:4b"
            self.last_usage = None
            self.call_count = 0
            self.responses = []

        def chat(self, messages, temperature=0.1, stream_callback=None):
            self.call_count += 1
            if stream_callback:
                stream_callback("thinking...")
            if self.responses:
                return self.responses.pop(0)
            return "No valid tool output"

    client = DummyClient()

    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "awaiting_intervention"
    assert new_state["proposed_tool"] is None
    assert any(err["type"] == "format_error" for err in new_state["errors_encountered"])
    assert client.call_count == 10

    client.call_count = 0
    client.responses = ["<think>Thinking through the next step.</think>"] * 10
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "awaiting_intervention"
    assert new_state["proposed_tool"] is None
    assert any(err["type"] == "format_error" for err in new_state["errors_encountered"])
    assert client.call_count == 10


def test_run_llm_for_tool_retries_and_succeeds(monkeypatch):
    state = {
        "task_id": "task_dummy",
        "step": 1,
        "mode": "auto",
        "messages": [],
        "errors_encountered": [],
        "execution_log": [],
    }

    monkeypatch.setattr(server, "save_task_state", lambda *a: None)

    class DummyClient:
        def __init__(self):
            self.base_url = "http://localhost:11434"
            self.model = "qwen3.5:4b"
            self.last_usage = {"prompt_tokens": 10}
            self.call_count = 0
            self.responses = [
                "Invalid output first",
                "<tool name=\"list_dir\"><path>.</path></tool>",
            ]

        def chat(self, messages, temperature=0.1, stream_callback=None):
            self.call_count += 1
            if stream_callback:
                stream_callback("thinking...")
            return self.responses.pop(0)

    client = DummyClient()
    new_state = server.run_llm_for_tool(state.copy(), client)

    assert new_state["status"] == "running"
    assert new_state["proposed_tool"] == {
        "name": "list_dir",
        "args": {"path": "."},
    }
    assert len(new_state["errors_encountered"]) == 1
    assert new_state["errors_encountered"][0]["type"] == "format_error"
    assert client.call_count == 2


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


def test_task_full_lifecycle_auto_mode(monkeypatch, tmp_path):
    """Complete task lifecycle through all 6 stages in auto mode"""
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "MEMORY_DIR", str(tmp_path / "memory"))

    # Set up memory files
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    prompt_html = """<!DOCTYPE html><html><body><pre id="system-prompt">System prompt</pre></body></html>"""
    lessons_html = """<!DOCTYPE html><html><body><div id="lessons-list"></div></body></html>"""
    with open(memory_dir / "system_prompt.html", "w", encoding="utf-8") as f:
        f.write(prompt_html)
    with open(memory_dir / "lessons.html", "w", encoding="utf-8") as f:
        f.write(lessons_html)

    fake_improved_prompt = "Improved: Create a test file"
    fake_plan = "# Plan\n1. Create a test file with Hello World content"
    fake_steps = ["Create a test file with Hello World content"]

    monkeypatch.setattr(server.MariaAgent, "improve_prompt", MagicMock(return_value=fake_improved_prompt))
    monkeypatch.setattr(server.MariaAgent, "generate_plan", MagicMock(return_value=fake_plan))
    monkeypatch.setattr(server.MariaAgent, "create_steps", MagicMock(return_value=fake_steps))
    monkeypatch.setattr(server.MariaAgent, "verify_execution", MagicMock(return_value=("SUCCESS", "Verified")))

    # Mock LLM for step execution
    mock_generate = MagicMock(
        return_value='<tool name="finish_task"><summary>Test file created</summary></tool>'
    )
    monkeypatch.setattr("maria.provider.ollama.OllamaProvider.generate", mock_generate)

    # Mock final supervisor review
    fake_review = {
        "action": "review",
        "reason": "Task completed successfully after all steps.",
        "summary": "All steps done.",
        "raw_response": "",
        "reviewed_at": "2026-01-01T00:00:00Z",
    }
    monkeypatch.setattr(server, "supervise_task_result", MagicMock(return_value=fake_review))
    monkeypatch.setattr(server, "trigger_self_improvement", MagicMock())
    monkeypatch.setattr(server.time, "sleep", lambda _: None)

    task_id = "task_full_lifecycle"
    task_path = tmp_path / task_id
    task_path.mkdir()
    os.makedirs(task_path / "output", exist_ok=True)

    state = {
        "task_id": task_id,
        "task": "Create a test file with Hello World content",
        "created_at": "2026-01-01 00:00:00",
        "mode": "auto",
        "status": "running",
        "stage": "improving_prompt",
        "step": 0,
        "max_steps": 20,
        "model_think": True,
        "provider_type": "ollama",
        "ollama_url": server.OLLAMA_URL,
        "messages": [],
        "execution_log": [],
        "errors_encountered": [],
        "proposed_tool": {
            "name": "improve_prompt",
            "args": {},
        },
        "last_raw_response": None,
        "step_summaries": [],
        "last_tool_result": None,
        "last_user_intervention": None,
        "improved_prompt": None,
        "plan": None,
        "steps": [],
        "current_step_idx": 0,
        "completed_step_summaries": [],
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
    server.save_task_state(task_id, state)

    server.background_execution_loop(task_id)

    final_state = server.load_task_state(task_id)
    assert final_state["status"] == "completed", f"Expected completed, got {final_state['status']}"
    assert final_state["stage"] == "supervisor_review"
    assert final_state["improved_prompt"] == fake_improved_prompt
    assert final_state["plan"] == fake_plan
    assert final_state["steps"] == fake_steps
    assert final_state["verification_verdict"] == "SUCCESS"
    assert final_state["supervision_status"] == "reviewed"
    assert final_state["supervision_review_summary"] == "All steps done."
    assert len(final_state["completed_step_summaries"]) == 1
    assert server.MariaAgent.improve_prompt.called
    assert server.MariaAgent.generate_plan.called
    assert server.MariaAgent.create_steps.called
    assert server.MariaAgent.verify_execution.called
    assert server.supervise_task_result.called


def test_raw_task_file_serves_file_content(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    task_id = "task_raw"
    task_path = tmp_path / task_id
    task_path.mkdir()
    file_path = task_path / "preview.html"
    file_content = "<html><body><h1>Preview</h1></body></html>"
    file_path.write_text(file_content, encoding="utf-8")

    client = server.app.test_client()
    response = client.get(f"/api/tasks/{task_id}/files/raw/preview.html")

    assert response.status_code == 200
    assert response.data.decode("utf-8") == file_content
    assert response.headers["Content-Type"].startswith("text/html")


def test_create_task_with_model_think(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    client = server.app.test_client()

    # 1. Create a task with model_think = False
    response = client.post(
        "/api/tasks",
        json={
            "task": "Test task with think disabled",
            "mode": "step",
            "model_think": False,
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["model_think"] is False

    task_id = data["task_id"]
    assert (tmp_path / task_id / "output").is_dir()

    # 2. Create a task with model_think = True
    response = client.post(
        "/api/tasks",
        json={
            "task": "Test task with think enabled",
            "mode": "step",
            "model_think": True,
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["model_think"] is True

    # 3. Create a task without model_think (should default to False)
    response = client.post(
        "/api/tasks", json={"task": "Test task with default think", "mode": "step"}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["model_think"] is False
