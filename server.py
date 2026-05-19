import os
import sys
import json
import time
import shutil
import threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from bs4 import BeautifulSoup

# Add current directory to path to load maria package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from maria.llm import OllamaClient
from maria.agent import parse_agent_response
from maria.security import is_command_critical
from maria.tools import ToolExecutor
from maria.memory import (
    load_system_prompt,
    load_lessons,
    add_task_history,
    save_system_prompt,
    save_lessons,
)
from maria.self_improvement import SelfImprovementAgent

# Set server environment variable for bypassing security console prompts
os.environ["MARIA_SERVER"] = "1"

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")
OLLAMA_URL = "http://localhost:11434"

os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)

# Thread safety lock for task files
task_locks = {}
# Active background task execution threads
active_threads = {}


def get_task_lock(task_id):
    if task_id not in task_locks:
        task_locks[task_id] = threading.Lock()
    return task_locks[task_id]


def get_task_path(task_id):
    return os.path.join(WORKSPACE_DIR, task_id)


def load_task_state(task_id):
    path = os.path.join(get_task_path(task_id), "task_state.json")
    if not os.path.exists(path):
        return None
    with get_task_lock(task_id):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def save_task_state(task_id, state):
    path = os.path.join(get_task_path(task_id), "task_state.json")
    with get_task_lock(task_id):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


def format_task_prompt(prompt):
    return (
        "Before starting implementation, first read the current project files and create "
        "a clear, step-by-step plan. Only after you have the plan, begin implementing "
        "code. Then follow the plan carefully.\n\n"
        f"Instruction:\n{prompt}"
    )


def build_file_tree(dir_path, base_path):
    tree = []
    try:
        for entry in sorted(os.listdir(dir_path)):
            if entry in (
                "__pycache__",
                ".pytest_cache",
                ".venv",
                ".git",
                "task_state.json",
            ):
                continue
            full_path = os.path.join(dir_path, entry)
            rel_path = os.path.relpath(full_path, base_path)
            is_dir = os.path.isdir(full_path)

            node = {
                "name": entry,
                "path": rel_path,
                "type": "directory" if is_dir else "file",
            }
            if is_dir:
                node["children"] = build_file_tree(full_path, base_path)
            tree.append(node)
    except Exception as e:
        pass
    return tree


# --- Core Task Stepping Execution Logic ---


