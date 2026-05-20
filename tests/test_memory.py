import os
from maria.memory import load_system_prompt, save_system_prompt, load_lessons, add_lesson, add_task_history, save_lessons

def test_memory_operations(tmpdir):
    # Set up temporary memory directory
    memory_dir = str(tmpdir)
    
    # 1. Create dummy system_prompt.html
    system_prompt_html = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="meta">Last Updated: Never</div>
    <pre id="system-prompt">Initial Prompt</pre>
</body>
</html>"""
    
    prompt_path = os.path.join(memory_dir, "system_prompt.html")
    with open(prompt_path, "w") as f:
        f.write(system_prompt_html)
        
    # 2. Create dummy lessons.html
    lessons_html = """<!DOCTYPE html>
<html>
<head><title>Lessons</title></head>
<body>
    <div id="lessons-list"></div>
</body>
</html>"""
    lessons_path = os.path.join(memory_dir, "lessons.html")
    with open(lessons_path, "w") as f:
        f.write(lessons_html)
        
    # 3. Create dummy task_history.html
    history_html = """<!DOCTYPE html>
<html>
<head><title>History</title></head>
<body>
    <div id="history-list"></div>
</body>
</html>"""
    history_path = os.path.join(memory_dir, "task_history.html")
    with open(history_path, "w") as f:
        f.write(history_html)
        
    # Test load system prompt
    assert load_system_prompt(memory_dir) == "Initial Prompt"
    
    # Test save system prompt
    save_system_prompt(memory_dir, "New Improved Prompt")
    assert load_system_prompt(memory_dir) == "New Improved Prompt"
    
    # Test add and load lessons
    add_lesson(memory_dir, "Failed Command", "Command 'foo' not found", "Install foo first")
    lessons = load_lessons(memory_dir)
    assert len(lessons) == 1
    assert lessons[0]["title"] == "Failed Command"
    assert lessons[0]["error"] == "Command 'foo' not found"
    assert lessons[0]["resolution"] == "Install foo first"
    
    # Test save_lessons (overwrite lessons list)
    compacted_lessons = [
        {"title": "Rule A", "error": "Err A", "resolution": "Fix A"},
        {"title": "Rule B", "error": "Err B", "resolution": "Fix B"}
    ]
    save_lessons(memory_dir, compacted_lessons)
    lessons = load_lessons(memory_dir)
    assert len(lessons) == 2
    assert lessons[0]["title"] == "Rule A"
    assert lessons[1]["title"] == "Rule B"
    
    # Test add task history (should write without raising exception)
    add_task_history(memory_dir, "Create Calculator", "SUCCESS", "Implemented calculator.py and ran pytest")
    
    # Verify file existence and readability
    assert os.path.exists(history_path)
    with open(history_path, "r") as f:
        content = f.read()
        assert "Create Calculator" in content
        assert "SUCCESS" in content
