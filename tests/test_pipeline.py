import os
from unittest.mock import MagicMock, ANY
from maria.agents import MariaAgent
from maria.agents.improve_prompt import improve_prompt as improve_prompt_fn

def test_improve_prompt(tmpdir, monkeypatch):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    agent = MariaAgent(workspace, memory)
    mock_get_generate = MagicMock(return_value="Improved task instruction.")
    monkeypatch.setattr("maria.provider.ollama.OllamaProvider.generate", mock_get_generate)
    
    improved = agent.improve_prompt("Test task", [])
    assert improved == "Improved task instruction."
    mock_get_generate.assert_called_once()

def test_generate_plan(tmpdir, monkeypatch):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    agent = MariaAgent(workspace, memory)
    mock_get_generate = MagicMock(return_value="# My Plan\nStep 1...")
    monkeypatch.setattr("maria.provider.ollama.OllamaProvider.generate", mock_get_generate)
    
    plan = agent.generate_plan("Improved task")
    assert plan == "# My Plan\nStep 1..."

def test_create_steps(tmpdir, monkeypatch):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    agent = MariaAgent(workspace, memory)
    mock_get_generate = MagicMock(return_value="1. Create file\n2. Run tests")
    monkeypatch.setattr("maria.provider.ollama.OllamaProvider.generate", mock_get_generate)
    
    steps = agent.create_steps("Plan text")
    assert len(steps) == 2
    assert steps[0] == "Create file"
    assert steps[1] == "Run tests"

def test_verify_execution(tmpdir, monkeypatch):
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))
    
    # Create a test file
    with open(os.path.join(workspace, "test.txt"), "w") as f:
        f.write("hello")
        
    agent = MariaAgent(workspace, memory)
    mock_get_generate = MagicMock(return_value="<analysis>Audited successfully</analysis>\n<verdict>SUCCESS</verdict>")
    monkeypatch.setattr("maria.provider.ollama.OllamaProvider.generate", mock_get_generate)
    
    verdict, analysis = agent.verify_execution("Plan text", ["Create file"])
    assert verdict == "SUCCESS"
    assert analysis == "Audited successfully"

def test_agent_run_pipeline_success(tmpdir, monkeypatch):
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
    mock_get_generate = MagicMock(side_effect=responses)
    monkeypatch.setattr("maria.provider.ollama.OllamaProvider.generate", mock_get_generate)
    
    # Mock verification
    agent.verify_execution = MagicMock(return_value=("SUCCESS", "All clean"))
    
    success = agent.run("Perform some task")
    assert success is True
    assert agent.improve_prompt.called
    assert agent.generate_plan.called
    assert agent.create_steps.called
    assert agent.verify_execution.called
    assert mock_get_generate.call_count == 2


def test_maria_agent_with_opencode_provider(tmpdir, monkeypatch):
    """Test that MariaAgent works with opencode provider and stream_callback"""
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))

    agent = MariaAgent(workspace, memory, provider_type="opencode")
    assert agent.client.provider.name == "opencode"

    mock_generate = MagicMock(return_value="Improved task with opencode.")
    monkeypatch.setattr(agent.client.provider.__class__, "generate", mock_generate)

    callback_called = []
    def stream_cb(text):
        callback_called.append(text)

    improved = agent.improve_prompt("Test task", [], stream_callback=stream_cb)
    assert improved == "Improved task with opencode."
    mock_generate.assert_called_once()
    _, kwargs = mock_generate.call_args
    assert "system_text" in kwargs
    assert "user_text" in kwargs
    assert kwargs["progress_callback"] is stream_cb


def test_improve_prompt_passes_stream_callback(tmpdir, monkeypatch):
    """Test that improve_prompt module passes stream_callback as progress_callback"""
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))

    callback_holder = {}
    def dummy_generate(system_text=None, user_text="", progress_callback=None):
        callback_holder["cb"] = progress_callback
        return "result"

    def stream_cb(text):
        pass

    result = improve_prompt_fn("Test task", [], get_generate_fn=dummy_generate, stream_callback=stream_cb)
    assert result == "result"
    assert callback_holder["cb"] is stream_cb


def test_improve_prompt_no_stream_callback_does_not_crash(tmpdir, monkeypatch):
    """Test that improve_prompt works even without stream_callback (None default)"""
    workspace = str(tmpdir.mkdir("workspace"))
    memory = str(tmpdir.mkdir("memory"))

    agent = MariaAgent(workspace, memory)

    mock_generate = MagicMock(return_value="Improved task.")
    monkeypatch.setattr(agent.client.provider.__class__, "generate", mock_generate)

    improved = agent.improve_prompt("Test task", [])
    assert improved == "Improved task."
    mock_generate.assert_called_once()
    _, kwargs = mock_generate.call_args
    assert kwargs.get("progress_callback") is None