def run_agent_step_sync(
    task_id, action="approve", modified_tool=None, user_prompt=None
):
    """
    Executes a single step for the agent.
    If action is 'approve' or 'modify', it runs the proposed/modified tool, logs the result,
    sends history to Ollama, and parses the next proposed tool.
    If action is 'inject', it appends the user prompt (intervention instruction) and queries Ollama.
    """
    state = load_task_state(task_id)
    if not state:
        return {"error": "Task not found"}

    if state["status"] not in ("running", "awaiting_intervention", "auto", "processando"):
        if action != "inject":
            return state
        if state["status"] in ("completed", "failed"):
            state["proposed_tool"] = None
            if state.get("mode") == "auto":
                state["status"] = "running"
            else:
                state["status"] = "awaiting_intervention"
            save_task_state(task_id, state)

    if action in ("inject", "approve", "modify"):
        state["status"] = "processando"
        save_task_state(task_id, state)

    workspace_path = get_task_path(task_id)
    executor = ToolExecutor(workspace_path)
    client = OllamaClient(base_url=state.get("ollama_url", OLLAMA_URL))

    messages = state["messages"]
    execution_log = state["execution_log"]
    errors_encountered = state["errors_encountered"]
    step = state["step"]
    max_steps = state["max_steps"]

    # 1. Handle previous tool execution/input injection
    tool_result = None
    applied_action_descr = ""

    if action == "approve" and state.get("proposed_tool"):
        tool_name = state["proposed_tool"]["name"]
        args = state["proposed_tool"]["args"]
        applied_action_descr = f"Approved & Executed: {tool_name} {args}"

        # Execute tool
        tool_result = execute_tool_call(executor, tool_name, args)

    elif action == "modify" and modified_tool:
        tool_name = modified_tool.get("name")
        args = modified_tool.get("args", {})
        applied_action_descr = f"Modified & Executed: {tool_name} {args}"

        # Execute modified tool
        tool_result = execute_tool_call(executor, tool_name, args)

    elif action == "inject" and user_prompt:
        wrapped_prompt = format_task_prompt(user_prompt)
        applied_action_descr = f"User Intervention / Prompt: {user_prompt}"
        # Inject the user instruction directly as a user turn
        messages.append(
            {
                "role": "user",
                "content": f"USER INTERVENTION / INSTRUCTION:\n{wrapped_prompt}",
            }
        )
        execution_log.append(
            {"step": step, "role": "user_intervention", "content": wrapped_prompt}
        )

    # Process tool results if we ran a tool
    if tool_result is not None:
        if tool_result.startswith("Error:"):
            errors_encountered.append(
                {"step": step, "tool": tool_name, "args": args, "error": tool_result}
            )

        # Append assistant turn and tool results to messages
        # Note: we only append assistant response if not already appended
        # In typical flow, we appended assistant message in the previous step after generation.
        # But we need to make sure we don't duplicate. Let's make sure the last message matches
        # state["last_raw_response"] or we append it.
        last_resp = state.get("last_raw_response")
        if last_resp and (not messages or messages[-1]["content"] != last_resp):
            messages.append({"role": "assistant", "content": last_resp})

        messages.append({"role": "user", "content": f"TOOL RESULT:\n{tool_result}"})
        execution_log.append(
            {"step": step, "role": "tool_result", "content": tool_result}
        )

    # Clear proposed tool since it's processed
    state["proposed_tool"] = None

    # Check if max steps exceeded
    if step >= max_steps:
        state["status"] = "failed"
        state["details"] = f"Reached maximum execution steps ({max_steps})."
        save_task_state(task_id, state)
        trigger_self_improvement(task_id, state)
        return state

    # 2. Call LLM for the next turn
    next_step = step + 1
    state["step"] = next_step

    try:
        response_text = client.chat(messages, temperature=0.1)
    except Exception as e:
        err_msg = f"LLM error: {e}"
        errors_encountered.append(
            {"step": next_step, "type": "llm_error", "message": err_msg}
        )
        state["status"] = "failed"
        state["details"] = err_msg
        save_task_state(task_id, state)
        trigger_self_improvement(task_id, state)
        return state

    # Log assistant response
    execution_log.append(
        {"step": next_step, "role": "assistant", "content": response_text}
    )
    state["last_raw_response"] = response_text

    # Parse response
    thought, tool_name, args = parse_agent_response(response_text)

    # Handle response types
    if not tool_name:
        err_msg = "Format error: You must output <thought>...</thought> followed by exactly one <tool name='...'>...</tool>."
        errors_encountered.append(
            {"step": next_step, "type": "format_error", "message": err_msg}
        )
        messages.append({"role": "assistant", "content": response_text})
        messages.append({"role": "user", "content": f"ERROR:\n{err_msg}"})
        execution_log.append(
            {"step": next_step, "role": "tool_result", "content": f"ERROR: {err_msg}"}
        )
        state["status"] = "awaiting_intervention"
        state["proposed_tool"] = {
            "name": "",
            "args": {},
            "thought": thought or "Formatting error detected.",
            "error": err_msg,
        }
    elif tool_name == "finish_task":
        summary = args.get("summary", "Task finished.")
        state["status"] = "completed"
        state["details"] = summary
        state["proposed_tool"] = None
        # Add to message list
        messages.append({"role": "assistant", "content": response_text})
        # Record task history
        try:
            add_task_history(MEMORY_DIR, state["task"], "SUCCESS", summary)
        except Exception as e:
            pass
        save_task_state(task_id, state)
        trigger_self_improvement(task_id, state)
        return state
    else:
        # A valid tool proposed
        state["proposed_tool"] = {"name": tool_name, "args": args, "thought": thought}
        # In non-auto mode, pause for user intervention
        if state.get("mode") != "auto":
            state["status"] = "awaiting_intervention"
        else:
            state["status"] = "running"

    # Save the updated state
    save_task_state(task_id, state)
    return state


def execute_tool_call(executor, name, args):
    if name == "list_dir":
        return executor.list_dir(args.get("path", "."))
    elif name == "read_file":
        return executor.read_file(args.get("path", ""))
    elif name == "write_file":
        return executor.write_file(args.get("path", ""), args.get("content", ""))
    elif name == "run_command":
        return executor.run_command(args.get("command", ""))
    else:
        return f"Error: Tool '{name}' is not supported."


def trigger_self_improvement(task_id, state):
    """Runs self-improvement loop in a background thread"""

    def run_improvement():
        try:
            meta_agent = SelfImprovementAgent(
                MEMORY_DIR, ollama_url=state.get("ollama_url", OLLAMA_URL)
            )
            meta_agent.improve(
                state["task"], state["execution_log"], state["errors_encountered"]
            )
        except Exception as e:
            print(f"Self-improvement failed: {e}")

    thread = threading.Thread(target=run_improvement)
    thread.daemon = True
    thread.start()


# --- Background Task Thread Loop ---


