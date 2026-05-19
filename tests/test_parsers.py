from maria.agent import parse_agent_response
from maria.self_improvement import parse_self_improvement_response

def test_parse_agent_response():
    # 1. Standard write_file
    response = """
    <thought>I need to write a python file to compute factorial.</thought>
    <tool name="write_file">
      <path>math_utils.py</path>
      <content>
def factorial(n):
    if n < 2:
        return 1
    return n * factorial(n - 1)
      </content>
    </tool>
    """
    thought, tool, args = parse_agent_response(response)
    assert thought == "I need to write a python file to compute factorial."
    assert tool == "write_file"
    assert args["path"] == "math_utils.py"
    # Verify that the < and > signs inside the python code are preserved and not mangled by XML parsing
    assert "if n < 2:" in args["content"]
    
    # 2. Run command
    response2 = """
    <thought>Let's run tests</thought>
    <tool name="run_command">
      <command>pytest tests/</command>
    </tool>
    """
    thought, tool, args = parse_agent_response(response2)
    assert thought == "Let's run tests"
    assert tool == "run_command"
    assert args["command"] == "pytest tests/"

    # 3. Finish task
    response3 = """
    <THOUGHT>All tests passed.</THOUGHT>
    <TOOL name="finish_task">
      <summary>Calculator module created.</summary>
    </TOOL>
    """
    thought, tool, args = parse_agent_response(response3)
    assert thought == "All tests passed."
    assert tool == "finish_task"
    assert args["summary"] == "Calculator module created."

    # 4. Closing tag typo / missing closing tag
    response4 = """
    <thought>Let's write a file.</thought>
    <tool name="write_file">
      <path>test_game.py</content>
      <content>print("game")</content>
    </tool>
    """
    thought, tool, args = parse_agent_response(response4)
    assert thought == "Let's write a file."
    assert tool == "write_file"
    assert args["path"] == "test_game.py"
    assert args["content"] == 'print("game")'

def test_parse_self_improvement_response():
    response = """
    <analysis>
    The agent failed to run pytest because it wasn't installed. I need to add a lesson and improve the prompt rules.
    </analysis>
    
    <new_lessons>
      <lesson>
        <title>Pytest Not Installed</title>
        <error>Error: Command 'pytest' not found.</error>
        <resolution>Always execute tests via .venv/bin/pytest or run pip install pytest first.</resolution>
      </lesson>
    </new_lessons>
    
    <improved_system_prompt>
    You are Maria. You must always use TDD.
    </improved_system_prompt>
    """
    analysis, lessons, prompt = parse_self_improvement_response(response)
    assert analysis == "The agent failed to run pytest because it wasn't installed. I need to add a lesson and improve the prompt rules."
    assert len(lessons) == 1
    assert lessons[0]["title"] == "Pytest Not Installed"
    assert lessons[0]["error"] == "Error: Command 'pytest' not found."
    assert lessons[0]["resolution"] == "Always execute tests via .venv/bin/pytest or run pip install pytest first."
    assert prompt == "You are Maria. You must always use TDD."
