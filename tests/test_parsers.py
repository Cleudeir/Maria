from maria.agents import parse_agent_response, parse_self_improvement_response


def test_parse_agent_response():
    # 1. Standard write_file
    response = """
    I need to write a python file to compute factorial.
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
    tool, args = parse_agent_response(response)
    assert tool == "write_file"
    assert args["path"] == "math_utils.py"
    # Verify that the < and > signs inside the python code are preserved and not mangled by XML parsing
    assert "if n < 2:" in args["content"]

    # 1b. Standard write_file
    response_plain = """
    I need to write a python file to compute factorial.
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
    tool, args = parse_agent_response(response_plain)
    assert tool == "write_file"
    assert args["path"] == "math_utils.py"
    assert "if n < 2:" in args["content"]

    # 2. Run command
    response2 = """
    Let's run tests
    <tool name="run_command">
      <command>pytest tests/</command>
    </tool>
    """
    tool, args = parse_agent_response(response2)
    assert tool == "run_command"
    assert args["command"] == "pytest tests/"

    # 3. Finish task
    response3 = """
    All tests passed.
    <TOOL name="finish_task">
      <summary>Calculator module created.</summary>
    </TOOL>
    """
    tool, args = parse_agent_response(response3)
    assert tool == "finish_task"
    assert args["summary"] == "Calculator module created."

    # 4. Closing tag typo / missing closing tag
    response4 = """
    Let's write a file.
    <tool name="write_file">
      <path>test_game.py</content>
      <content>print("game")</content>
    </tool>
    """
    tool, args = parse_agent_response(response4)
    assert tool == "write_file"
    assert args["path"] == "test_game.py"
    assert args["content"] == 'print("game")'


def test_is_llm_response():
    from maria.agents import is_llm_response

    assert is_llm_response("<tool name='finish_task'></tool>")
    assert is_llm_response('<tool name="read_file">')
    assert not is_llm_response("Just plain text without XML tags.")
    assert not is_llm_response("")


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
    assert (
        analysis
        == "The agent failed to run pytest because it wasn't installed. I need to add a lesson and improve the prompt rules."
    )
    assert len(lessons) == 1
    assert lessons[0]["title"] == "Pytest Not Installed"
    assert lessons[0]["error"] == "Error: Command 'pytest' not found."
    assert (
        lessons[0]["resolution"]
        == "Always execute tests via .venv/bin/pytest or run pip install pytest first."
    )
    assert prompt == "You are Maria. You must always use TDD."


def test_parse_new_tools():
    # find_in_files
    response = """
    Let's find occurrences of config in workspace.
    <tool name="find_in_files">
      <path>src/</path>
      <query>config</query>
    </tool>
    """
    tool, args = parse_agent_response(response)
    assert tool == "find_in_files"
    assert args["path"] == "src/"
    assert args["query"] == "config"

    # grep_output
    response2 = """
    Let's grep output.
    <tool name="grep_output">
      <query>game_state</query>
    </tool>
    """
    tool2, args2 = parse_agent_response(response2)
    assert tool2 == "grep_output"
    assert args2["query"] == "game_state"

    # edit_file
    response3 = """
    Let's edit the file.
    <tool name="edit_file">
      <path>output/test.py</path>
      <target>
def old_function():
    return True
      </target>
      <replacement>
def new_function():
    return False
      </replacement>
    </tool>
    """
    tool3, args3 = parse_agent_response(response3)
    assert tool3 == "edit_file"
    assert args3["path"] == "output/test.py"
    assert "\ndef old_function():\n    return True\n      " in args3["target"]
    assert "\ndef new_function():\n    return False\n      " in args3["replacement"]


def test_parse_agent_response_self_closing():
    response = """
    I need to read the index.html file.
    <tool name="read_file" path="output/index.html" />
    """
    tool, args = parse_agent_response(response)
    assert tool == "read_file"
    assert args["path"] == "output/index.html"

    # Test with single quotes and extra spacing/no spaces
    response2 = "Check dir <tool name='list_dir' path='.'/>"
    tool2, args2 = parse_agent_response(response2)
    assert tool2 == "list_dir"
    assert args2["path"] == "."