def background_execution_loop(task_id):
    """Loop execution steps in background for auto mode"""
    while True:
        state = load_task_state(task_id)
        if not state or state["status"] != "running":
            break

        if not state.get("proposed_tool"):
            state = run_agent_step_sync(task_id, action="inject", user_prompt=None)
            if not state or state["status"] != "running":
                break

        proposed_tool = state.get("proposed_tool")
        if proposed_tool:
            if proposed_tool.get("name") == "run_command":
                command = proposed_tool.get("args", {}).get("command", "")
                if is_command_critical(command):
                    state["status"] = "awaiting_intervention"
                    save_task_state(task_id, state)
                    break
            state = run_agent_step_sync(task_id, action="approve")

        if not state or state["status"] in ("completed", "failed", "awaiting_intervention"):
            break

        time.sleep(0.5)


# --- Flask API Routes ---


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/socket.io/", defaults={"path": ""})
@app.route("/socket.io/<path:path>")
def socket_io_fallback(path):
    # Socket.IO client requests may hit this app even when Socket.IO is not supported.
    # Return a no-content response so the server does not log repeated 404 errors.
    return "", 204


@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    # Gather statistics
    tasks = []
    try:
        for folder in os.listdir(WORKSPACE_DIR):
            if folder.startswith("task_") and os.path.isdir(
                os.path.join(WORKSPACE_DIR, folder)
            ):
                state = load_task_state(folder)
                if state:
                    tasks.append(
                        {
                            "task_id": state["task_id"],
                            "created_at": state["created_at"],
                            "task": state["task"],
                            "status": state["status"],
                        }
                    )
    except Exception as e:
        pass

    lessons = load_lessons(MEMORY_DIR)

    total = len(tasks)
    success = len([t for t in tasks if t["status"] == "completed"])
    failed = len([t for t in tasks if t["status"] == "failed"])
    running = len(
        [
            t
            for t in tasks
            if t["status"] in ("running", "awaiting_intervention", "processando")
        ]
    )

    return jsonify(
        {
            "stats": {
                "total_tasks": total,
                "success_rate": round(success / total * 100, 1) if total > 0 else 0,
                "completed": success,
                "failed": failed,
                "running": running,
                "lessons_count": len(lessons),
            },
            "tasks": sorted(tasks, key=lambda x: x["created_at"], reverse=True),
        }
    )


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    tasks = []
    try:
        for folder in os.listdir(WORKSPACE_DIR):
            if folder.startswith("task_") and os.path.isdir(
                os.path.join(WORKSPACE_DIR, folder)
            ):
                state = load_task_state(folder)
                if state:
                    tasks.append(state)
                else:
                    # Legacy or running task info html
                    info_path = os.path.join(WORKSPACE_DIR, folder, "task_info.html")
                    task_desc = "Unknown Task"
                    created_time = folder.replace("task_", "")
                    if os.path.exists(info_path):
                        with open(info_path, "r", encoding="utf-8") as f:
                            soup = BeautifulSoup(f.read(), "html.parser")
                            desc_div = soup.find(class_="task-description")
                            if desc_div:
                                task_desc = desc_div.text.strip()
                    tasks.append(
                        {
                            "task_id": folder,
                            "created_at": created_time,
                            "task": task_desc,
                            "status": "legacy",
                            "step": 0,
                            "max_steps": 20,
                        }
                    )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(sorted(tasks, key=lambda x: x.get("created_at", ""), reverse=True))


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.json or {}
    task_prompt = data.get("task")
    if not task_prompt:
        return jsonify({"error": "Task prompt is required"}), 400

    max_steps = int(data.get("max_steps", 20))
    mode = data.get("mode", "step")  # 'step' or 'auto'

    # 1. Create isolated directory
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    task_id = f"task_{timestamp}"
    task_path = get_task_path(task_id)
    os.makedirs(task_path, exist_ok=True)

    # 2. Write legacy task info HTML (keep standard compatibility)
    created_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    info_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Maria - Task Information</title>
</head>
<body>
    <div class="container">
        <h1>Maria Task Info</h1>
        <div class="meta"><strong>Created:</strong> {created_time_str}</div>
        <div class="task-description">{task_prompt}</div>
    </div>
