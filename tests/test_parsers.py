from maria.agents import parse_agent_response, parse_self_improvement_response
from maria.agents.utils import is_llm_response


def test_parse_agent_response():
    # 1. Standard write_file with JSON format
    response = """
    I need to write a python file to compute factorial.
    {"tool": "write_file", "args": {"path": "math_utils.py", "content": "def factorial(n):\\n    if n < 2:\\n        return 1\\n    return n * factorial(n - 1)"}}
    """
    tool, args = parse_agent_response(response)
    assert tool == "write_file"
    assert args["path"] == "math_utils.py"
    assert "if n < 2:" in args["content"]

    # 1b. Standard write_file in markdown code block
    response_plain = """
    I need to write a python file to compute factorial.
    ```json
    {"tool": "write_file", "args": {"path": "math_utils.py", "content": "def factorial(n):\\n    if n < 2:\\n        return 1\\n    return n * factorial(n - 1)"}}
    ```
    """
    tool, args = parse_agent_response(response_plain)
    assert tool == "write_file"
    assert args["path"] == "math_utils.py"
    assert "if n < 2:" in args["content"]

    # 2. Run command
    response2 = """
    Let's run tests
    {"tool": "run_command", "args": {"command": "pytest tests/"}}
    """
    tool, args = parse_agent_response(response2)
    assert tool == "run_command"
    assert args["command"] == "pytest tests/"

    # 3. Finish task
    response3 = """
    All tests passed.
    {"tool": "finish_task", "args": {"summary": "Calculator module created."}}
    """
    tool, args = parse_agent_response(response3)
    assert tool == "finish_task"
    assert args["summary"] == "Calculator module created."

    # 4. Complex content with special characters
    response4 = """
    Let's write a file.
    {"tool": "write_file", "args": {"path": "test_game.py", "content": "print(\\"game\\")"}}
    """
    tool, args = parse_agent_response(response4)
    assert tool == "write_file"
    assert args["path"] == "test_game.py"

    # 5. finish_task with various arg styles
    response5 = '''
    Step complete.
    {"tool": "finish_task", "args": {"summary": "All tests passed and implementation is done."}}
    '''
    tool, args = parse_agent_response(response5)
    assert tool == "finish_task"
    assert "summary" in args


def test_is_llm_response():
    assert is_llm_response('{"tool": "finish_task", "args": {"summary": "done"}}')
    assert is_llm_response('{"tool": "read_file", "args": {"path": "test.py"}}')
    assert is_llm_response('Here is my tool call:\n{"tool": "list_dir", "args": {"path": "."}}')
    assert not is_llm_response("Just plain text without JSON tool calls.")
    assert not is_llm_response("")
    assert not is_llm_response("I'm thinking about what to do next...")


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
    {"tool": "find_in_files", "args": {"path": "src/", "query": "config"}}
    """
    tool, args = parse_agent_response(response)
    assert tool == "find_in_files"
    assert args["path"] == "src/"
    assert args["query"] == "config"

    # grep_output
    response2 = """
    Let's grep output.
    {"tool": "grep_output", "args": {"query": "game_state"}}
    """
    tool2, args2 = parse_agent_response(response2)
    assert tool2 == "grep_output"
    assert args2["query"] == "game_state"

    # edit_file
    response3 = """
    Let's edit the file.
    {"tool": "edit_file", "args": {"path": "output/test.py", "target": "def old_function():\\n    return True", "replacement": "def new_function():\\n    return False"}}
    """
    tool3, args3 = parse_agent_response(response3)
    assert tool3 == "edit_file"
    assert args3["path"] == "output/test.py"
    assert "old_function" in args3["target"]
    assert "new_function" in args3["replacement"]


def test_parse_agent_response_edge_cases():
    # Response with reasoning before JSON
    response = """
    I need to read the index.html file to understand the structure.
    {"tool": "read_file", "args": {"path": "output/index.html"}}
    """
    tool, args = parse_agent_response(response)
    assert tool == "read_file"
    assert args["path"] == "output/index.html"

    # Response with nested JSON in args
    response2 = '''
    Writing a complex file.
    {"tool": "write_file", "args": {"path": "app.js", "content": "const x = {\\"key\\": \\"value\\"};"}}
    '''
    tool2, args2 = parse_agent_response(response2)
    assert tool2 == "write_file"
    assert args2["path"] == "app.js"

    # Response with no tool call
    response3 = "I'm thinking about the best approach..."
    tool3, args3 = parse_agent_response(response3)
    assert tool3 == ""
    assert args3 == {}
