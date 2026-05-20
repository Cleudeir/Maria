"""
Tests for the task-start freeze fix.

Verifies:
1. Task creation immediately sets status="running" (never "awaiting_intervention" on start).
2. A background thread is launched right away for BOTH auto and step modes.
3. The /action endpoint returns immediately (non-blocking) even during LLM execution.
4. The duplicate-thread guard prevents stacking concurrent executions for the same task.
"""

import json
import os
import time
import threading
from unittest.mock import MagicMock, patch

import pytest
import server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_full_state(task_id, mode="step", status="running", stage="improving_prompt"):
    return {
        "task_id": task_id,
        "task": "hello world task",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "status": status,
        "stage": stage,
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
            "thought": "Let's begin by improving the user prompt using the LLM.",
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


class DummyThread:
    """Thread substitute that records calls without actually running anything."""

    def __init__(self, target=None, args=()):
        self.target = target
        self.args = args
        self.daemon = False
        self.started = False
        self._alive = False

    def start(self):
        self.started = True
        self._alive = True

    def is_alive(self):
        return self._alive

    def stop(self):
        self._alive = False


# ---------------------------------------------------------------------------
# 1. Task creation — never blocks, always starts running
# ---------------------------------------------------------------------------

def test_create_task_step_mode_starts_as_running(monkeypatch, tmp_path):
    """Step-mode tasks must NOT start as awaiting_intervention (the freeze trigger)."""
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    threads_created = []

    class RecordingThread(DummyThread):
        def start(self):
            super().start()
            threads_created.append(self)

    monkeypatch.setattr(server.threading, "Thread", RecordingThread)

    client = server.app.test_client()
    response = client.post(
        "/api/tasks",
        json={"task": "Write hello world", "mode": "step"},
    )

    assert response.status_code == 200
    data = response.get_json()

    # Must return running, never awaiting_intervention
    assert data["status"] == "running", (
        f"Task created with status='{data['status']}' — should be 'running' so the "
        "UI does not show the intervention panel immediately."
    )


def test_create_task_step_mode_launches_background_thread(monkeypatch, tmp_path):
    """A background thread must start right after task creation for step mode."""
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    threads_started = []

    class RecordingThread(DummyThread):
        def start(self):
            super().start()
            threads_started.append(self)

    monkeypatch.setattr(server.threading, "Thread", RecordingThread)

    client = server.app.test_client()
    client.post(
        "/api/tasks",
        json={"task": "Write hello world", "mode": "step"},
    )

    assert len(threads_started) >= 1, (
        "No background thread was started after task creation. "
        "The first LLM step must run in background to avoid freezing."
    )
    assert threads_started[0].started is True


def test_create_task_auto_mode_launches_background_thread(monkeypatch, tmp_path):
    """Auto-mode task creation must also launch a background thread immediately."""
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    threads_started = []

    class RecordingThread(DummyThread):
        def start(self):
            super().start()
            threads_started.append(self)

    monkeypatch.setattr(server.threading, "Thread", RecordingThread)

    client = server.app.test_client()
    client.post(
        "/api/tasks",
        json={"task": "Write hello world", "mode": "auto"},
    )

    assert len(threads_started) >= 1
    assert threads_started[0].started is True


# ---------------------------------------------------------------------------
# 2. Action endpoint — non-blocking, returns immediately
# ---------------------------------------------------------------------------

def test_action_approve_returns_immediately_without_blocking(monkeypatch, tmp_path):
    """
    POST /action must return BEFORE the LLM finishes.
    Simulates a slow LLM by using an event; the HTTP response must arrive
    before the LLM 'completes'.
    """
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    task_id = "task_nonblock"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = _make_full_state(task_id, mode="step", status="awaiting_intervention")
    server.save_task_state(task_id, state)

    llm_started = threading.Event()
    llm_released = threading.Event()

    def slow_run_agent_step(*args, **kwargs):
        llm_started.set()
        llm_released.wait(timeout=10)  # blocks until test releases it
        state = server.load_task_state(task_id)
        return state

    monkeypatch.setattr(server, "run_agent_step_sync", slow_run_agent_step)

    threads_launched = []
    _real_Thread = threading.Thread  # capture before monkeypatching

    class RecordingThread:
        """Wraps a real thread but records that it was started."""
        def __init__(self, target=None, args=(), **kwargs):
            self._inner = _real_Thread(target=target, args=args, daemon=True)
            self.daemon = True
            self.started = False

        def start(self):
            self.started = True
            threads_launched.append(self)
            self._inner.start()

        def is_alive(self):
            return self._inner.is_alive()

    monkeypatch.setattr(server.threading, "Thread", RecordingThread)

    client = server.app.test_client()

    start_ts = time.monotonic()
    response = client.post(
        f"/api/tasks/{task_id}/action",
        json={"action": "approve"},
    )
    elapsed = time.monotonic() - start_ts

    # Release the blocking LLM after response is measured
    llm_released.set()

    assert response.status_code == 200, response.get_json()

    # The response must come back almost immediately — well under 1 second —
    # even though the LLM is still "running" in background.
    assert elapsed < 1.5, (
        f"Action endpoint took {elapsed:.2f}s — it is blocking the HTTP request. "
        "The LLM must run in a background thread."
    )

    data = response.get_json()
    # Immediately returns processando (background work underway)
    assert data["status"] in ("processando", "running", "awaiting_intervention"), (
        f"Unexpected status: {data['status']}"
    )


def test_action_sets_processando_before_llm_runs(monkeypatch, tmp_path):
    """The response status must be 'processando' to signal work is underway."""
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    task_id = "task_proc"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = _make_full_state(task_id, mode="step", status="awaiting_intervention")
    server.save_task_state(task_id, state)

    # Slow LLM that never finishes during the test
    def hanging_llm(*args, **kwargs):
        time.sleep(60)

    monkeypatch.setattr(server, "run_agent_step_sync", hanging_llm)

    class QuickThread(DummyThread):
        def start(self):
            super().start()
            # Don't actually run target — just mark started

    monkeypatch.setattr(server.threading, "Thread", QuickThread)

    client = server.app.test_client()
    response = client.post(
        f"/api/tasks/{task_id}/action",
        json={"action": "approve"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "processando", (
        f"Expected 'processando' but got '{data['status']}'. "
        "The endpoint must persist processando before launching the thread."
    )


# ---------------------------------------------------------------------------
# 3. Duplicate thread guard
# ---------------------------------------------------------------------------

def test_action_duplicate_guard_blocks_second_thread(monkeypatch, tmp_path):
    """
    If a thread is already alive for a task, a second action request must
    NOT start another thread — it should return the current state instead.
    """
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    task_id = "task_dup"
    task_path = tmp_path / task_id
    task_path.mkdir()
    state = _make_full_state(task_id, mode="step", status="awaiting_intervention")
    server.save_task_state(task_id, state)

    # Plant an already-alive thread for this task
    alive_thread = DummyThread()
    alive_thread._alive = True
    server.active_threads[task_id] = alive_thread

    threads_started = []

    def counting_thread_class(target=None, args=()):
        t = DummyThread(target=target, args=args)
        threads_started.append(t)
        return t

    monkeypatch.setattr(server.threading, "Thread", counting_thread_class)

    client = server.app.test_client()
    response = client.post(
        f"/api/tasks/{task_id}/action",
        json={"action": "approve"},
    )

    assert response.status_code == 200
    assert len(threads_started) == 0, (
        f"{len(threads_started)} new thread(s) were started even though one was already alive. "
        "The duplicate guard must block redundant thread creation."
    )


# ---------------------------------------------------------------------------
# 4. Full round-trip: create → status poll shows work started
# ---------------------------------------------------------------------------

def test_create_task_then_poll_shows_work_started(monkeypatch, tmp_path):
    """
    After creating a task the GET endpoint must never return
    awaiting_intervention with the initial improve_prompt proposed_tool
    (which would mean the task is frozen waiting for user approval).
    """
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(server, "active_threads", {})

    class QuickThread(DummyThread):
        def start(self):
            super().start()  # don't actually run anything

    monkeypatch.setattr(server.threading, "Thread", QuickThread)

    client = server.app.test_client()
    create_resp = client.post(
        "/api/tasks",
        json={"task": "Write hello world", "mode": "step"},
    )
    assert create_resp.status_code == 200
    task_id = create_resp.get_json()["task_id"]

    get_resp = client.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 200
    data = get_resp.get_json()

    # The task must be in processando or running — not frozen at awaiting_intervention
    # with just the initial improve_prompt proposed tool (which was the freeze bug).
    assert data["status"] in ("running", "processando"), (
        f"Task polled as '{data['status']}' right after creation — "
        "the UI would show the 'Action Required' panel immediately, reproducing the freeze."
    )