</body>
</html>
"""
    with open(os.path.join(task_path, "task_info.html"), "w", encoding="utf-8") as f:
        f.write(info_html)

    # 3. Load prompt/lessons
    try:
        base_prompt = load_system_prompt(MEMORY_DIR)
    except Exception:
        base_prompt = "You are Maria, an agentic coding assistant. Use TDD."

    lessons = load_lessons(MEMORY_DIR)
    lessons_prompt = ""
    if lessons:
        lessons_prompt = "\n\nCRITICAL: Lessons learned from previous runs to prevent repeating mistakes:\n"
        for i, l in enumerate(lessons, 1):
            lessons_prompt += f"Lesson {i}: {l['title']}\n"
            if l.get("error"):
                lessons_prompt += f"  Previous Error: {l['error']}\n"
            lessons_prompt += f"  Correction/Resolution: {l['resolution']}\n"

    system_message = base_prompt + lessons_prompt

    # 4. Formulate state
    state = {
        "task_id": task_id,
        "task": task_prompt,
        "created_at": created_time_str,
        "mode": mode,
        "status": "running" if mode == "auto" else "awaiting_intervention",
        "step": 0,
        "max_steps": max_steps,
        "ollama_url": OLLAMA_URL,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": format_task_prompt(task_prompt)},
        ],
        "execution_log": [
            {"step": 0, "role": "system", "content": f"Initialized task: {task_prompt}"}
        ],
        "errors_encountered": [],
        "proposed_tool": None,
        "last_raw_response": None,
    }

    save_task_state(task_id, state)

    # 5. Handle initial execution based on mode
    if mode == "auto":
        # Launch background thread
        thread = threading.Thread(target=background_execution_loop, args=(task_id,))
        thread.daemon = True
        thread.start()
        active_threads[task_id] = thread
    else:
        # Step mode: Run first step to generate the first proposed tool call
        state = run_agent_step_sync(task_id, action="inject", user_prompt=None)

    return jsonify(state)


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    state = load_task_state(task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    # Include file tree for workspace pane
    state["file_tree"] = build_file_tree(get_task_path(task_id), get_task_path(task_id))
    return jsonify(state)


@app.route("/api/tasks/<task_id>/action", methods=["POST"])
def post_task_action(task_id):
    data = request.json or {}
    action = data.get("action")  # approve, modify, inject, resume_auto

    state = load_task_state(task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    # Synchronous Step/Intervention execution
    modified_tool = data.get("modified_tool")
    user_prompt = data.get("user_prompt")

    # Temporary run agent step
    state = run_agent_step_sync(
        task_id, action=action, modified_tool=modified_tool, user_prompt=user_prompt
    )

    if (
        action == "inject"
        and state.get("mode") == "auto"
        and state.get("status") == "running"
    ):
        thread = active_threads.get(task_id)
        if not thread or not thread.is_alive():
            thread = threading.Thread(target=background_execution_loop, args=(task_id,))
            thread.daemon = True
            thread.start()
            active_threads[task_id] = thread

    return jsonify(state)


@app.route("/api/tasks/<task_id>/pause", methods=["POST"])
def pause_task(task_id):
    state = load_task_state(task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    if state["status"] == "running":
        state["status"] = "awaiting_intervention"
        save_task_state(task_id, state)

    return jsonify(state)


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    task_path = get_task_path(task_id)
    if not os.path.exists(task_path):
        return jsonify({"error": "Task not found"}), 404

    try:
        shutil.rmtree(task_path)
        # Also clean up memory mapping or thread reference if exists
        if task_id in active_threads:
            del active_threads[task_id]
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to delete task files: {e}"}), 500


# --- Workspace File Manager Routes ---


@app.route("/api/tasks/<task_id>/files/view", methods=["GET"])
def view_task_file(task_id):
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "File path is required"}), 400

    task_path = get_task_path(task_id)
    target_file = os.path.abspath(os.path.join(task_path, path))

    # Security check
    if not target_file.startswith(os.path.abspath(task_path)):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(target_file):
        return jsonify({"error": "File does not exist"}), 404

    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>/files/edit", methods=["POST"])
def edit_task_file(task_id):
    data = request.json or {}
    path = data.get("path")
    content = data.get("content")

    if not path or content is None:
        return jsonify({"error": "File path and content are required"}), 400

    task_path = get_task_path(task_id)
    target_file = os.path.abspath(os.path.join(task_path, path))

    # Security check
    if not target_file.startswith(os.path.abspath(task_path)):
        return jsonify({"error": "Access denied"}), 403

    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- System Memory Management Routes ---


@app.route("/api/memory/prompt", methods=["GET", "POST"])
def manage_system_prompt():
    if request.method == "GET":
        try:
            prompt = load_system_prompt(MEMORY_DIR)
            return jsonify({"prompt": prompt})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        data = request.json or {}
        new_prompt = data.get("prompt")
        if not new_prompt:
            return jsonify({"error": "Prompt cannot be empty"}), 400
        try:
            save_system_prompt(MEMORY_DIR, new_prompt)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/memory/lessons", methods=["GET", "POST"])
def manage_lessons():
    if request.method == "GET":
        try:
            lessons = load_lessons(MEMORY_DIR)
            return jsonify({"lessons": lessons})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        data = request.json or {}
        lessons = data.get("lessons")
        if not isinstance(lessons, list):
            return jsonify({"error": "Lessons list must be a JSON array"}), 400
        try:
            save_lessons(MEMORY_DIR, lessons)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
