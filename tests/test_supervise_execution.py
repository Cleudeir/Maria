import time

from maria.agents.supervise_execution import supervise_proposed_tool, supervise_task_result


def test_supervise_proposed_tool_approves_with_reason():
    def fake_get_generate(system_text, user_text):
        return '{"tool": "approve", "args": {"reason": "Aligned with the plan."}}'

    decision = supervise_proposed_tool(
        task="Build a todo app",
        stage="executing_steps",
        plan="Write a todo app with add/remove feature.",
        steps=["Create project structure"],
        current_step_idx=0,
        proposed_tool={"name": "write_file", "args": {"path": "app.py"}},
        completed_summaries=[],
        last_tool_result=None,
        last_user_intervention=None,
        get_generate_fn=fake_get_generate,
    )

    assert decision["action"] == "approve"
    assert decision["reason"] == "Aligned with the plan."


def test_supervise_proposed_tool_pauses_on_invalid_action():
    def fake_get_generate(system_text, user_text):
        return '{"tool": "nonexistent", "args": {}}'

    decision = supervise_proposed_tool(
        task="Build a todo app",
        stage="creating_steps",
        plan="Write a todo app with add/remove feature.",
        steps=[],
        current_step_idx=0,
        proposed_tool={"name": "generate_plan", "args": {}},
        completed_summaries=[],
        last_tool_result=None,
        last_user_intervention=None,
        get_generate_fn=fake_get_generate,
    )

    assert decision["action"] == "pause"
    assert decision["reason"] == "No reason provided."


def test_supervise_proposed_tool_isolates_on_empty_response():
    def fake_get_generate(system_text, user_text):
        return ""

    decision = supervise_proposed_tool(
        task="Build a todo app",
        stage="executing_steps",
        plan="Write a todo app.",
        steps=["Step 1"],
        current_step_idx=0,
        proposed_tool={"name": "write_file", "args": {"path": "app.py"}},
        completed_summaries=[],
        get_generate_fn=fake_get_generate,
    )

    assert decision["action"] == "approve"
    assert "empty response" in decision["reason"].lower()


def test_supervise_proposed_tool_isolates_on_exception():
    def fake_get_generate(system_text, user_text):
        raise RuntimeError("LLM connection failed")

    decision = supervise_proposed_tool(
        task="Build a todo app",
        stage="executing_steps",
        plan="Write a todo app.",
        steps=["Step 1"],
        current_step_idx=0,
        proposed_tool={"name": "write_file", "args": {"path": "app.py"}},
        completed_summaries=[],
        get_generate_fn=fake_get_generate,
    )

    assert decision["action"] == "approve"
    assert "failed to read response" in decision["reason"].lower()


def test_supervise_task_result_isolates_on_empty_response():
    def fake_get_generate(system_text, user_text):
        return ""

    result = supervise_task_result(
        task="Build a todo app",
        plan="Write a todo app.",
        steps=["Step 1", "Step 2"],
        completed_summaries=["Step 1 done"],
        verification_report="All tests passed",
        verdict="SUCCESS",
        get_generate_fn=fake_get_generate,
    )

    assert result["action"] == "review"
    assert "empty response" in result["reason"].lower()


def test_supervise_task_result_isolates_on_exception():
    def fake_get_generate(system_text, user_text):
        raise ConnectionError("LLM service unavailable")

    result = supervise_task_result(
        task="Build a todo app",
        plan="Write a todo app.",
        steps=["Step 1", "Step 2"],
        completed_summaries=["Step 1 done"],
        verification_report="All tests passed",
        verdict="SUCCESS",
        get_generate_fn=fake_get_generate,
    )

    assert result["action"] == "review"
    assert "failed to read response" in result["reason"].lower()
