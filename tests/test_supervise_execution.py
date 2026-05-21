import time

from maria.agents.supervise_execution import supervise_proposed_tool


def test_supervise_proposed_tool_approves_with_reason():
    def fake_get_generate(system_text, user_text):
        return "<tool name='approve'><reason>Aligned with the plan.</reason></tool>"

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
        return "<tool name='nonexistent'></tool>"

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
