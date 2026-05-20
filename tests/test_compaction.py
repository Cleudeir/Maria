import os
from unittest.mock import MagicMock
from maria.agents import parse_compacted_lessons_response, SelfImprovementAgent
from maria.memory import load_system_prompt, load_lessons

def test_parse_compacted_lessons_response():
    response = """
    We have analyzed the lessons. Here is the compacted list:
    <compacted_lessons>
      <lesson>
        <title>Resilient XML Parsing</title>
        <error>Format error: missing thought or closing tags</error>
        <resolution>Always start with a thought block and properly open/close tags.</resolution>
      </lesson>
      <lesson>
        <title>TDD Compliance</title>
        <error>Expected tests to fail, but they passed or missing tests</error>
        <resolution>Implement test files first before starting application code.</resolution>
      </lesson>
    </compacted_lessons>
    """
    lessons = parse_compacted_lessons_response(response)
    assert len(lessons) == 2
    assert lessons[0]["title"] == "Resilient XML Parsing"
    assert lessons[0]["error"] == "Format error: missing thought or closing tags"
    assert lessons[0]["resolution"] == "Always start with a thought block and properly open/close tags."
    
    assert lessons[1]["title"] == "TDD Compliance"
    assert lessons[1]["error"] == "Expected tests to fail, but they passed or missing tests"
    assert lessons[1]["resolution"] == "Implement test files first before starting application code."

def test_compact_lessons_integration(tmpdir, monkeypatch):
    memory_dir = str(tmpdir)
    
    # Create mock files
    prompt_html = """<!DOCTYPE html>
<html>
<body>
    <pre id="system-prompt">Base Prompt Rules.
## DYNAMIC GUIDELINES & LESSONS LEARNED:
- Old Rule 1
- Old Rule 2</pre>
</body>
</html>"""
    
    lessons_html = """<!DOCTYPE html>
<html>
<body>
    <div id="lessons-list">
        <div class="lesson">
            <div class="lesson-title">Old Lesson</div>
            <div class="lesson-resolution">Lesson/Fix: Old Res</div>
        </div>
    </div>
</body>
</html>"""
    
    with open(os.path.join(memory_dir, "system_prompt.html"), "w") as f:
        f.write(prompt_html)
    with open(os.path.join(memory_dir, "lessons.html"), "w") as f:
        f.write(lessons_html)
        
    # Initialize Agent and mock LLM response
    agent = SelfImprovementAgent(memory_dir)
    mock_get_generate = MagicMock(return_value="""
    <compacted_lessons>
      <lesson>
        <title>Merged Rule</title>
        <error>Various path errors</error>
        <resolution>Use relative paths inside workspace.</resolution>
      </lesson>
    </compacted_lessons>
    """)
    monkeypatch.setattr("maria.agents.self_improvement.getGenerate", mock_get_generate)
    
    # Run compaction
    success = agent.compact_lessons([
        {"title": "Path Error 1", "error": "Err 1", "resolution": "Fix 1"},
        {"title": "Path Error 2", "error": "Err 2", "resolution": "Fix 2"}
    ], compaction_threshold=1)
    
    assert success is True
    
    # Verify HTML memory updated
    lessons = load_lessons(memory_dir)
    assert len(lessons) == 1
    assert lessons[0]["title"] == "Merged Rule"
    assert lessons[0]["error"] == "Various path errors"
    assert lessons[0]["resolution"] == "Use relative paths inside workspace."
    
    # Verify System Prompt updated
    prompt = load_system_prompt(memory_dir)
    assert "Base Prompt Rules." in prompt
    assert "Merged Rule" in prompt
    assert "Use relative paths inside workspace." in prompt
    assert "Old Rule 1" not in prompt
