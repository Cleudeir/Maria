import os
from unittest.mock import MagicMock
from maria.agent import MariaAgent

def test_improve_prompt(tmpdir):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    agent = MariaAgent(workspace, memory)
    agent.client.chat = MagicMock(return_value="Improved task instruction.")
    
    improved = agent.improve_prompt("Test task", [])
    assert improved == "Improved task instruction."
    agent.client.chat.assert_called_once()

def test_generate_plan(tmpdir):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    agent = MariaAgent(workspace, memory)
    agent.client.chat = MagicMock(return_value="# My Plan\nStep 1...")
    
    plan = agent.generate_plan("Improved task")
    assert plan == "# My Plan\nStep 1..."

def test_create_steps(tmpdir):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    agent = MariaAgent(workspace, memory)
    agent.client.chat = MagicMock(return_value="1. Create file\n2. Run tests")
    
    steps = agent.create_steps("Plan text")
    assert len(steps) == 2
    assert steps[0] == "Create file"
    assert steps[1] == "Run tests"

def test_verify_execution(tmpdir):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    # Create a test file
    with open(os.path.join(workspace, "test.txt"), "w") as f:
        f.write("hello")
        
    agent = MariaAgent(workspace, memory)
    agent.client.chat = MagicMock(return_value="<analysis>Audited successfully</analysis>\n<verdict>SUCCESS</verdict>")
    
    verdict, analysis = agent.verify_execution("Plan text", ["Create file"])
    assert verdict == "SUCCESS"
    assert analysis == "Audited successfully"

def test_agent_run_pipeline_success(tmpdir):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    # Write empty system prompt to avoid exceptions
    prompt_html = """<!DOCTYPE html><html><body><pre id="system-prompt">Prompt</pre></body></html>"""
    lessons_html = """<!DOCTYPE html><html><body><div id="lessons-list"></div></body></html>"""
    with open(os.path.join(memory, "system_prompt.html"), "w") as f:
        f.write(prompt_html)
    with open(os.path.join(memory, "lessons.html"), "w") as f:
        f.write(lessons_html)

    agent = MariaAgent(workspace, memory)
    
    # Mock stage methods
    agent.improve_prompt = MagicMock(return_value="Improved task")
    agent.generate_plan = MagicMock(return_value="Plan text")
    agent.create_steps = MagicMock(return_value=["Step 1", "Step 2"])
    
    # Mock LLM chat for executing steps
    responses = [
        '<thought>Done step 1</thought><tool name="finish_task"><summary>Summary 1</summary></tool>',
        '<thought>Done step 2</thought><tool name="finish_task"><summary>Summary 2</summary></tool>'
    ]
    agent.client.chat = MagicMock(side_effect=responses)
    
    # Mock verification
    agent.verify_execution = MagicMock(return_value=("SUCCESS", "All clean"))
    
    success = agent.run("Perform some task")
    assert success is True
    assert agent.improve_prompt.called
    assert agent.generate_plan.called
    assert agent.create_steps.called
    assert agent.verify_execution.called
    assert agent.client.chat.call_count == 2
