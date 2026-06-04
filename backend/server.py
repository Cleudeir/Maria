import os
import sys
import json
import time
import shutil

import threading
import mimetypes
import logging
from datetime import datetime
from flask import (
    Flask,
    request,
    jsonify,
    send_file,
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from bs4 import BeautifulSoup

# Load .env file if present
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

# Add current directory to path to load maria package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from maria.llm import LLMClient as OllamaClient
from maria.provider import PROVIDER_URLS
from maria.agents import parse_agent_response, MariaAgent
from maria.runaway import is_runaway_response, truncate_runaway, has_text_loop, _MAX_RESPONSE_CHARS

from maria.tools import ToolExecutor, terminate_task_process_groups, terminate_task_http_servers, list_http_servers, stop_http_server as stop_http_server_tool
from maria.memory import (
    load_system_prompt,
    load_lessons,
    add_task_history,
    save_system_prompt,
    save_lessons,
)
from maria.self_improvement import SelfImprovementAgent
from maria.readme_generator import ReadmeGenerator
from maria.provider.base import LoopDetectedError, ContextExceededError
from maria.compact_context import compact_messages, estimate_tokens, total_tokens
from maria.step_checkpoint import (
    save_checkpoint,
    load_checkpoint,
    restore_checkpoint_into_state,
    clear_checkpoint,
)
from maria.whatsapp_client import (
    send_admin_text,
    send_admin_ask,
    send_admin_alert,
    is_configured as whatsapp_configured,
)
from maria.webhook_handler import register_pending_ask, resolve_pending_ask, cleanup_stale_asks

MAX_STAGE_RETRIES = 5
MAX_TASK_RETRIES = 5  # max overall retries before giving up
MAX_WHATSAPP_RETRIES = 5  # max retries for auto-whatsapp mode
TASK_RETRY_DELAY = 10  # seconds


def _compact_error_detail(detail: str) -> str:
    """Extract a short (~40 chars) core error tag from verbose error text."""
    if not detail:
        return "unknown"
    for marker in [
        "Context size has been exceeded",
        "exceeds the available context size",
        "context exceeded",
        "context",
    ]:
        if marker.lower() in detail.lower():
            return "context exceeded"
    for marker in ["timeout", "timed out"]:
        if marker.lower() in detail.lower():
            return "timeout"
    for marker in ["rate limit", "429"]:
        if marker.lower() in detail.lower():
            return "rate limited"
    for marker in ["authentication", "api key", "401", "403"]:
        if marker.lower() in detail.lower():
            return "auth error"
    clean = detail.strip().rstrip(".")
    if len(clean) > 60:
        return clean[:57] + "..."
    return clean


# Set server environment variable for bypassing security console prompts
os.environ["MARIA_SERVER"] = "1"

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS"
    return response


@app.before_request
def handle_options_preflight():
    if request.method == "OPTIONS":
        response = app.make_response("")
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS"
        return response


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspace")
MEMORY_DIR = os.path.join(PROJECT_ROOT, "memory")
LLAMACPP_URL = PROVIDER_URLS.get("llamacpp", "http://192.168.20.180:8081/v1/chat/completions")


def get_provider_url(provider_type: str) -> str:
    return PROVIDER_URLS.get(provider_type, LLAMACPP_URL)

os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(MEMORY_DIR, exist_ok=True)

# Thread safety lock for task files
task_locks = {}
# Active background task execution threads
active_threads = {}
# Stop signals for background threads
task_stop_events = {}


def is_task_stopped(task_id):
    event = task_stop_events.get(task_id)
    return event is not None and event.is_set()


def signal_task_stop(task_id):
    event = task_stop_events.get(task_id)
    if event:
        event.set()


def ensure_task_stop_event(task_id):
    if task_id not in task_stop_events:
        task_stop_events[task_id] = threading.Event()
    return task_stop_events[task_id]


# ── WebSocket event handlers ──────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    emit("connected", {"status": "ok"})


@socketio.on("disconnect")
def handle_disconnect():
    pass


@socketio.on("subscribe_task")
def handle_subscribe_task(data):
    task_id = data.get("task_id")
    if task_id:
        join_room(f"task:{task_id}")
        # Send current state immediately
        state = load_task_state(task_id)
        if state:
            state.pop("messages", None)
            state.pop("_recent_tool_calls", None)
            state.pop("failure_history", None)
            state["file_tree"] = build_output_file_tree(get_task_path(task_id))
            state["current_streaming_response"] = state.get("current_streaming_response", "")
            state["is_streaming"] = state.get("is_streaming", False)
            state["current_command_output"] = state.get("current_command_output", "")
            created_files = state.get("created_files", [])
            project_files = state.get("project_files_to_create", [])
            if project_files:
                created_set = {f.get("path") for f in created_files}
                completed = sum(1 for f in project_files if (f.get("path") if isinstance(f, dict) else f) in created_set)
                state["files_progress"] = round(completed / len(project_files) * 100)
            else:
                state["files_progress"] = 100 if created_files else 0
            emit("task_update", state)


@socketio.on("unsubscribe_task")
def handle_unsubscribe_task(data):
    task_id = data.get("task_id")
    if task_id:
        leave_room(f"task:{task_id}")


def emit_task_update(task_id):
    """Broadcast task state change to all subscribers of that task room."""
    state = load_task_state(task_id)
    if not state:
        return
    # Strip heavy fields not needed for live updates
    slim = {
        "task_id": state.get("task_id"),
        "task": state.get("task"),
        "status": state.get("status"),
        "step": state.get("step", 0),
        "stage": state.get("stage"),
        "stage_retries": state.get("stage_retries", 0),
        "created_at": state.get("created_at"),
        "details": state.get("details"),
        "is_streaming": state.get("is_streaming", False),
        "current_streaming_response": state.get("current_streaming_response", ""),
        "current_command_output": state.get("current_command_output", ""),
        "errors_encountered": state.get("errors_encountered", []),
        "proposed_tool": state.get("proposed_tool"),
        "supervision_status": state.get("supervision_status"),
        "execution_log": state.get("execution_log", [])[-50:],
        "created_files": state.get("created_files", []),
        "project_files_to_create": state.get("project_files_to_create", []),
        "files_progress": state.get("files_progress", 0),
    }
    socketio.emit("task_update", slim, room=f"task:{task_id}")


def emit_tasks_list_update():
    """Broadcast a lightweight tasks list update to all connected clients."""
    tasks = []
    try:
        for folder in os.listdir(WORKSPACE_DIR):
            if folder.startswith("task_") and os.path.isdir(os.path.join(WORKSPACE_DIR, folder)):
                state = load_task_state(folder)
                if state:
                    tasks.append({
                        "task_id": state.get("task_id", folder),
                        "task": state.get("task", ""),
                        "status": state.get("status", "unknown"),
                        "step": state.get("step", 0),
                        "created_at": state.get("created_at", ""),
                    })
    except Exception:
        pass
    tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    socketio.emit("tasks_list_update", tasks)


def emit_dashboard_update():
    """Broadcast dashboard stats to all connected clients."""
    tasks = []
    try:
        for folder in os.listdir(WORKSPACE_DIR):
            if folder.startswith("task_") and os.path.isdir(os.path.join(WORKSPACE_DIR, folder)):
                state = load_task_state(folder)
                if state:
                    tasks.append({
                        "task_id": state["task_id"],
                        "created_at": state["created_at"],
                        "task": state["task"],
                        "status": state["status"],
                    })
    except Exception:
        pass
    lessons = load_lessons(MEMORY_DIR)
    total = len(tasks)
    success = len([t for t in tasks if t["status"] == "completed"])
    running = len([t for t in tasks if t["status"] in ("running", "processando")])
    socketio.emit("dashboard_update", {
        "total_tasks": total,
        "success_rate": round(success / total * 100, 1) if total > 0 else 0,
        "completed": success,
        "failed": len([t for t in tasks if t["status"] == "failed"]),
        "running": running,
        "lessons_count": len(lessons),
    })


def _is_whatsapp_mode(state: dict) -> bool:
    if not state:
        return False
    return state.get("mode") == "auto-whatsapp"


def _ask_whatsapp_for_guidance(task_id: str, state: dict, reason: str, ask_type: str = "stuck"):
    if not whatsapp_configured():
        return False
    task_preview = state.get("task", "Unknown task")[:80]
    current_stage = state.get("stage", "unknown")
    failure_count = len(state.get("failure_history", []))
    body = (
        f"Task: {task_preview}\n"
        f"Stage: {current_stage}\n"
        f"Failures: {failure_count}\n\n"
        f"{reason}"
    )
    options = [
        "Continue with same approach",
        "Change approach and retry",
        "Abort task",
    ]
    result = send_admin_ask(
        f"Agent needs guidance: {reason[:50]}",
        options,
        task_id=task_id,
    )
    if result.get("success"):
        ask_id = str(result.get("askId", ""))
        if ask_id:
            register_pending_ask(
                ask_id, task_id, ask_type,
                options, {
                    "reason": reason,
                    "mode": state.get("mode"),
                    "stage": state.get("stage"),
                    "task": state.get("task", "")[:200],
                    "plan": state.get("plan", "")[:500],
                    "step": state.get("step"),
                }
            )
            return True
    return False


def _apply_whatsapp_intervention(task_id: str, state: dict, ask_data: dict, response_index: int):
    ask_type = ask_data.get("ask_type", "")
    options = ask_data.get("options", [])
    choice = options[response_index] if 0 <= response_index < len(options) else str(response_index)
    context = ask_data.get("context", {})

    if ask_type == "stuck":
        if choice == "Continue with same approach":
            reason = context.get("reason", "")
            state["execution_log"].append({
                "step": state.get("step", 0),
                "role": "system",
                "content": f"🔄 WhatsApp: User said continue with same approach: {reason}",
            })
            if state.get("messages"):
                state["messages"].append({
                    "role": "user",
                    "content": f"USER GUIDANCE (via WhatsApp):\nContinue with the same approach. Try again.\nOriginal reason: {reason}",
                })
        elif choice == "Change approach and retry":
            reason = context.get("reason", "")
            state["execution_log"].append({
                "step": state.get("step", 0),
                "role": "system",
                "content": f"🔄 WhatsApp: User said change approach: {reason}",
            })
            if state.get("messages"):
                state["messages"].append({
                    "role": "user",
                    "content": (
                        f"USER GUIDANCE (via WhatsApp):\nChange your approach. The current strategy is not working.\n"
                        f"Original reason: {reason}\n\n"
                        f"Rethink the problem and try a completely different implementation strategy. "
                        f"Do NOT repeat what failed before."
                    ),
                })
        elif choice == "Abort task":
            state["status"] = "failed"
            state["details"] = "Aborted by user via WhatsApp"
            state["proposed_tool"] = None
            state["execution_log"].append({
                "step": state.get("step", 0),
                "role": "system",
                "content": "🛑 Task aborted by user via WhatsApp.",
            })
            save_task_state(task_id, state)
            return

    state["status"] = "running"
    save_task_state(task_id, state)


def get_task_lock(task_id):
    if task_id not in task_locks:
        task_locks[task_id] = threading.Lock()
    return task_locks[task_id]


def get_task_path(task_id):
    return os.path.join(WORKSPACE_DIR, task_id)


def _compact_execution_log(log):
    """Remove repeated verbose error entries from execution_log."""
    if not log:
        return log
    kept = []
    seen = set()
    for entry in log:
        if entry.get("role") == "system":
            content = entry.get("content", "")
            if any(w in content for w in ("Retry ", "failed.", "failures", "PREVIOUS FAILURE")):
                key = content[:80]
                if key in seen:
                    continue
                seen.add(key)
        kept.append(entry)
    if len(kept) > 300:
        kept = kept[-300:]
    return kept


def load_task_state(task_id):
    path = os.path.join(get_task_path(task_id), "task_state.json")
    with get_task_lock(task_id):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                return None
            if "execution_log" in state:
                state["execution_log"] = _compact_execution_log(state["execution_log"])
            return state
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None


def save_task_state(task_id, state):
    if not isinstance(state, dict):
        return
    task_path = get_task_path(task_id)
    if is_task_stopped(task_id):
        return
    os.makedirs(task_path, exist_ok=True)
    path = os.path.join(task_path, "task_state.json")
    with get_task_lock(task_id):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    current_disk_state = json.load(f)
                if isinstance(current_disk_state, dict) and current_disk_state.get("status") in ("completed", "failed"):
                    state["status"] = current_disk_state["status"]
                    if "details" in current_disk_state:
                        state["details"] = current_disk_state["details"]
                    if "proposed_tool" in current_disk_state:
                        state["proposed_tool"] = current_disk_state["proposed_tool"]
            except Exception:
                pass
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            if os.path.exists(tmp_path):
                os.replace(tmp_path, path)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

    # Emit WebSocket update (throttled to max once per 300ms per task)
    _maybe_emit_task_update(task_id)


_emit_throttle: dict = {}

def _maybe_emit_task_update(task_id: str):
    """Emit task update throttled to avoid flooding clients."""
    now = time.time()
    last = _emit_throttle.get(task_id, 0)
    if now - last < 0.3:
        return
    _emit_throttle[task_id] = now
    try:
        emit_task_update(task_id)
        emit_tasks_list_update()
    except Exception:
        pass


def format_task_prompt(prompt):
    return (
        "Before starting implementation, first read the current project files and create "
        "a clear, step-by-step plan. The plan should explain and describe the approach only; "
        "it must not include code snippets, pseudocode, or exact implementation text. "
        "Only after you have the plan, begin implementing code. Then follow the plan carefully.\n\n"
        f"Instruction:\n{prompt}"
    )


def get_plan_dir(task_path):
    return os.path.join(task_path, "plan")


def get_logs_dir(task_path):
    return os.path.join(task_path, "logs")


def ensure_task_plan_dirs(task_path):
    plan_dir = get_plan_dir(task_path)
    logs_dir = get_logs_dir(task_path)
    os.makedirs(plan_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    return plan_dir, logs_dir


def save_plan_overview(task_path, task_prompt, created_time_str):
    plan_dir, _ = ensure_task_plan_dirs(task_path)
    plan_md_path = os.path.join(plan_dir, "plan.md")
    with open(plan_md_path, "w", encoding="utf-8") as f:
        f.write("# Task Plan\n\n")
        f.write(f"Created: {created_time_str}\n\n")
        f.write("## Task\n\n")
        f.write(f"{task_prompt}\n\n")
        f.write("## Notes\n\n")
        f.write(
            "- Initial task created. The agent should create a step-by-step plan and implement it incrementally while minimizing context sent to the LLM.\n"
        )
    return plan_md_path


def save_step_summary(task_path, step, summary):
    _, logs_dir = ensure_task_plan_dirs(task_path)
    step_path = os.path.join(logs_dir, f"step_{step:03d}.md")
    with open(step_path, "w", encoding="utf-8") as f:
        f.write(f"# Step {step}\n\n")
        f.write(summary)
        if not summary.endswith("\n"):
            f.write("\n")
    return step_path


def save_execution_plan_steps(task_path, steps):
    plan_dir, _ = ensure_task_plan_dirs(task_path)
    execution_steps_path = os.path.join(plan_dir, "execution_plan_steps.md")
    with open(execution_steps_path, "w", encoding="utf-8") as f:
        f.write("# Execution Plan Steps\n\n")
        for idx, step in enumerate(steps, 1):
            f.write(f"{idx}. {step}\n")
    return execution_steps_path


def build_step_prompt(state):
    task_prompt = state.get("task", "")
    complexity = state.get("complexity", "complex")
    prompt_lines = [
        "Use only the minimum context required for this step. Do not resend the entire conversation history.",
        "You are an agentic assistant executing a single step at a time.",
        "You should output your reasoning and the next tool action in JSON format.",
        "\n",
        "Task:\n" + task_prompt,
        f"\nCurrent step: {state.get('step', 0) + 1}.\n",
    ]
    if complexity != "simple":
        prompt_lines.append(
            "ORGANIZATION: Split code into separate files by domain/responsibility. "
            "Each file should contain related functions with a single purpose. "
            "Each function must have one clear responsibility."
        )
    else:
        prompt_lines.append(
            "Keep everything in a single file unless the task explicitly requires multiple files. "
            "Do NOT over-engineer or create unnecessary files."
        )

    if state.get("step_summaries"):
        prompt_lines.append("Previously completed step summaries:")
        for i, summary in enumerate(state.get("step_summaries", []), 1):
            prompt_lines.append(f"{i}. {summary}")
        prompt_lines.append("\n")

    last_tool_result = state.get("last_tool_result")
    if last_tool_result:
        prompt_lines.append("Last tool result:")
        prompt_lines.append(last_tool_result)
        prompt_lines.append("\n")

    last_user_intervention = state.get("last_user_intervention")
    if last_user_intervention:
        prompt_lines.append("User intervention instruction:")
        prompt_lines.append(last_user_intervention)
        prompt_lines.append("\n")

    prompt_lines.extend(
        [
            "Respond with your reasoning followed by exactly one tool call using the format below:",
            '{"tool": "tool_name", "args": {}}',
            'If the step is done, use {"tool": "finish_task", "args": {"summary": "..."}}.',
        ]
    )

    return "\n".join(prompt_lines)


def build_file_tree(dir_path, base_path, current_depth=0, max_depth=5):
    if current_depth > max_depth:
        return []
    tree = []
    try:
        for entry in sorted(os.listdir(dir_path)):
            if entry in (
                "__pycache__",
                ".pytest_cache",
                ".venv",
                ".git",
                "task_state.json",
                "node_modules",
                ".next",
                "dist",
                "build",
                ".idea",
                ".vscode",
                ".sass-cache",
                ".mypy_cache",
                ".cache",
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
                node["children"] = build_file_tree(
                    full_path, base_path, current_depth + 1, max_depth
                )
            tree.append(node)
    except Exception:
        pass
    return tree


def build_output_file_tree(task_path):
    output_dir = os.path.join(task_path, "output")
    if not os.path.exists(output_dir):
        return [
            {
                "name": "output",
                "path": "output",
                "type": "directory",
                "children": [],
            }
        ]

    return [
        {
            "name": "output",
            "path": "output",
            "type": "directory",
            "children": build_file_tree(output_dir, task_path),
        }
    ]


# --- Command Error Analysis ---


def analyze_command_error(tool_name, args, tool_result):
    """Analyze command output and return generic, actionable advice."""
    output_lower = tool_result.lower()
    advice = "\n\nADVICE: The tool execution failed."

    # 1. Command not found (exit code 127) - universal
    if "exited with code 127" in tool_result:
        advice = (
            "\n\nADVICE: The command was not found (exit code 127). "
            "The executable is not installed or not in PATH.\n"
            "SOLUTIONS:\n"
            "1. Install the required tool/dependency first\n"
            "2. Use npx for node packages (e.g., 'npx <cmd>' instead of '<cmd>')\n"
            "3. Check if the command name is spelled correctly\n"
            "Do NOT retry the same command - it will fail again. Fix the issue first."
        )

    # 2. Permission errors (generic pattern)
    elif any(kw in output_lower for kw in ["permission denied", "eacces", "eperm", "access denied", "not authorized"]):
        advice = (
            "\n\nADVICE: A permission error occurred.\n"
            "SOLUTIONS:\n"
            "1. The process lacks the required permissions to access a file or resource\n"
            "2. Check file ownership and permissions with: ls -la\n"
            "3. Try removing lock files or cache directories that may be owned by another user\n"
            "4. If a directory exists with wrong permissions, delete and recreate it\n"
            "Do NOT retry the same command without fixing the permission issue first."
        )

    # 3. Missing files or modules (generic patterns)
    elif any(kw in output_lower for kw in [
        "enoent", "no such file", "not found", "cannot find", "does not exist",
        "module not found", "cannot resolve", "unable to resolve", "no module named",
        "modulenotfounderror", "import error", "importerror"
    ]):
        advice = (
            "\n\nADVICE: A required file, module, or dependency was not found.\n"
            "SOLUTIONS:\n"
            "1. Check if the file or module path is correct\n"
            "2. List the directory to find what's actually available: list_dir\n"
            "3. Install missing dependencies if needed\n"
            "4. Create the missing file if it should exist\n"
            "5. For import errors, check that the module is installed and imported correctly\n"
            "Do NOT retry the same command - investigate what's missing and fix it first."
        )

    # 4. Network/connectivity errors
    elif any(kw in output_lower for kw in [
        "network", "connect", "socket", "timeout", "timed out", "econnrefused",
        "econnreset", "enetunreach", "getaddrinfo", "dns", "request failed",
        "fetch failed", "unable to connect"
    ]):
        advice = (
            "\n\nADVICE: A network or connectivity error occurred.\n"
            "SOLUTIONS:\n"
            "1. The operation failed due to a network issue\n"
            "2. Check if the required server/service is reachable\n"
            "3. Try the operation again - it may be a transient issue\n"
            "4. If the server URL is misconfigured, fix the URL first\n"
            "If the error is transient, retrying may work. Otherwise, fix the configuration."
        )

    # 5. Compilation/build errors
    elif any(kw in output_lower for kw in [
        "compilation error", "failed to compile", "build error", "build failed",
        "syntax error", "syntaxerror", "parse error", "unexpected token",
        "cannot compile", "error compiling", "compilation failed"
    ]):
        advice = (
            "\n\nADVICE: A compilation or syntax error occurred in the source code.\n"
            "SOLUTIONS:\n"
            "1. Read the error output to identify which file and line has the issue\n"
            "2. Fix the code using write_file or edit_file\n"
            "3. Check for syntax errors, missing imports, or type mismatches\n"
            "4. Do NOT retry the build command - fix the code first, then rebuild."
        )

    # 6. Dependency conflicts
    elif any(kw in output_lower for kw in [
        "conflict", "eresolve", "peer dep", "dependency", "incompatible",
        "version conflict", "circular dependency"
    ]):
        advice = (
            "\n\nADVICE: A dependency conflict was detected.\n"
            "SOLUTIONS:\n"
            "1. Read the dependency conflict details in the output\n"
            "2. Try using compatible versions or force flags (e.g., --legacy-peer-deps, --force)\n"
            "3. Check if dependencies in package.json/requirements.txt are compatible\n"
            "4. Do NOT retry the same command without addressing the conflict."
        )

    # 7. Test failures (detected by common test output patterns)
    elif any(kw in output_lower for kw in [
        "tests failed", "test failed", "failed tests", "assertion error",
        "assertionerror", "expect(", "expected", "assertion failed",
        "test suite failed", "failing", "✗", "✕"
    ]):
        advice = (
            "\n\nADVICE: Tests or assertions failed.\n"
            "SOLUTIONS:\n"
            "1. Read the test output to understand what assertion failed and why\n"
            "2. Fix the source code to make the test pass using write_file or edit_file\n"
            "3. If tests reference files that don't exist, create them first\n"
            "4. Do NOT retry the same test command - fix the code first, then re-run tests."
        )

    # 8. Port/already in use errors
    elif any(kw in output_lower for kw in [
        "address already in use", "port already in use", "eaddrinuse",
        "bind", "already running", "port is taken"
    ]):
        advice = (
            "\n\nADVICE: A port or resource is already in use.\n"
            "SOLUTIONS:\n"
            "1. Another process is using the required port\n"
            "2. Use a different port number\n"
            "3. Or kill the existing process: fuser -k <port>/tcp\n"
            "4. Do NOT retry the same command - choose a different port or free the current one."
        )

    # 9. Out of memory/disk space
    elif any(kw in output_lower for kw in [
        "out of memory", "oom", "memory allocation", "no space left",
        "disk full", "no space", "cannot allocate memory"
    ]):
        advice = (
            "\n\nADVICE: The system ran out of memory or disk space.\n"
            "SOLUTIONS:\n"
            "1. Free up disk space or reduce memory usage\n"
            "2. Delete temporary files: rm -rf /tmp/* 2>/dev/null\n"
            "3. Try a more efficient approach that uses fewer resources\n"
            "4. Do NOT retry the same command - it will likely fail again."
        )

    else:
        advice = (
            "\n\nADVICE: The command failed with a non-zero exit code.\n"
            "Read the error output above carefully to understand what went wrong.\n"
            "GENERAL APPROACH:\n"
            "1. Identify the error type from the output\n"
            "2. If code needs fixing, use write_file or edit_file\n"
            "3. If dependencies are missing, install them\n"
            "4. If configuration is wrong, correct it\n"
            "5. Do NOT retry the same command - it will fail again. Fix the issue first."
        )

    return advice


# --- Core Task Stepping Execution Logic ---


def run_agent_step_sync(
    task_id, action="approve", modified_tool=None, user_prompt=None
):
    """
    Executes a single step for the agent in the multi-stage flow.
    """
    state = load_task_state(task_id)
    if not state:
        return {"error": "Task not found"}

    if "stage" not in state:
        state["stage"] = "generating_plan"
        state["plan"] = None
        state["steps"] = []
        state["current_step_idx"] = 0
        state["completed_step_summaries"] = []

    if "step_summaries" not in state:
        state["step_summaries"] = []
    if "last_tool_result" not in state:
        state["last_tool_result"] = None
    if "last_user_intervention" not in state:
        state["last_user_intervention"] = None
    if "stage_retries" not in state:
        state["stage_retries"] = 0

    if "created_files" not in state:
        state["created_files"] = []

    if state["status"] not in (
        "running",
        "processando",
    ):
        if action != "inject":
            return state
        if state["status"] in ("completed", "failed"):
            # Preserve created_files across re-initializations
            preserved_created_files = state.get("created_files", [])
            
            state["proposed_tool"] = {
                "name": "generate_plan",
                "args": {},
            }
            state["stage"] = "generating_plan"
            state["step"] = 0
            state["plan"] = None
            state["steps"] = []
            state["current_step_idx"] = 0
            state["completed_step_summaries"] = []
            state["messages"] = []
            state["last_raw_response"] = None
            state["last_tool_result"] = None
            state["last_user_intervention"] = user_prompt
            state["current_streaming_response"] = ""
            state["is_streaming"] = False
            state["errors_encountered"] = []
            state["details"] = None
            state["created_files"] = preserved_created_files
            state["project_structure"] = None
            state["project_files_to_create"] = []
            if user_prompt:
                state["task"] = user_prompt
            state["provider_type"] = "llamacpp"
            state["llamacpp_url"] = get_provider_url("llamacpp")
            state["execution_log"].append(
                {
                    "step": 0,
                    "role": "system",
                    "content": f"🔄 Task re-initialized with new prompt: {user_prompt or state['task']}",
                }
            )
            state["status"] = "running"
            save_task_state(task_id, state)
            return state

    if action in ("inject", "approve", "modify"):
        state["status"] = "processando"
        save_task_state(task_id, state)

    workspace_path = get_task_path(task_id)

    _last_output_save = [0.0]

    def _command_output_callback(line):
        state["current_command_output"] += line + "\n"
        now = time.time()
        if now - _last_output_save[0] > 0.3:
            _last_output_save[0] = now
            save_task_state(task_id, state)

    executor = ToolExecutor(workspace_path, task_id=task_id, output_callback=_command_output_callback)
    client = OllamaClient(
        base_url=state.get("llamacpp_url", LLAMACPP_URL),
        provider_type=state.get("provider_type", "llamacpp"),
        model_think=state.get("model_think", False),
    )

    agent = MariaAgent(
        workspace_path,
        MEMORY_DIR,
        base_url=state.get("llamacpp_url", LLAMACPP_URL),
        provider_type=state.get("provider_type", "llamacpp"),
        model_think=state.get("model_think", False),
    )

    def _start_streaming():
        state["current_streaming_response"] = ""
        state["is_streaming"] = True
        save_task_state(task_id, state)

        def _callback(latest_text):
            state["current_streaming_response"] = latest_text
            save_task_state(task_id, state)

        return _callback

    def _stop_streaming():
        state["is_streaming"] = False
        save_task_state(task_id, state)

    # Load memories
    try:
        base_prompt = load_system_prompt(MEMORY_DIR)
    except Exception:
        base_prompt = "You are Maria, an agentic coding assistant."

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

    # Handle user intervention injection
    if action == "inject" and user_prompt:
        state["execution_log"].append(
            {"step": state["step"], "role": "user_intervention", "content": user_prompt}
        )
        state["last_user_intervention"] = user_prompt
        if state.get("messages"):
            state["messages"].append(
                {
                    "role": "user",
                    "content": f"USER INTERVENTION / INSTRUCTION:\n{user_prompt}",
                }
            )

    # State Machine
    if state["stage"] == "generating_plan":
        try:
            callback = _start_streaming()
            try:
                task_text = state["task"]
                if state.get("last_user_intervention"):
                    task_text += f"\n\nAdditional instructions: {state['last_user_intervention']}"
                plan = agent.generate_plan(
                    task_text, stream_callback=callback, complexity=state.get("complexity", "complex")
                )
            finally:
                _stop_streaming()
            state["plan"] = plan
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"📋 Stage 1 Complete: Complete Plan:\n{plan}",
                }
            )

            # Save plan.md for compatibility
            try:
                plan_dir, _ = ensure_task_plan_dirs(workspace_path)
                with open(
                    os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8"
                ) as f:
                    f.write(plan)
            except Exception:
                pass

            # Transition to generating project structure
            state["stage"] = "generating_structure"
            state["stage_retries"] = 0
            state["proposed_tool"] = {
                "name": "generate_structure",
                "args": {},
            }
            state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, task_id, state)
        except LoopDetectedError as e:
            state["stage_retries"] += 1
            if state["stage_retries"] >= MAX_STAGE_RETRIES:
                state["status"] = "failed"
                state["proposed_tool"] = None
                state["details"] = f"Failed to create steps: {e}"
            else:
                state["details"] = (
                    f"Retry {state['stage_retries']}/{MAX_STAGE_RETRIES} - {e}"
                )
                state["status"] = "running"
                # After first retry, force fewer steps
                if state["stage_retries"] >= 1:
                    state["last_user_intervention"] = (
                        f"⚠️ Você já tentou criar etapas {state['stage_retries']} vezes.\n"
                        f"Crie no máximo 2-3 etapas. Seja agressivo em simplificar.\n"
                        f"Exemplo: 1) Criar arquivo único com tudo; 2) Testar e corrigir; 3) Finalizar."
                    )
            print(
                f"[Stage] creating_steps loop detected for {task_id}: retry {state['stage_retries']}/{MAX_STAGE_RETRIES}",
                flush=True,
            )
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to create steps: {e}"
            print(f"[Stage] creating_steps failed for {task_id}: {e}", flush=True)

    elif state["stage"] == "generating_structure":
        try:
            callback = _start_streaming()
            try:
                project_structure = agent.generate_structure(
                    state["plan"], stream_callback=callback, complexity=state.get("complexity", "complex")
                )
            finally:
                _stop_streaming()
            state["project_structure"] = project_structure
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"📁 Project Structure:\n{project_structure}",
                }
            )
            state["project_files_to_create"] = parse_project_structure_to_files(project_structure)

            # Transition to regenerating plan with structure paths
            state["stage"] = "regenerating_plan"
            state["stage_retries"] = 0
            state["proposed_tool"] = {"name": "regenerate_plan", "args": {}}
            state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, task_id, state)
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to generate structure: {e}"
            print(f"[Stage] generate_structure failed for {task_id}: {e}", flush=True)

    elif state["stage"] == "regenerating_plan":
        try:
            callback = _start_streaming()
            try:
                updated_plan = agent.regenerate_plan(
                    state["plan"],
                    state["project_structure"],
                    stream_callback=callback,
                )
            finally:
                _stop_streaming()
            state["plan"] = updated_plan
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"📋 Plan Updated with Structure Paths:\n{updated_plan}",
                }
            )
            # Save updated plan
            try:
                plan_dir, _ = ensure_task_plan_dirs(workspace_path)
                with open(
                    os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8"
                ) as f:
                    f.write(updated_plan)
            except Exception:
                pass

            # Transition to creating steps
            state["stage"] = "creating_steps"
            state["stage_retries"] = 0
            state["proposed_tool"] = {"name": "create_steps", "args": {}}
            state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, task_id, state)
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to regenerate plan: {e}"
            print(f"[Stage] regenerating_plan failed for {task_id}: {e}", flush=True)

    elif state["stage"] == "creating_steps":
        try:
            callback = _start_streaming()
            try:
                steps = agent.create_steps(
                    state["plan"],
                    stream_callback=callback,
                    complexity=state.get("complexity", "complex"),
                )
            finally:
                _stop_streaming()
            state["steps"] = steps
            steps_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"🛠️ Stage 2 Complete: Execution Steps:\n{steps_str}",
                }
            )

            # Save execution_plan_steps.md for compatibility
            try:
                plan_dir, _ = ensure_task_plan_dirs(workspace_path)
                with open(
                    os.path.join(plan_dir, "execution_plan_steps.md"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write("# Execution Plan Steps\n\n")
                    for i, s in enumerate(steps, 1):
                        f.write(f"{i}. {s}\n")
            except Exception:
                pass

            # Transition to executing steps
            state["stage"] = "executing_steps"
            state["current_step_idx"] = 0
            state["proposed_tool"] = {
                "name": "execute_step",
                "args": {
                    "step_num": 1,
                    "description": steps[0] if steps else "",
                },
            }
            state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, task_id, state)
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to create steps: {e}"
            print(f"[Stage] creating_steps failed for {task_id}: {e}", flush=True)

    elif state["stage"] == "executing_steps":
        steps = state["steps"]
        curr_idx = state["current_step_idx"]
        step_num = curr_idx + 1
        total_steps = len(steps)
        last_proposed = state.get("proposed_tool")
        parallel_groups = state.get("parallel_groups", [[i] for i in range(len(steps))])

        # Find which group the current step belongs to
        current_group = None
        for group in parallel_groups:
            if curr_idx in group:
                current_group = group
                break

        # If initializing step
        if not state.get("messages") or (
            last_proposed
            and last_proposed.get("name") == "execute_step"
            and action == "approve"
        ):
            # Check if this is a parallel group with multiple steps
            if current_group and len(current_group) > 1:
                # Run parallel group
                completed_context = ""
                if state["completed_step_summaries"]:
                    completed_context = "\nPreviously completed steps:\n"
                    for idx, summary in enumerate(state["completed_step_summaries"], 1):
                        completed_context += f"Step {idx}: {summary}\n"

                state["execution_log"].append(
                    {
                        "step": state["step"],
                        "role": "system",
                        "content": f"🔀 Running parallel group: steps {[i+1 for i in current_group]}",
                    }
                )

                from maria.agents.parallel_executor import run_parallel_group
                parallel_results = run_parallel_group(
                    group=current_group,
                    steps=steps,
                    plan=state["plan"],
                    completed_context=completed_context,
                    system_message=system_message,
                    workspace_path=workspace_path,
                    primary_provider=state.get("provider_type", "llamacpp"),
                    model_think=state.get("model_think", False),
                    complexity=state.get("complexity", "complex"),
                    project_structure=state.get("project_structure", ""),
                )

                # Process results
                for step_idx, success, summary in parallel_results:
                    step_desc = steps[step_idx]
                    state["completed_step_summaries"].append(f"{step_desc} -> {summary}")
                    state["execution_log"].append(
                        {
                            "step": state["step"],
                            "role": "system",
                            "content": f"✅ Step {step_idx+1} Complete: {summary}",
                        }
                    )

                # Find next step after this group
                next_idx = max(current_group) + 1
                if next_idx < len(steps):
                    state["current_step_idx"] = next_idx
                    state["messages"] = []
                    state["proposed_tool"] = {
                        "name": "execute_step",
                        "args": {"step_num": next_idx + 1, "description": steps[next_idx]},
                    }
                else:
                    planned = state.get("project_files_to_create", [])
                    created = state.get("created_files", [])
                    created_set = {f.get("path", "") for f in created}
                    missing = [f for f in planned if f.get("path", "") not in created_set]

                    if missing:
                        missing_file_attempts = state.get("_missing_file_attempts", 0) + 1
                        state["_missing_file_attempts"] = missing_file_attempts

                        if missing_file_attempts > 2:
                            state["stage"] = "completed"
                            state["status"] = "completed"
                            state["details"] = f"Parallel steps executed. {len(missing)} planned file(s) not created after {missing_file_attempts} attempts - completing anyway."
                            state["proposed_tool"] = None
                            state["messages"] = []
                            state["execution_log"].append({
                                "step": state["step"],
                                "role": "system",
                                "content": f"⚠️ {len(missing)} file(s) not created after {missing_file_attempts} attempts. Task completed anyway.",
                            })
                            try:
                                add_task_history(
                                    MEMORY_DIR, state["task"], "SUCCESS",
                                    state["details"]
                                )
                            except Exception:
                                pass
                            if state.get("errors_encountered"):
                                trigger_self_improvement(task_id, state)
                            trigger_readme_generation(task_id, state)
                        else:
                            missing_paths = [f.get("path") for f in missing]
                            file_list = "\n".join(f"- {p}" for p in missing_paths)
                            step_desc = (
                                f"Create files still missing from the project structure:\n{file_list}\n\n"
                                "Forneça conteúdo completo para cada arquivo. Não é necessário recriar arquivos já existentes."
                            )
                            state["project_structure"] = json.dumps(missing_paths)
                            state["project_files_to_create"] = missing
                            state["steps"].append(step_desc)
                            state["current_step_idx"] = len(state["steps"]) - 1
                            state["proposed_tool"] = {
                                "name": "execute_step",
                                "args": {
                                    "step_num": len(state["steps"]),
                                    "description": step_desc,
                                },
                            }
                            state["status"] = "running"
                            state["execution_log"].append({
                                "step": state["step"],
                                "role": "system",
                                "content": f"📋 {len(missing)} arquivo(s) planejado(s) ainda não foram criados. Nova etapa adicionada para criá-los.",
                            })
                    else:
                        state["stage"] = "completed"
                        state["status"] = "completed"
                        state["details"] = "All steps executed successfully."
                        state["proposed_tool"] = None
                        state["messages"] = []
                        try:
                            add_task_history(
                                MEMORY_DIR, state["task"], "SUCCESS",
                                "All steps executed successfully."
                            )
                        except Exception:
                            pass
                        if state.get("errors_encountered"):
                            trigger_self_improvement(task_id, state)
                        trigger_readme_generation(task_id, state)

                save_checkpoint(WORKSPACE_DIR, task_id, state)

            else:
                # Sequential execution (single step)
                completed_context = ""
                if state["completed_step_summaries"]:
                    completed_context = "\nPreviously completed steps:\n"
                    for idx, summary in enumerate(state["completed_step_summaries"], 1):
                        completed_context += f"Step {idx}: {summary}\n"

                # Inject created files context
                created_files_context = ""
                created_files = state.get("created_files", [])
                if created_files:
                    created_files_context = "\nCRITICAL: Files already created in this workspace:\n"
                    for entry in created_files:
                        path = entry.get("path", "")
                        created_at = entry.get("created_at", "")
                        step = entry.get("step", "")
                        step_info = f" (step {step})" if step else ""
                        created_files_context += f"- {path}{step_info}\n"
                    created_files_context += "\nIMPORTANT: Use list_dir and read_file to inspect existing files before creating new ones. Do NOT recreate files that already exist unless explicitly required.\n"

                # Inject project structure overview
                project_structure_context = ""
                project_structure = state.get("project_structure")
                if project_structure:
                    project_structure_context = "\nPROJECT STRUCTURE OVERVIEW (files to be created):\n"
                    project_structure_context += project_structure + "\n"
                    project_structure_context += "CRITICAL: When calling write_file, you MUST use the EXACT paths shown above (e.g. 'src/entity_factory.py' NOT just 'entity_factory.py'). The paths include directory prefixes like 'src/' or 'tests/'. Using wrong paths will place files in the wrong location.\n"

                state["messages"] = [
                    {"role": "system", "content": system_message},
                    {
                        "role": "user",
                        "content": f"""We are executing a multi-stage plan.
Complete Plan:
{state["plan"]}
{completed_context}{created_files_context}{project_structure_context}
Current Step: Step {step_num} of {total_steps}
Step Description: {steps[curr_idx]}

{"Do exactly what is asked. Do NOT over-engineer. Do NOT create extra files or architecture." if state.get("complexity") == "simple" else "ORGANIZATION RULE:\n- Split code into separate files by domain/responsibility\n- Each file should contain related functions with a single purpose\n- Each function must have one clear responsibility"}

IMPORTANT: 'write_file' automatically creates parent directories. You do NOT need to create directories first - just write files directly.

Your objective is to complete ONLY this step using your tools.
When you believe this step is fully complete, call the 'finish_task' tool with a summary of what you did.

CRITICAL: Do not ask the user for input, next steps, feedback, or choices. Do not ask "What would you like to do next?". You must execute the entire step autonomously. Once the code is written, immediately call the 'finish_task' tool to proceed to the next step.
""",
                    },
                ]
                state["execution_log"].append(
                    {
                        "step": state["step"],
                        "role": "system",
                        "content": f"🎬 Starting Step {step_num}/{total_steps}: {steps[curr_idx]}",
                    }
                )
                state["last_tool_result"] = None
                pending_intervention = state.get("last_user_intervention")
                if pending_intervention and pending_intervention not in str(state.get("messages", [])):
                    state["messages"].append(
                        {
                            "role": "user",
                            "content": f"USER INTERVENTION / INSTRUCTION:\n{pending_intervention}",
                        }
                    )
                state["last_user_intervention"] = None
                state["_recent_tool_calls"] = []
                state["step"] = 0

                # Get first tool proposal
                state = run_llm_for_tool(state, client)

        else:
            # Step in progress
            tool_result = None
            applied_action_descr = ""

            if action == "approve" and last_proposed:
                tool_name = last_proposed.get("name")
                args = last_proposed.get("args", {})
                if tool_name:
                    applied_action_descr = f"Approved & Executed: {tool_name} {args}"
                    tool_result = execute_tool_call(executor, tool_name, args, state.get("project_structure"))
                else:
                    applied_action_descr = "Approved & continued"

            elif action == "modify" and modified_tool:
                tool_name = modified_tool.get("name")
                args = modified_tool.get("args", {})
                applied_action_descr = f"Modified & Executed: {tool_name} {args}"
                tool_result = execute_tool_call(executor, tool_name, args, state.get("project_structure"))

            if tool_result is not None:
                state["current_command_output"] = ""
                if tool_result.startswith("Error:"):
                    state["errors_encountered"].append(
                        {
                            "step": state["step"],
                            "tool": tool_name,
                            "args": args,
                            "error": tool_result,
                        }
                    )
                else:
                    # Track created/edited files
                    if tool_name in ("write_file", "edit_file", "edit_lines"):
                        file_path = args.get("path", "")
                        if file_path:
                            track_created_file(state, file_path, state["step"])
                state["last_tool_result"] = tool_result

                try:
                    summary_text = tool_result
                    if len(summary_text) > 1200:
                        summary_text = summary_text[:1200] + "\n\n[truncated]"
                    save_step_summary(
                        workspace_path,
                        state["step"],
                        f"{applied_action_descr}\n\n{summary_text}",
                    )
                except Exception:
                    pass

                last_resp = state.get("last_raw_response")
                if last_resp and (
                    not state["messages"]
                    or state["messages"][-1]["content"] != last_resp
                ):
                    state["messages"].append(
                        {"role": "assistant", "content": last_resp}
                    )

                tool_content = f"TOOL RESULT:\n{tool_result}"
                if tool_result.startswith("Error:"):
                    tool_content += analyze_command_error(tool_name, args, tool_result)
                state["messages"].append(
                    {"role": "user", "content": tool_content}
                )
                state["execution_log"].append(
                    {
                        "step": state["step"],
                        "role": "tool_result",
                        "content": tool_result,
                    }
                )

            save_checkpoint(WORKSPACE_DIR, task_id, state)

            # Get next tool proposal
            state = run_llm_for_tool(state, client)

    elif state["stage"] == "verifying":
        planned = state.get("project_files_to_create", [])
        created = state.get("created_files", [])
        created_set = {f.get("path", "") for f in created}
        missing = [f for f in planned if f.get("path", "") not in created_set]

        if missing:
            missing_paths = [f.get("path") for f in missing]
            file_list = "\n".join(f"- {p}" for p in missing_paths)
            step_desc = (
                f"Create files still missing from the project structure:\n{file_list}\n\n"
                "Forneça conteúdo completo para cada arquivo. Não é necessário recriar arquivos já existentes."
            )
            state["project_structure"] = json.dumps(missing_paths)
            state["project_files_to_create"] = missing
            state["steps"].append(step_desc)
            state["current_step_idx"] = len(state["steps"]) - 1
            state["proposed_tool"] = {
                "name": "execute_step",
                "args": {
                    "step_num": len(state["steps"]),
                    "description": step_desc,
                },
            }
            state["status"] = "running"
            state["execution_log"].append({
                "step": state["step"],
                "role": "system",
                "content": f"📋 {len(missing)} arquivo(s) planejado(s) ainda não foram criados. Nova etapa adicionada para criá-los.",
            })
        else:
            state["status"] = "completed"
            state["stage"] = "completed"
            state["details"] = "Task completed."
            state["proposed_tool"] = None
            if state.get("errors_encountered"):
                trigger_self_improvement(state["task_id"], state)
            trigger_readme_generation(state["task_id"], state)
        save_checkpoint(WORKSPACE_DIR, task_id, state)

    save_task_state(task_id, state)
    return state


def run_llm_for_tool(state, client):
    """
    Helper function to query LLM for the next tool call during step execution.
    Handles finish_task to transition steps or stages.
    """
    max_retries = MAX_STAGE_RETRIES

    # Loop detection: track recent tool calls to detect repeated patterns
    if "_recent_tool_calls" not in state:
        state["_recent_tool_calls"] = []
    if "_analysis_nudge_count" not in state:
        state["_analysis_nudge_count"] = 0
    recent_tool_calls = state["_recent_tool_calls"]

    for attempt in range(max_retries):
        state["step"] += 1

        # Prepare streaming state before the LLM call
        state["current_streaming_response"] = ""
        state["is_streaming"] = True
        save_task_state(state["task_id"], state)

        def _streaming_callback(latest_text):
            state["current_streaming_response"] = latest_text
            save_task_state(state["task_id"], state)

        max_ctx = getattr(client.provider, 'max_context_window', 8192)
        compacted = compact_messages(
            state["messages"],
            max_context_tokens=max_ctx,
        )
        if compacted != state["messages"]:
            state["messages"] = compacted
            state["execution_log"].append({
                "step": state["step"],
                "role": "system",
                "content": "📏 Message history compacted to fit context window.",
            })
            save_task_state(state["task_id"], state)

        try:
            response_text = client.chat(
                state["messages"],
                temperature=0.1,
                stream_callback=_streaming_callback,
            )
        except ContextExceededError:
            state["is_streaming"] = False
            state["step"] -= 1
            max_ctx = getattr(client.provider, 'max_context_window', 8192)
            compacted = compact_messages(
                state["messages"],
                token_budget=int(max_ctx * 0.35),
                keep_last=3,
                max_context_tokens=max_ctx,
            )
            if compacted != state["messages"] and len(compacted) < len(state["messages"]):
                state["messages"] = compacted
                state["execution_log"].append({
                    "step": state["step"],
                    "role": "system",
                    "content": "⚠️ Context exceeded — message history compacted to fit context window.",
                })
                save_task_state(state["task_id"], state)
                continue
            err_msg = "LLM context exceeded and compaction failed to reduce size"
            state["status"] = "failed"
            state["details"] = err_msg
            save_task_state(state["task_id"], state)
            return state
        except LoopDetectedError:
            state["is_streaming"] = False
            state["step"] -= 1
            state["stage_retries"] = state.get("stage_retries", 0) + 1

            curr_idx = state.get("current_step_idx", 0)
            step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
            err_guidance = (
                f"ERROR: Loop detected - You are repeating the same pattern without making progress.\n\n"
                f"ADVICE: To break out of this loop, try a completely different approach. "
                f"Analyze what you have already done and what still needs to be done.\n\n"
                f"CURRENT STEP: {step_desc}\n\n"
                f"What you should do: Complete this step using your tools. "
                f"If you have already written the necessary code and the step is done, "
                f"call finish_task with a summary of what you did to proceed."
            )
            state["messages"].append({"role": "user", "content": err_guidance})

            if state["stage_retries"] >= MAX_STAGE_RETRIES:
                err_msg = f"LLM loop detected after {MAX_STAGE_RETRIES} retries"
                state["status"] = "failed"
                state["details"] = err_msg
                save_task_state(state["task_id"], state)
                return state
            state["details"] = (
                f"Retry {state['stage_retries']}/{MAX_STAGE_RETRIES} - LLM loop detected"
            )
            state["status"] = "running"
            save_task_state(state["task_id"], state)
            continue
        except Exception as e:
            err_msg = f"LLM error: {e}"
            state["errors_encountered"].append(
                {"step": state["step"], "type": "llm_error", "message": err_msg}
            )
            state["status"] = "failed"
            state["details"] = err_msg
            state["is_streaming"] = False
            save_task_state(state["task_id"], state)
            return state
        finally:
            state["is_streaming"] = False
            save_task_state(state["task_id"], state)

        # Cap and sanitize runaway responses before storing
        if is_runaway_response(response_text):
            response_text = truncate_runaway(response_text)
            state["execution_log"].append({
                "step": state["step"],
                "role": "system",
                "content": "⚠️ Runaway generation detected and truncated.",
            })
        elif len(response_text) > _MAX_RESPONSE_CHARS:
            response_text = truncate_runaway(response_text)

        # Text loop detection: 20-char segment repeated 3+ times
        if has_text_loop(response_text):
            curr_idx = state.get("current_step_idx", 0)
            step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
            response_text = "[Text loop detected - repeated content]"
            err_guidance = (
                f"CRITICAL LOOP DETECTED: Your response contains a repeating text pattern "
                f"(the same 20-character segment repeated 3+ times). This is an LLM loop.\n\n"
                f"ADVICE: To break out of this loop, try a completely different approach. "
                f"Analyze what you have already done and what still needs to be done.\n\n"
                f"CURRENT STEP: {step_desc}\n\n"
                f"If you have already written the necessary code and the step is done, "
                f"call finish_task with a summary of what you did to proceed."
            )
            state["messages"].append({"role": "user", "content": err_guidance})
            state["execution_log"].append({
                "step": state["step"],
                "role": "tool_result",
                "content": "LOOP DETECTED: Text-level loop (repeating 20-char segment 3+ times).",
            })
            recent_tool_calls.clear()
            continue

        state["last_raw_response"] = response_text
        assistant_entry = {
            "step": state["step"],
            "role": "assistant",
            "content": response_text,
        }
        usage = client.last_usage
        if usage:
            assistant_entry["llm_usage"] = usage
        state["execution_log"].append(assistant_entry)

        tool_name, args = parse_agent_response(response_text)

        # Loop detection: check if same tool call is being repeated
        if tool_name:
            call_signature = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
            recent_tool_calls.append(call_signature)

            # Keep only last 5 calls for comparison
            if len(recent_tool_calls) > 5:
                recent_tool_calls.pop(0)

            # Check for repeated pattern (3+ identical consecutive calls)
            if len(recent_tool_calls) >= 3:
                last_three = recent_tool_calls[-3:]
                if last_three[0] == last_three[1] == last_three[2]:
                    curr_idx = state.get("current_step_idx", 0)
                    step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
                    force_finish_msg = (
                        f"CRITICAL LOOP DETECTED: You have called '{tool_name}' with the same arguments 3 times in a row "
                        f"without making progress. This is a loop.\n\n"
                        f"You MUST stop making tool calls and immediately call finish_task:\n"
                        f'{{"tool": "finish_task", "args": {{"summary": "Completed step: {step_desc}"}}}}\n\n'
                        f"If you keep calling the same tool, you will never complete the task. "
                        f"Call finish_task NOW."
                    )
                    state["messages"].append({"role": "user", "content": force_finish_msg})
                    state["execution_log"].append(
                        {
                            "step": state["step"],
                            "role": "tool_result",
                            "content": f"LOOP DETECTED: Forced finish_task guidance injected.",
                        }
                    )
                    recent_tool_calls.clear()
                    continue

            # Check for alternating file write pattern (same 1-2 files rewritten repeatedly)
            write_file_calls = [c for c in recent_tool_calls if c.startswith("write_file:")]
            if len(write_file_calls) >= 4:
                written_paths = set()
                for call in write_file_calls:
                    try:
                        args_str = call[len("write_file:"):]
                        call_args = json.loads(args_str)
                        path = call_args.get("path", "")
                        written_paths.add(path)
                    except (json.JSONDecodeError, KeyError):
                        pass
                if len(written_paths) <= 2:
                    curr_idx = state.get("current_step_idx", 0)
                    step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
                    paths_str = ", ".join(sorted(written_paths))
                    loop_msg = (
                        f"CRITICAL LOOP DETECTED: You have written the same file(s) repeatedly "
                        f"({paths_str}) {len(write_file_calls)} times without making progress. "
                        f"This is a loop.\n\n"
                        f"You MUST stop making tool calls and immediately call finish_task:\n"
                        f'{{"tool": "finish_task", "args": {{"summary": "Completed step: {step_desc}"}}}}\n\n'
                        f"Call finish_task NOW."
                    )
                    state["messages"].append({"role": "user", "content": loop_msg})
                    state["execution_log"].append(
                        {
                            "step": state["step"],
                            "role": "tool_result",
                            "content": f"LOOP DETECTED: Alternating file write pattern detected.",
                        }
                    )
                    recent_tool_calls.clear()
                    continue

            # Also detect if no finish_task after tool calls in same step
            non_finish_calls = [c for c in recent_tool_calls if not c.startswith("finish_task:")]
            if len(non_finish_calls) >= 2:
                # Check if any file writing actually happened
                write_calls = [c for c in non_finish_calls if c.startswith("write_file:") or c.startswith("edit_file:") or c.startswith("edit_lines:")]
                if len(write_calls) == 0:
                    curr_idx = state.get("current_step_idx", 0)
                    step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
                    analysis_nudge_count = state.get("_analysis_nudge_count", 0) + 1
                    state["_analysis_nudge_count"] = analysis_nudge_count

                    if analysis_nudge_count >= 2:
                        # Force-finish the step after 3 consecutive analysis loop nudges
                        summary = f"Step auto-completed after {analysis_nudge_count} analysis loop nudges: {step_desc}"
                        state["completed_step_summaries"].append(f"{step_desc} -> {summary}")
                        state["execution_log"].append({
                            "step": state["step"],
                            "role": "system",
                            "content": f"✅ Step {curr_idx + 1} Auto-Completed (analysis loop): {summary}",
                        })
                        state["messages"].append({"role": "user", "content": (
                            f"CRITICAL: You were stuck in an analysis loop after {analysis_nudge_count} warnings. "
                            f"The step has been auto-completed to prevent infinite looping.\n\n"
                            f"Your tool call was NOT executed. The next step will begin."
                        )})
                        recent_tool_calls.clear()
                        state["_analysis_nudge_count"] = 0

                        next_idx = curr_idx + 1
                        if next_idx < len(state["steps"]):
                            state["current_step_idx"] = next_idx
                            state["proposed_tool"] = {
                                "name": "execute_step",
                                "args": {
                                    "step_num": next_idx + 1,
                                    "description": state["steps"][next_idx],
                                },
                            }
                            state["status"] = "running"
                        else:
                            planned = state.get("project_files_to_create", [])
                            created = state.get("created_files", [])
                            created_set = {f.get("path", "") for f in created}
                            missing = [f for f in planned if f.get("path", "") not in created_set]

                            if missing:
                                missing_paths = [f.get("path") for f in missing]
                                file_list = "\n".join(f"- {p}" for p in missing_paths)
                                step_desc = (
                                    f"Create files still missing from the project structure:\n{file_list}\n\n"
                                    "Forneça conteúdo completo para cada arquivo. Não é necessário recriar arquivos já existentes."
                                )
                                state["project_structure"] = json.dumps(missing_paths)
                                state["project_files_to_create"] = missing
                                state["steps"].append(step_desc)
                                state["current_step_idx"] = len(state["steps"]) - 1
                                state["proposed_tool"] = {
                                    "name": "execute_step",
                                    "args": {
                                        "step_num": len(state["steps"]),
                                        "description": step_desc,
                                    },
                                }
                                state["status"] = "running"
                                state["execution_log"].append({
                                    "step": state["step"],
                                    "role": "system",
                                    "content": f"📋 {len(missing)} arquivo(s) planejado(s) ainda não foram criados. Nova etapa adicionada para criá-los.",
                                })
                            else:
                                state["stage"] = "completed"
                                state["status"] = "completed"
                                state["details"] = "All steps executed successfully."
                                state["proposed_tool"] = None
                                try:
                                    add_task_history(
                                        MEMORY_DIR, state["task"], "SUCCESS",
                                        "All steps executed successfully."
                                    )
                                except Exception:
                                    pass
                                if state.get("errors_encountered"):
                                    trigger_self_improvement(state["task_id"], state)
                                trigger_readme_generation(state["task_id"], state)
                        save_checkpoint(WORKSPACE_DIR, state["task_id"], state)
                        return state
                    else:
                        nudge_msg = (
                            f"WARNING: You have made {len(non_finish_calls)} tool calls without writing any files "
                            f"or calling finish_task. You are likely stuck in an analysis loop.\n\n"
                            f"CURRENT STEP: {step_desc}\n\n"
                            f"Warning {analysis_nudge_count}/2. After 2 warnings, the step will be "
                            f"auto-completed and the tool call will be discarded.\n\n"
                            f"IMPORTANT: 'write_file' automatically creates parent directories. You do NOT need to list_dir or create directories first. "
                            f"Start implementing by calling write_file directly. "
                            f"If the step is already complete, call finish_task immediately."
                        )
                        state["messages"].append({"role": "user", "content": nudge_msg})
                        state["execution_log"].append({
                            "step": state["step"],
                            "role": "tool_result",
                            "content": f"WARNING: Analysis loop detected - nudging toward implementation (nudge {analysis_nudge_count}/3).",
                        })
                        recent_tool_calls.clear()
                        continue
        else:
            # No valid tool call - reset recent calls tracking
            recent_tool_calls.clear()

        if not tool_name:
            curr_idx = state.get("current_step_idx", 0)
            step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
            err_msg = (
                f"ERROR: Format error - Your response could not be parsed into a valid tool call.\n\n"
                f"CORRECT FORMAT:\n"
                f"Output your reasoning followed by exactly one tool call:\n"
                f'{{"tool": "tool_name", "args": {{"parameter_name": "value"}}}}\n\n'
                f"Available tools: list_dir, read_file, write_file, edit_file, edit_lines, grep, find_in_files, grep_output, start_http_server, stop_http_server, list_http_servers, run_lint, finish_task\n\n"
                f"CURRENT STEP: {step_desc}\n\n"
                f"What you should do: Determine the next action for this step and output it in the correct JSON format. "
                f"Do not ask questions or request input. Execute autonomously."
            )
            state["errors_encountered"].append(
                {"step": state["step"], "type": "format_error", "message": err_msg}
            )
            state["messages"].append({"role": "assistant", "content": response_text})
            state["messages"].append({"role": "user", "content": f"ERROR:\n{err_msg}"})
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "tool_result",
                    "content": f"ERROR: {err_msg}",
                }
            )

            if attempt < max_retries - 1:
                continue

            state["status"] = "failed"
            state["proposed_tool"] = None
            return state

        if tool_name == "finish_task":
            recent_tool_calls.clear()
            state["_analysis_nudge_count"] = 0
            summary = args.get("summary", "Step completed.")
            curr_idx = state["current_step_idx"]
            step_desc = state["steps"][curr_idx]
            state["completed_step_summaries"].append(f"{step_desc} -> {summary}")
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"✅ Step {curr_idx + 1} Complete: {summary}",
                }
            )

            next_idx = curr_idx + 1
            if next_idx < len(state["steps"]):
                state["current_step_idx"] = next_idx
                state["proposed_tool"] = {
                    "name": "execute_step",
                    "args": {
                        "step_num": next_idx + 1,
                        "description": state["steps"][next_idx],
                    },
                }
                state["status"] = "running"
            else:
                planned = state.get("project_files_to_create", [])
                created = state.get("created_files", [])
                created_set = {f.get("path", "") for f in created}
                missing = [f for f in planned if f.get("path", "") not in created_set]

                if missing:
                    missing_file_attempts = state.get("_missing_file_attempts", 0) + 1
                    state["_missing_file_attempts"] = missing_file_attempts

                    if missing_file_attempts > 2:
                        state["stage"] = "completed"
                        state["status"] = "completed"
                        state["details"] = f"Steps executed. {len(missing)} planned file(s) not created after {missing_file_attempts} attempts - completing anyway."
                        state["proposed_tool"] = None
                        state["execution_log"].append({
                            "step": state["step"],
                            "role": "system",
                            "content": f"⚠️ {len(missing)} file(s) not created after {missing_file_attempts} attempts. Task completed anyway.",
                        })
                        try:
                            add_task_history(
                                MEMORY_DIR, state["task"], "SUCCESS",
                                state["details"]
                            )
                        except Exception:
                            pass
                        if state.get("errors_encountered"):
                            trigger_self_improvement(state["task_id"], state)
                        trigger_readme_generation(state["task_id"], state)
                    else:
                        missing_paths = [f.get("path") for f in missing]
                        file_list = "\n".join(f"- {p}" for p in missing_paths)
                        step_desc = (
                            f"Create files still missing from the project structure:\n{file_list}\n\n"
                            "Forneça conteúdo completo para cada arquivo. Não é necessário recriar arquivos já existentes."
                        )
                        state["project_structure"] = json.dumps(missing_paths)
                        state["project_files_to_create"] = missing
                        state["steps"].append(step_desc)
                        state["current_step_idx"] = len(state["steps"]) - 1
                        state["proposed_tool"] = {
                            "name": "execute_step",
                            "args": {
                                "step_num": len(state["steps"]),
                                "description": step_desc,
                            },
                        }
                        state["status"] = "running"
                        state["execution_log"].append({
                            "step": state["step"],
                            "role": "system",
                            "content": f"📋 {len(missing)} arquivo(s) planejado(s) ainda não foram criados. Nova etapa adicionada para criá-los.",
                        })
                else:
                    state["stage"] = "completed"
                    state["status"] = "completed"
                    state["details"] = "All steps executed successfully."
                    state["proposed_tool"] = None
                    try:
                        add_task_history(
                            MEMORY_DIR, state["task"], "SUCCESS",
                            "All steps executed successfully."
                        )
                    except Exception:
                        pass
                    if state.get("errors_encountered"):
                        trigger_self_improvement(state["task_id"], state)
                    trigger_readme_generation(state["task_id"], state)
            save_checkpoint(WORKSPACE_DIR, state["task_id"], state)
            return state

        state["proposed_tool"] = {"name": tool_name, "args": args}
        state["status"] = "running"
        save_checkpoint(WORKSPACE_DIR, state["task_id"], state)
        return state


def track_created_file(state, file_path, step_num=None):
    """Track a file created by the agent in the task state."""
    if not file_path:
        return
    
    # Normalize path: remove output/ prefix if present
    normalized_path = file_path
    if normalized_path.startswith("output/"):
        normalized_path = normalized_path[7:]
    
    # Check if file already tracked (update existing entry)
    created_files = state.get("created_files", [])
    for i, entry in enumerate(created_files):
        if entry.get("path") == normalized_path:
            # Update existing entry with new timestamp
            created_files[i]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if step_num is not None:
                created_files[i]["step"] = step_num
            return
    
    # Add new entry
    entry = {
        "path": normalized_path,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if step_num is not None:
        entry["step"] = step_num
    
    created_files.append(entry)
    state["created_files"] = created_files


def parse_project_structure_to_files(structure_text):
    if not structure_text:
        return []
    try:
        files = json.loads(structure_text)
        if isinstance(files, list):
            return [{"path": f} for f in files if isinstance(f, str) and f.strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _resolve_path_from_structure(path: str, project_structure) -> str:
    """Correct any file path to match the project structure by basename lookup."""
    if not path or not project_structure:
        return path
    # Parse structure if it's a JSON string
    structure = project_structure
    if isinstance(structure, str):
        try:
            structure = json.loads(structure)
        except (json.JSONDecodeError, TypeError):
            return path
    if not isinstance(structure, list):
        return path
    basename = os.path.basename(path)
    if not basename:
        return path
    # Find all entries matching this filename
    candidates = [entry for entry in structure if isinstance(entry, str) and os.path.basename(entry) == basename]
    if not candidates:
        return path
    # If only one match, use it
    if len(candidates) == 1:
        return candidates[0]
    # Multiple matches — prefer shortest path (most specific location)
    return min(candidates, key=len)


def execute_tool_call(executor, name, args, project_structure=None):
    if name == "list_dir":
        return executor.list_dir(args.get("path", "."))
    elif name == "read_file":
        return executor.read_file(args.get("path", ""))
    elif name == "write_file":
        raw_path = args.get("path", "")
        corrected_path = _resolve_path_from_structure(raw_path, project_structure)
        result = executor.write_file(corrected_path, args.get("content", ""))
        # If path was corrected, update args so callers track the actual path
        if corrected_path != raw_path:
            args["path"] = corrected_path
            result = result.replace(f"'{raw_path}'", f"'{corrected_path}'")
        return result
    elif name == "edit_file":
        return executor.edit_file(
            args.get("path", ""),
            args.get("target", ""),
            args.get("replacement", ""),
        )
    elif name == "edit_lines":
        return executor.edit_lines(
            args.get("path", ""),
            args.get("start_line", 1),
            args.get("end_line", 1),
            args.get("replacement", ""),
        )
    elif name == "grep":
        return executor.grep(
            args.get("path", ""),
            args.get("pattern", ""),
        )
    elif name == "find_in_files":
        return executor.find_in_files(
            args.get("query", ""), args.get("path", ".")
        )
    elif name == "grep_output":
        return executor.grep_output(args.get("query", ""))
    elif name == "run_lint":
        return executor.run_lint(args.get("language", "python"), args.get("path", "."))
    else:
        return f"Error: Tool '{name}' is not supported."


def trigger_self_improvement(task_id, state):
    """Runs self-improvement loop in a background thread"""

    def run_improvement():
        try:
            meta_agent = SelfImprovementAgent(
                MEMORY_DIR, base_url=state.get("llamacpp_url", LLAMACPP_URL)
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


def trigger_readme_generation(task_id, state):
    """Generates a README.md in the output directory after task completion."""
    task_path = get_task_path(task_id)

    def run_generator():
        try:
            generator = ReadmeGenerator(task_path)
            readme = generator.generate()
            if readme:
                generator.save_readme(readme)
                print(f"📄 README.md generated for task {task_id}")
        except Exception as e:
            print(f"README generation failed: {e}")

    thread = threading.Thread(target=run_generator)
    thread.daemon = True
    thread.start()


def background_execution_loop(task_id, retry_delay=TASK_RETRY_DELAY):
    """Loop execution steps in background with self-correcting retry on failure.
    In whatsapp mode, asks for guidance on repeated failures.
    On repeated failures, instructs the LLM to change approach instead of retrying the same way."""

    state = load_task_state(task_id)
    if state is None:
        print(f"[Background] Task {task_id} has no state file, aborting loop", flush=True)
        return
    max_retries = MAX_WHATSAPP_RETRIES if _is_whatsapp_mode(state) else MAX_TASK_RETRIES
    whatsapp_mode = _is_whatsapp_mode(state)

    attempt = 0

    while True:
        if attempt > 0:
            state = load_task_state(task_id)
            if state:
                state["execution_log"].append(
                    {
                        "step": state.get("step", 0),
                        "role": "system",
                        "content": f"🔄 Retry attempt {attempt}/{max_retries} (waiting {retry_delay}s)...",
                    }
                )
                save_task_state(task_id, state)
            time.sleep(retry_delay)

        if is_task_stopped(task_id):
            break

        # WhatsApp mode: ask for guidance on repeated failures (every 3 attempts)
        if whatsapp_mode and attempt > 0 and attempt % 3 == 0:
            state = load_task_state(task_id)
            if state and state.get("status") != "completed":
                failure_count = len(state.get("failure_history", []))
                last_detail = state.get("details") or "Unknown error"
                _ask_whatsapp_for_guidance(
                    task_id, state,
                    f"Agent has failed {failure_count} times. Last error: {last_detail[:100]}",
                    ask_type="stuck"
                )

        # Smart retry: keep existing plan and assess what was done
        if attempt > 0:
            state = load_task_state(task_id)
            if state and state.get("status") == "failed":
                existing_plan = state.get("plan")
                existing_steps = state.get("steps", [])
                completed_summaries = state.get("completed_step_summaries", [])
                last_step = state.get("current_step_idx", 0)

                raw_detail = state.get("details") or ""
                archived = {
                    "attempt": attempt,
                    "errors": state.get("errors_encountered", []),
                    "details": (raw_detail[:200] + "..." if len(raw_detail) > 200 else raw_detail),
                    "stage": state.get("stage"),
                    "step": last_step,
                }
                failure_history = state.get("failure_history", [])
                failure_history.append(archived)
                state["failure_history"] = failure_history

                state["status"] = "running"
                state["stage_retries"] = 0
                state["errors_encountered"] = []
                state["last_raw_response"] = None
                state["last_tool_result"] = None
                state["last_user_intervention"] = None
                state["current_streaming_response"] = ""
                state["is_streaming"] = False
                state["details"] = None

                total_failures = len(failure_history)

                # Decide strategy based on failure count
                if total_failures >= 3 and existing_steps and existing_plan:
                    # After 3+ failures: regenerate plan with past failure context
                    state["stage"] = "generating_plan"
                    state["step"] = 0
                    state["plan"] = None
                    state["steps"] = []
                    state["messages"] = []
                    state["proposed_tool"] = {"name": "generate_plan", "args": {}}
                    from collections import Counter
                    error_summary = Counter()
                    for entry in failure_history:
                        detail = entry.get("details") or "Unknown error"
                        stage = entry.get("stage", "?")
                        core = _compact_error_detail(detail)
                        error_summary[(stage, core)] += 1
                    failure_context = " | ".join(f"{s}: {e} [×{c}]" for (s, e), c in error_summary.items())
                    msg = (
                        f"FALHAS ANTERIORES ({total_failures} tentativas): {failure_context}\n\n"
                        f"Você tentou implementar este plano {total_failures} vezes e todas falharam. Gere um plano COMPLETAMENTE NOVO e MUITO MAIS SIMPLES.\n"
                        f"O plano anterior NÃO funcionou. Crie uma abordagem completamente diferente.\n"
                        f"CRÍTICO: Use no máximo 2-3 etapas. Mantenha tudo em UM arquivo único. NÃO crie arquivos separados.\n"
                        f"Não use DDD, arquitetura em camadas, ou padrões complexos. Apenas implemente o essencial."
                    )
                    state["complexity"] = "simple"
                    state["last_user_intervention"] = msg
                elif existing_steps and existing_plan:
                    resume_step = min(last_step, len(existing_steps) - 1)
                    all_done = last_step >= len(existing_steps)
                    state["plan"] = existing_plan
                    state["steps"] = existing_steps
                    state["current_step_idx"] = resume_step if not all_done else len(existing_steps)
                    state["step"] = 0
                    state["completed_step_summaries"] = completed_summaries

                    if all_done:
                        planned = state.get("project_files_to_create", [])
                        created = state.get("created_files", [])
                        created_set = {f.get("path", "") for f in created}
                        missing = [f for f in planned if f.get("path", "") not in created_set]

                        if missing:
                            missing_file_attempts = state.get("_missing_file_attempts", 0) + 1
                            state["_missing_file_attempts"] = missing_file_attempts

                            if missing_file_attempts > 2:
                                state["stage"] = "completed"
                                state["status"] = "completed"
                                state["details"] = f"Steps executed. {len(missing)} planned file(s) not created after {missing_file_attempts} attempts - completing anyway."
                                state["messages"] = []
                                state["proposed_tool"] = None
                                state["execution_log"].append({
                                    "step": state["step"],
                                    "role": "system",
                                    "content": f"⚠️ {len(missing)} file(s) not created after {missing_file_attempts} attempts. Task completed anyway.",
                                })
                                try:
                                    add_task_history(
                                        MEMORY_DIR, state["task"], "SUCCESS",
                                        state["details"]
                                    )
                                except Exception:
                                    pass
                                if state.get("errors_encountered"):
                                    trigger_self_improvement(task_id, state)
                                trigger_readme_generation(task_id, state)
                            else:
                                missing_paths = [f.get("path") for f in missing]
                                file_list = "\n".join(f"- {p}" for p in missing_paths)
                                step_desc = (
                                    f"Create files still missing from the project structure:\n{file_list}\n\n"
                                    "Forneça conteúdo completo para cada arquivo. Não é necessário recriar arquivos já existentes."
                                )
                                state["project_structure"] = json.dumps(missing_paths)
                                state["project_files_to_create"] = missing
                                state["steps"].append(step_desc)
                                state["current_step_idx"] = len(state["steps"]) - 1
                                state["proposed_tool"] = {
                                    "name": "execute_step",
                                    "args": {
                                        "step_num": len(state["steps"]),
                                        "description": step_desc,
                                    },
                                }
                                state["status"] = "running"
                                state["execution_log"].append({
                                    "step": state["step"],
                                    "role": "system",
                                    "content": f"📋 {len(missing)} arquivo(s) planejado(s) ainda não foram criados. Nova etapa adicionada para criá-los.",
                                })
                        else:
                            state["stage"] = "completed"
                            state["status"] = "completed"
                            state["details"] = "All steps executed successfully."
                            state["messages"] = []
                            state["proposed_tool"] = None
                            try:
                                add_task_history(
                                    MEMORY_DIR, state["task"], "SUCCESS",
                                    "All steps executed successfully."
                                )
                            except Exception:
                                pass
                            if state.get("errors_encountered"):
                                trigger_self_improvement(task_id, state)
                            trigger_readme_generation(task_id, state)
                    else:
                        state["stage"] = "executing_steps"
                        completed_text = ""
                        if completed_summaries:
                            completed_text = "\nPreviously completed steps:\n"
                            for idx, s in enumerate(completed_summaries):
                                completed_text += f"  Step {idx+1}: {s}\n"

                        failure_lessons = ""
                        approach_change = ""
                        if failure_history:
                            from collections import Counter
                            error_summary = Counter()
                            last_entry = failure_history[-1]
                            for entry in failure_history:
                                detail = entry.get("details") or "Unknown error"
                                stage = entry.get("stage", "?")
                                core = _compact_error_detail(detail)
                                error_summary[(stage, core)] += 1
                            total = len(failure_history)
                            last_stage = last_entry.get("stage", "?")
                            last_core = _compact_error_detail(last_entry.get("details") or "Unknown error")
                            last_count = error_summary.get((last_stage, last_core), 1)
                            failure_lessons = (
                                f"\n\nPREVIOUS FAILURES: {total} total, "
                                f"last: {last_core} (stage: {last_stage}) [×{last_count}]"
                            )
                            others = [(k, v) for k, v in error_summary.items() if k != (last_stage, last_core)]
                            if others:
                                brief = "; ".join(f"{s}: {e} [×{c}]" for (s, e), c in sorted(others, key=lambda x: -x[1]))
                                failure_lessons += f" | also: {brief}"
                            if total_failures >= 3:
                                approach_change = (
                                    "\n\nCHANGE APPROACH REQUIRED: You have failed multiple times. "
                                    "Do NOT repeat the same implementation strategy that failed before. "
                                    "Analyze what went wrong and try a fundamentally different approach. "
                                    "Consider: different architecture, different libraries, different patterns. "
                                    "If the previous attempts used certain patterns that failed, deliberately avoid them."
                                )

                        state["messages"] = [
                            {
                                "role": "system",
                                "content": f"""We are retrying a partially completed task.

EXISTING PLAN:
{existing_plan}

{completed_text}
Remaining steps to execute:
{chr(10).join(f"Step {i+1}: {s}" for i, s in enumerate(existing_steps) if i >= resume_step)}

First, explore what already exists:
1. List the output directory to see existing files
2. Read key files to understand current state
3. Then continue implementing from where it left off

IMPORTANT: 'write_file' automatically creates parent directories. You do NOT need to create directories first - just write files directly.

Do NOT generate a new plan. Follow the existing plan.{failure_lessons}{approach_change}""",
                            }
                        ]
                        state["proposed_tool"] = {
                            "name": "execute_step",
                            "args": {"step_num": resume_step + 1, "description": existing_steps[resume_step]},
                        }
                else:
                    state["stage"] = "generating_plan"
                    state["step"] = 0
                    state["proposed_tool"] = {"name": "generate_plan", "args": {}}

                save_task_state(task_id, state)

        # Run execution loop
        while True:
            if is_task_stopped(task_id):
                break
            state = load_task_state(task_id)
            if not state or state["status"] not in ("running", "processando"):
                break

            if not state.get("proposed_tool"):
                state = run_agent_step_sync(task_id, action="inject", user_prompt=None)
                if is_task_stopped(task_id):
                    break
                if (
                    not state
                    or state["status"] not in ("running", "processando")
                    or not state.get("proposed_tool")
                ):
                    break

            proposed_tool = state.get("proposed_tool")
            if proposed_tool:
                if proposed_tool.get("executed"):
                    del proposed_tool["executed"]
                    save_task_state(task_id, state)
                    continue
                state = run_agent_step_sync(task_id, action="approve")
            else:
                state = run_agent_step_sync(task_id, action="approve")

            if not state or state["status"] in (
                "completed",
                "failed",
            ):
                break

            time.sleep(0.5)

        # Check if task succeeded
        state = load_task_state(task_id)
        if state and state.get("status") == "completed":
            if whatsapp_mode and whatsapp_configured():
                task_preview = state.get("task", "Task")[:50]
                send_admin_text(f"✅ Task completed: {task_preview}")
            break

        # Check max retries
        attempt += 1
        if attempt > max_retries:
            state = load_task_state(task_id)
            if state and state.get("status") != "completed":
                state["details"] = f"Max retries ({max_retries}) exhausted."
                if whatsapp_mode and whatsapp_configured():
                    task_preview = state.get("task", "Task")[:50]
                    send_admin_alert(
                        "Task Failed After Max Retries",
                        f"Task: {task_preview}\nRetries: {attempt}/{max_retries}\nLast status: {state.get('status')}",
                        task_id=task_id,
                    )
                save_task_state(task_id, state)
            break

        # Build compact failure summary for execution_log
        state = load_task_state(task_id)
        if state and state.get("status") != "completed":
            failure_history = state.get("failure_history", [])
            from collections import Counter
            error_counts: Counter = Counter()
            last_entry = failure_history[-1] if failure_history else None
            for entry in failure_history:
                detail = entry.get("details") or "Unknown error"
                stage = entry.get("stage", "?")
                core = _compact_error_detail(detail)
                error_counts[(stage, core)] += 1
            total = len(failure_history)
            parts = [f"Retry {attempt} failed. ({total} total failures)"]
            if last_entry:
                last_core = _compact_error_detail(last_entry.get("details") or "Unknown error")
                last_stage = last_entry.get("stage", "?")
                last_n = error_counts.get((last_stage, last_core), 1)
                parts.append(f"  Last: {last_core} (stage: {last_stage}) [×{last_n}]")
            # Other distinct errors (skip last which was already shown)
            others = [(k, v) for k, v in error_counts.items()
                      if not (last_entry and k == (_compact_error_detail(last_entry.get("details") or "Unknown error"), last_entry.get("stage", "?")))]
            if others:
                brief = "; ".join(f"{s}: {e} [×{c}]" for (s, e), c in sorted(others, key=lambda x: -x[1]))
                parts.append(f"  Also: {brief}")
            state["execution_log"].append(
                {
                    "step": state.get("step", 0),
                    "role": "system",
                    "content": "\n".join(parts),
                }
            )
            save_task_state(task_id, state)


# --- Flask API Routes ---


@app.route("/api/webhooks/whatsapp", methods=["POST"])
def whatsapp_webhook():
    task_id = request.args.get("task_id") or request.args.get("taskId")
    data = request.json or {}
    ask_id = data.get("askId") or data.get("ask_id")
    response_str = data.get("response") or data.get("originalMessage", "")
    phone = data.get("senderIdentity") or request.args.get("phoneNumber") or "unknown"

    if not ask_id:
        return jsonify({"error": "Missing askId"}), 400

    pending = resolve_pending_ask(ask_id)
    if not pending:
        return jsonify({"status": "no_pending_ask", "detail": "Ask expired or already resolved"}), 200

    stored_task_id = pending.get("task_id")
    if not stored_task_id:
        return jsonify({"error": "No task_id associated with ask"}), 400

    state = load_task_state(stored_task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    if state.get("status") not in ("failed", "running", "processando"):
        return jsonify({"status": "task_not_pending", "current_status": state.get("status")}), 200

    try:
        response_index = int(response_str.strip()) - 1
    except (ValueError, TypeError):
        response_index = -1

    if response_index < 0:
        try:
            options = pending.get("options", [])
            response_lower = response_str.strip().lower()
            for i, opt in enumerate(options):
                if opt.lower() == response_lower or response_lower in opt.lower():
                    response_index = i
                    break
        except Exception:
            pass

    if response_index < 0:
        return jsonify({"status": "invalid_response", "response": response_str}), 200

    print(f"[WhatsApp Webhook] task={stored_task_id} ask={ask_id} phone={phone} choice={response_str}", flush=True)

    _apply_whatsapp_intervention(stored_task_id, state, pending, response_index)

    state["status"] = "running"
    state["proposed_tool"] = None
    state["last_tool_result"] = None
    state["stage_retries"] = 0
    state["errors_encountered"] = []
    state["current_streaming_response"] = ""
    state["is_streaming"] = False

    task_path = get_task_path(stored_task_id)
    task_state_file = os.path.join(task_path, "task_state.json")
    os.makedirs(task_path, exist_ok=True)
    try:
        with open(task_state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print(f"[WhatsApp Webhook] State saved with running status for {stored_task_id}", flush=True)
    except Exception as e:
        print(f"[WhatsApp Webhook] Failed to save state: {e}", flush=True)

    signal_task_stop(stored_task_id)
    time.sleep(0.5)

    if _is_whatsapp_mode(state):
        print(f"[WhatsApp Webhook] Starting resume thread for {stored_task_id}", flush=True)
        def _resume():
            try:
                background_execution_loop(stored_task_id)
            except Exception as e:
                print(f"[WhatsApp Resume] Error for {stored_task_id}: {e}", flush=True)
        ensure_task_stop_event(stored_task_id)
        t = threading.Thread(target=_resume)
        t.daemon = True
        t.start()
        active_threads[stored_task_id] = t
    elif state.get("mode") == "auto":
        print(f"[WhatsApp Webhook] Starting auto resume for {stored_task_id}", flush=True)
        def _resume_auto():
            try:
                background_execution_loop(stored_task_id)
            except Exception as e:
                print(f"[WhatsApp Auto Resume] Error for {stored_task_id}: {e}", flush=True)
        ensure_task_stop_event(stored_task_id)
        t = threading.Thread(target=_resume_auto)
        t.daemon = True
        t.start()
        active_threads[stored_task_id] = t

    print(f"[WhatsApp Webhook] Done - {stored_task_id} status=running", flush=True)

    return jsonify({
        "status": "ok",
        "task_id": stored_task_id,
        "task_status": "running",
        "choice": response_str,
        "action": pending.get("options", [])[response_index] if 0 <= response_index < len(pending.get("options", [])) else str(response_index),
    })


# Socket.IO is handled by flask-socketio directly


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
            if t["status"] in ("running", "processando")
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


def _detect_complexity(task: str) -> str:
    """Auto-detect complexity based on task description.
    Returns 'simple' for straightforward single-file tasks, 'complex' otherwise."""
    t = task.lower().strip()
    simple_keywords = [
        "html", "css", "pagina", "page", "single", "único", "unico",
        "js", "javascript", "simples", "simple", "one file",
        "create a single", "criar um html", "criar uma pagina",
    ]
    char_count = len(t)
    word_count = len(t.split())

    for kw in simple_keywords:
        if kw in t:
            return "simple"

    if char_count < 60 or word_count < 8:
        return "simple"

    return "complex"


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
                    tasks.append({
                        "task_id": state.get("task_id", folder),
                        "task": state.get("task", ""),
                        "status": state.get("status", "unknown"),
                        "step": state.get("step", 0),
                        "created_at": state.get("created_at", ""),
                    })
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

    mode = data.get("mode", "auto")  # 'auto' or 'auto-whatsapp'
    model_think = data.get("model_think", False)
    provider_type = data.get("provider_type", "llamacpp")
    complexity = data.get("complexity", _detect_complexity(task_prompt))  # 'simple' or 'complex'
    default_retries = MAX_WHATSAPP_RETRIES if mode == "auto-whatsapp" else MAX_TASK_RETRIES
    max_retries = int(data.get("max_retries", default_retries))
    retry_delay = int(data.get("retry_delay", TASK_RETRY_DELAY))

    # 1. Create isolated directory and output directory
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    task_id = f"task_{timestamp}"
    task_path = get_task_path(task_id)
    os.makedirs(task_path, exist_ok=True)
    os.makedirs(os.path.join(task_path, "output"), exist_ok=True)

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

    # 3. Formulate state
    state = {
        "task_id": task_id,
        "task": task_prompt,
        "created_at": created_time_str,
        "mode": mode,
        "status": "running",  # always start running
        "stage": "generating_plan",
        "step": 0,
        "model_think": model_think,
        "provider_type": provider_type,
        "complexity": complexity,
        "llamacpp_url": get_provider_url(provider_type),
        "messages": [],
        "execution_log": [
            {
                "step": 0,
                "role": "system",
                "content": f"Initialized task: {task_prompt}. Stage: Generating plan.",
            }
        ],
        "errors_encountered": [],
        "proposed_tool": {
            "name": "generate_plan",
            "args": {},
        },
        "last_raw_response": None,
        "step_summaries": [],
        "last_tool_result": None,
        "last_user_intervention": None,
        "plan": None,
        "steps": [],
        "current_step_idx": 0,
        "completed_step_summaries": [],
        "current_streaming_response": "",
        "is_streaming": False,
        "current_command_output": "",
        "created_files": [],
        "project_structure": None,
        "project_files_to_create": [],
    }

    save_task_state(task_id, state)
    save_plan_overview(task_path, task_prompt, created_time_str)

    # 5. Always auto-start first step in background.
    def _initial_step():
        try:
            run_agent_step_sync(task_id, action="approve")
            if mode in ("auto", "auto-whatsapp"):
                background_execution_loop(task_id, retry_delay=retry_delay)
        except Exception as e:
            print(f"[Startup] _initial_step crashed for {task_id}: {e}", flush=True)
            try:
                s = load_task_state(task_id)
                if s and s.get("status") not in ("completed", "failed"):
                    s["status"] = "failed"
                    s["proposed_tool"] = None
                    s["details"] = f"Internal startup error: {e}"
                    save_task_state(task_id, s)
            except Exception:
                pass
            if mode == "auto-whatsapp" and whatsapp_configured():
                send_admin_alert(
                    "Agent Crashed on Startup",
                    f"Task: {task_prompt[:80]}\nError: {e}",
                    task_id=task_id,
                )

    ensure_task_stop_event(task_id)
    thread = threading.Thread(target=_initial_step)
    thread.daemon = True
    thread.start()
    active_threads[task_id] = thread

    # Notify WebSocket clients
    try:
        emit_tasks_list_update()
        emit_dashboard_update()
    except Exception:
        pass

    return jsonify(state)


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    state = load_task_state(task_id)
    if not state:
        # Gracefully handle legacy tasks
        task_path = get_task_path(task_id)
        info_path = os.path.join(task_path, "task_info.html")
        if os.path.exists(info_path):
            task_desc = "Unknown Task"
            with open(info_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
                desc_div = soup.find(class_="task-description")
                if desc_div:
                    task_desc = desc_div.text.strip()
            created_time = task_id.replace("task_", "")
            state = {
                "task_id": task_id,
                "task": task_desc,
                "created_at": created_time,
                "status": "legacy",
                "stage": "legacy",
                "step": 0,
                "messages": [],
                "execution_log": [],
                "errors_encountered": [],
                "proposed_tool": None,
                "last_raw_response": None,
                "step_summaries": [],
                "last_tool_result": None,
                "last_user_intervention": None,
                "plan": None,
                "steps": [],
                "current_step_idx": 0,
                "completed_step_summaries": [],
                "current_streaming_response": "",
                "is_streaming": False,
                "current_command_output": "",
            }
        else:
            return jsonify({"error": "Task not found"}), 404

    # Remove large internal fields not needed by frontend
    state.pop("messages", None)
    state.pop("_recent_tool_calls", None)
    state.pop("failure_history", None)

    # Include output-only file tree for workspace pane
    state["file_tree"] = build_output_file_tree(get_task_path(task_id))
    state["current_streaming_response"] = state.get("current_streaming_response", "")
    state["is_streaming"] = state.get("is_streaming", False)
    state["current_command_output"] = state.get("current_command_output", "")
    created_files = state.get("created_files", [])
    project_files = state.get("project_files_to_create", [])
    if project_files:
        created_set = {f.get("path") for f in created_files}
        completed = sum(1 for f in project_files if (f.get("path") if isinstance(f, dict) else f) in created_set)
        state["files_progress"] = round(completed / len(project_files) * 100)
    else:
        state["files_progress"] = 100 if created_files else 0
    return jsonify(state)


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    signal_task_stop(task_id)
    clear_checkpoint(WORKSPACE_DIR, task_id)
    task_path = get_task_path(task_id)
    try:
        terminate_task_process_groups(task_id)
    except Exception:
        pass
    try:
        terminate_task_http_servers(task_id)
    except Exception:
        pass
    if os.path.exists(task_path):
        try:
            shutil.rmtree(task_path)
        except Exception as e:
            return jsonify({"error": f"Failed to remove task directory: {str(e)}"}), 500
    active_threads.pop(task_id, None)
    task_stop_events.pop(task_id, None)
    task_locks.pop(task_id, None)
    # Notify WebSocket clients
    try:
        emit_tasks_list_update()
        emit_dashboard_update()
    except Exception:
        pass
    return jsonify({"success": True})


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

    if action == "force_complete":
        status = data.get("status", "completed")
        reason = data.get("reason", "Manually finished by user.")

        state["execution_log"].append(
            {
                "step": state.get("step", 0) + 1,
                "role": "system",
                "content": f"🏁 Task manually marked as {status.upper()}: {reason}",
            }
        )

        state["status"] = status
        state["details"] = reason
        state["proposed_tool"] = None

        try:
            outcome = "SUCCESS" if status == "completed" else "FAILED"
            add_task_history(MEMORY_DIR, state["task"], outcome, reason[:200])
        except Exception:
            pass

        try:
            trigger_self_improvement(task_id, state)
            trigger_readme_generation(task_id, state)
        except Exception:
            pass

        save_task_state(task_id, state)

        if task_id in active_threads:
            del active_threads[task_id]

        return jsonify(state)

    if action == "resume_auto":
        if state.get("mode") != "auto":
            return jsonify({"error": "Task is not in auto mode"}), 400

        state["status"] = "running"
        save_task_state(task_id, state)

        thread = active_threads.get(task_id)
        if not thread or not thread.is_alive():
            ensure_task_stop_event(task_id)
            thread = threading.Thread(target=background_execution_loop, args=(task_id,))
            thread.daemon = True
            thread.start()
            active_threads[task_id] = thread

        return jsonify(state)

    if action == "resume":
        checkpoint = load_checkpoint(WORKSPACE_DIR, task_id)
        if checkpoint:
            state = restore_checkpoint_into_state(checkpoint, state)
            clear_checkpoint(WORKSPACE_DIR, task_id)
            state["is_streaming"] = False
            state["current_streaming_response"] = ""
            # Clear proposed_tool so the engine re-evaluates the next action
            state["proposed_tool"] = None
            resolution = (
                "Resumed from checkpoint at stage '{stage}', step {step}".format(
                    stage=checkpoint.get("stage", "unknown"),
                    step=checkpoint.get("step", 0),
                )
            )
            state["details"] = resolution
            state["execution_log"].append(
                {
                    "step": state.get("step", 0) + 1,
                    "role": "system",
                    "content": f"🔄 {resolution}",
                }
            )

        if state.get("status") in ("completed", "failed"):
            return jsonify(state)

        state["status"] = "running"
        save_task_state(task_id, state)
        _start_background_thread(task_id)

        return jsonify(state)

    # Handle inject on completed/failed tasks: reset and re-run with new prompt
    if action == "inject" and state.get("status") in ("completed", "failed"):
        # Preserve created_files across re-initializations
        preserved_created_files = state.get("created_files", [])
        
        state["proposed_tool"] = {
            "name": "generate_plan",
            "args": {},
        }
        state["stage"] = "generating_plan"
        state["step"] = 0
        state["plan"] = None
        state["steps"] = []
        state["current_step_idx"] = 0
        state["completed_step_summaries"] = []
        state["messages"] = []
        state["last_raw_response"] = None
        state["last_tool_result"] = None
        state["last_user_intervention"] = user_prompt
        state["current_streaming_response"] = ""
        state["is_streaming"] = False
        state["supervision_review_summary"] = None
        state["supervision_status"] = "idle"
        state["supervision_reason"] = None
        state["supervision_last_review"] = None
        state["supervision_log"] = []
        state["errors_encountered"] = []
        state["details"] = None
        state["task"] = user_prompt
        state["provider_type"] = "llamacpp"
        state["llamacpp_url"] = get_provider_url("llamacpp")
        state["created_files"] = preserved_created_files
        state["project_structure"] = None
        state["project_files_to_create"] = []
        state["execution_log"].append(
            {
                "step": 0,
                "role": "system",
                "content": f"🔄 Task re-initialized with new prompt: {user_prompt}",
            }
        )
        state["status"] = "running"

        # Delete old state file so save_task_state's completed/failed guard
        # does not override the status back to completed/failed
        task_state_file = os.path.join(get_task_path(task_id), "task_state.json")
        if os.path.exists(task_state_file):
            os.remove(task_state_file)
        save_task_state(task_id, state)

        # Kick off the background loop
        def _auto_restart():
            background_execution_loop(task_id)
        ensure_task_stop_event(task_id)
        thread = threading.Thread(target=_auto_restart)
        thread.daemon = True
        thread.start()
        active_threads[task_id] = thread

        return jsonify(state)

    # Handle inject directly when a background thread is running (auto mode)
    existing_thread = active_threads.get(task_id)
    if existing_thread and existing_thread.is_alive():
        if action == "inject" and user_prompt:
            state["execution_log"].append(
                {
                    "step": state.get("step", 0),
                    "role": "user_intervention",
                    "content": user_prompt,
                }
            )
            state["last_user_intervention"] = user_prompt
            if state.get("messages"):
                state["messages"].append(
                    {
                        "role": "user",
                        "content": f"USER INTERVENTION / INSTRUCTION:\n{user_prompt}",
                    }
                )
            save_task_state(task_id, state)
            return jsonify(state)
        return jsonify(load_task_state(task_id) or state)

    # Mark as processing immediately so the UI knows work is underway
    state["status"] = "processando"
    save_task_state(task_id, state)

    def _run_step_in_background():
        result = run_agent_step_sync(
            task_id, action=action, modified_tool=modified_tool, user_prompt=user_prompt
        )
        # If auto mode and still running after inject, keep the loop going
        if (
            action == "inject"
            and result
            and result.get("mode") in ("auto", "auto-whatsapp")
            and result.get("status") == "running"
        ):
            background_execution_loop(task_id)

    ensure_task_stop_event(task_id)
    thread = threading.Thread(target=_run_step_in_background)
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
        state["status"] = "failed"
        state["details"] = "Task paused by user."
        save_task_state(task_id, state)

    return jsonify(state)


@app.route("/api/tasks/<task_id>/stop", methods=["POST"])
def stop_task(task_id):
    state = load_task_state(task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    if state["status"] not in ("running", "processando"):
        return jsonify({"error": "Task is not currently running"}), 400

    state["status"] = "failed"
    state["details"] = "Task stopped by user"
    state["proposed_tool"] = None
    save_task_state(task_id, state)

    signal_task_stop(task_id)
    try:
        terminate_task_process_groups(task_id)
    except Exception:
        pass
    try:
        terminate_task_http_servers(task_id)
    except Exception:
        pass

    return jsonify(state)


@app.route("/api/tasks/<task_id>/continue", methods=["POST"])
def continue_task(task_id):
    state = load_task_state(task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    # Only allow continue for failed tasks
    if state.get("status") != "failed":
        return jsonify({"error": "Only failed tasks can be continued"}), 400

    # Kill any old thread (best-effort)
    if task_id in active_threads:
        del active_threads[task_id]

    # Keep existing plan and assess what was already done
    existing_plan = state.get("plan")
    existing_steps = state.get("steps", [])
    completed_summaries = state.get("completed_step_summaries", [])
    last_step = state.get("current_step_idx", 0)

    # Archive failure info before clearing (truncate details to avoid context bloat)
    raw_detail = state.get("details") or ""
    archived = {
        "attempt": len(state.get("failure_history", [])) + 1,
        "errors": state.get("errors_encountered", []),
        "details": (raw_detail[:200] + "..." if len(raw_detail) > 200 else raw_detail),
        "stage": state.get("stage"),
        "step": last_step,
    }
    failure_history = state.get("failure_history", [])
    failure_history.append(archived)
    state["failure_history"] = failure_history

    state["status"] = "running"
    state["stage"] = "executing_steps"
    state["stage_retries"] = 0
    state["messages"] = []
    state["errors_encountered"] = []
    state["last_raw_response"] = None
    state["last_tool_result"] = None
    state["last_user_intervention"] = None
    state["current_streaming_response"] = ""
    state["is_streaming"] = False
    state["details"] = None

    if existing_steps and existing_plan:
        all_done = last_step >= len(existing_steps)
        resume_step = min(last_step, len(existing_steps) - 1)
        state["plan"] = existing_plan
        state["steps"] = existing_steps
        state["current_step_idx"] = resume_step if not all_done else len(existing_steps)
        state["step"] = 0
        state["completed_step_summaries"] = completed_summaries

        if all_done:
            planned = state.get("project_files_to_create", [])
            created = state.get("created_files", [])
            created_set = {f.get("path", "") for f in created}
            missing = [f for f in planned if f.get("path", "") not in created_set]

            if missing:
                missing_paths = [f.get("path") for f in missing]
                file_list = "\n".join(f"- {p}" for p in missing_paths)
                step_desc = (
                    f"Create files still missing from the project structure:\n{file_list}\n\n"
                    "Forneça conteúdo completo para cada arquivo. Não é necessário recriar arquivos já existentes."
                )
                state["project_structure"] = json.dumps(missing_paths)
                state["project_files_to_create"] = missing
                state["steps"].append(step_desc)
                state["current_step_idx"] = len(state["steps"]) - 1
                state["proposed_tool"] = {
                    "name": "execute_step",
                    "args": {
                        "step_num": len(state["steps"]),
                        "description": step_desc,
                    },
                }
                state["status"] = "running"
                state["execution_log"].append({
                    "step": state["step"],
                    "role": "system",
                    "content": f"📋 {len(missing)} arquivo(s) planejado(s) ainda não foram criados. Nova etapa adicionada para criá-los.",
                })
            else:
                state["stage"] = "completed"
                state["status"] = "completed"
                state["details"] = "All steps executed successfully."
                state["messages"] = []
                state["proposed_tool"] = None
                try:
                    add_task_history(
                        MEMORY_DIR, state["task"], "SUCCESS",
                        "All steps executed successfully."
                    )
                except Exception:
                    pass
                if state.get("errors_encountered"):
                    trigger_self_improvement(state["task_id"], state)
                trigger_readme_generation(state["task_id"], state)
        else:
            completed_text = ""
            if completed_summaries:
                completed_text = "\nPreviously completed steps:\n"
                for idx, s in enumerate(completed_summaries):
                    completed_text += f"  Step {idx+1}: {s}\n"

            state["messages"] = [
                {
                    "role": "system",
                    "content": f"""We are continuing a partially completed task.

EXISTING PLAN:
{existing_plan}

{completed_text}
Remaining steps to execute:
{chr(10).join(f"Step {i+1}: {s}" for i, s in enumerate(existing_steps) if i >= resume_step)}

Your first action must be to explore what already exists:
1. Read the plan above carefully
2. List the output directory to see what files exist: list_dir path="."
3. Read key files to understand the current state
4. Determine what is still needed
5. Continue implementing from where it left off

IMPORTANT: 'write_file' automatically creates parent directories. You do NOT need to create directories first - just write files directly.

Do NOT generate a new plan. Follow the existing plan above.""",
                }
            ]
            state["proposed_tool"] = {
                "name": "execute_step",
                "args": {"step_num": resume_step + 1, "description": existing_steps[resume_step]},
            }
    else:
        # No plan exists - start fresh
        state["stage"] = "generating_plan"
        state["step"] = 0
        state["proposed_tool"] = {"name": "generate_plan", "args": {}}

    state["execution_log"].append(
        {
            "step": state.get("step", 0),
            "role": "system",
            "content": "🔄 Task continued by user.",
        }
    )

    # Clear stop signal so save_task_state and background loops work
    task_stop_events.pop(task_id, None)

    # Remove the old state file so save_task_state's override logic
    # (which forces status back to the on-disk value for completed/failed tasks)
    # does not undo the status reset.
    task_state_file = os.path.join(get_task_path(task_id), "task_state.json")
    if os.path.exists(task_state_file):
        os.remove(task_state_file)

    save_task_state(task_id, state)

    mode = state.get("mode", "auto")

    def _continue_initial_step():
        try:
            run_agent_step_sync(task_id, action="approve")
            background_execution_loop(task_id)
        except Exception as e:
            print(
                f"[Continue] _continue_initial_step crashed for {task_id}: {e}",
                flush=True,
            )
            try:
                s = load_task_state(task_id)
                if s and s.get("status") not in ("completed", "failed"):
                    s["status"] = "failed"
                    s["proposed_tool"] = None
                    s["details"] = f"Internal continue error: {e}"
                    save_task_state(task_id, s)
            except Exception:
                pass

    ensure_task_stop_event(task_id)
    thread = threading.Thread(target=_continue_initial_step)
    thread.daemon = True
    thread.start()
    active_threads[task_id] = thread

    return jsonify(state)


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


@app.route("/api/tasks/<task_id>/files/raw/<path:file_path>", methods=["GET"])
def raw_task_file(task_id, file_path):
    task_path = get_task_path(task_id)
    target_file = os.path.abspath(os.path.join(task_path, file_path))

    # Security check
    if not target_file.startswith(os.path.abspath(task_path)):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(target_file):
        return jsonify({"error": "File does not exist"}), 404

    if os.path.isdir(target_file):
        return jsonify({"error": "Path is a directory"}), 400

    mime_type, _ = mimetypes.guess_type(target_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    return send_file(target_file, mimetype=mime_type, as_attachment=False)


@app.route("/api/tasks/<task_id>/files/edit", methods=["POST"])
def edit_task_file(task_id):
    data = request.json or {}
    path = data.get("path")
    content = data.get("content")

    if not path or content is None:
        return jsonify({"error": "File path and content are required"}), 400

    task_path = get_task_path(task_id)
    output_dir = os.path.abspath(os.path.join(task_path, "output"))

    if os.path.isabs(path):
        return jsonify({"error": "Access denied"}), 403

    normalized_path = path
    if normalized_path.startswith("output" + os.sep):
        normalized_path = normalized_path[len("output" + os.sep) :]

    target_file = os.path.abspath(os.path.join(output_dir, normalized_path))

    # Security check: enforce output directory only
    if not target_file.startswith(output_dir):
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


def find_html_files(output_dir):
    """Find all HTML files in the output directory recursively."""
    html_files = []
    if not os.path.exists(output_dir):
        return html_files
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.endswith(('.html', '.htm')):
                rel_path = os.path.relpath(os.path.join(root, f), output_dir)
                html_files.append(rel_path)
    return sorted(html_files)


@app.route("/api/tasks/<task_id>/html-files", methods=["GET"])
def get_task_html_files(task_id):
    task_path = get_task_path(task_id)
    output_dir = os.path.join(task_path, "output")
    html_files = find_html_files(output_dir)
    return jsonify({"html_files": html_files})


@app.route("/api/tasks/<task_id>/preview/<path:file_path>", methods=["GET"])
def preview_html_file(task_id, file_path):
    return _serve_task_output_file(task_id, file_path)


@app.route("/api/servers", methods=["GET"])
def list_active_servers():
    """List all active HTTP servers started by the agent."""
    try:
        servers = list_http_servers()
        return jsonify({"servers": servers})
    except Exception as e:
        return jsonify({"error": str(e), "servers": []}), 500


@app.route("/api/servers", methods=["POST"])
def manage_active_servers():
    """Stop an HTTP server. Body: { "server_id": "...", "task_id": "..." }"""
    data = request.json or {}
    server_id = (data.get("server_id") or "").strip()
    task_id = (data.get("task_id") or "").strip() or None
    if not server_id:
        return jsonify({"error": "server_id is required"}), 400
    if stop_http_server_tool(server_id, task_id):
        return jsonify({"success": True, "server_id": server_id})
    return jsonify({"error": f"No active HTTP server with id '{server_id}'"}), 404


@app.route("/tasks/<task_id>/output", methods=["GET"])
@app.route("/tasks/<task_id>/output/", methods=["GET"])
def serve_task_output_dir(task_id):
    task_path = get_task_path(task_id)
    output_dir = os.path.join(task_path, "output")
    index_file = os.path.join(output_dir, "index.html")

    if os.path.isdir(output_dir) and os.path.exists(index_file):
        return send_file(index_file, mimetype="text/html", as_attachment=False)

    if os.path.isdir(output_dir):
        files = sorted([f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))])
        html = "<html><head><title>Output Directory</title></head><body><h1>Files in output/</h1><ul>"
        for f in files:
            html += f'<li><a href="/{f}">{f}</a></li>'
        html += "</ul></body></html>"
        return html, 200, {"Content-Type": "text/html"}

    return jsonify({"error": "Output directory not found"}), 404


@app.route("/tasks/<task_id>/<path:file_path>", methods=["GET"])
def serve_task_file(task_id, file_path):
    return _serve_task_output_file(task_id, file_path)


def _serve_task_output_file(task_id, file_path):
    task_path = get_task_path(task_id)
    output_dir = os.path.abspath(os.path.join(task_path, "output"))
    target_file = os.path.abspath(os.path.join(output_dir, file_path))

    if not target_file.startswith(output_dir):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(target_file):
        return jsonify({"error": "File does not exist"}), 404

    if os.path.isdir(target_file):
        index_file = os.path.join(target_file, "index.html")
        if os.path.exists(index_file):
            return send_file(index_file, mimetype="text/html", as_attachment=False)
        files = sorted([f for f in os.listdir(target_file) if os.path.isfile(os.path.join(target_file, f))])
        html = "<html><head><title>Output Directory</title></head><body><h1>Files in output/</h1><ul>"
        for f in files:
            html += f'<li><a href="/{f}">{f}</a></li>'
        html += "</ul></body></html>"
        return html, 200, {"Content-Type": "text/html"}

    mime_type, _ = mimetypes.guess_type(target_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    return send_file(target_file, mimetype=mime_type, as_attachment=False)


def mark_incomplete_task_after_restart(task_id, state):
    """
    Mark a task incomplete when the application restarts.
    If a checkpoint exists, restores the checkpoint for seamless resume.
    Otherwise, falls back to safe defaults.
    """
    state["is_streaming"] = False

    # Try to restore from checkpoint for granular resume
    checkpoint = load_checkpoint(WORKSPACE_DIR, task_id)
    if checkpoint:
        restore_checkpoint_into_state(checkpoint, state)
        state["proposed_tool"] = None
        state["is_streaming"] = False
        state["status"] = "running"
        state["details"] = (
            "Task was interrupted by application restart. "
            "Auto-resuming from last checkpoint."
        )
        print(
            f"[Startup] Restored task {task_id} from checkpoint, resuming...",
            flush=True,
        )
        clear_checkpoint(WORKSPACE_DIR, task_id)
    else:
        state["proposed_tool"] = None
        state["status"] = "running"
        state["details"] = (
            "Task was interrupted by application restart. "
            "No checkpoint available. Auto-resuming from task state."
        )
        print(
            f"[Startup] Reset task {task_id} to running (no checkpoint), resuming...",
            flush=True,
        )

    save_task_state(task_id, state)


def resume_incomplete_tasks():
    """
    Scans workspace for incomplete tasks and resumes them from checkpoints.
    All incomplete tasks with checkpoints are automatically restarted in the background.
    """
    print("[Startup] Scanning for incomplete tasks to resume...", flush=True)
    if not os.path.exists(WORKSPACE_DIR):
        return
    for folder in os.listdir(WORKSPACE_DIR):
        if not folder.startswith("task_") or not os.path.isdir(
            os.path.join(WORKSPACE_DIR, folder)
        ):
            continue
        try:
            state = load_task_state(folder)
            if not state:
                continue

            status = state.get("status")
            mode = state.get("mode", "step")
            task_id = state.get("task_id")

            if status in ("running", "processando"):
                print(
                    f"[Startup] Found incomplete task: {task_id} (status: {status}, mode: {mode})",
                    flush=True,
                )
                mark_incomplete_task_after_restart(task_id, state)

                # Start a background execution thread for all restored tasks
                restored = load_task_state(task_id)
                if restored and restored.get("status") == "running":
                    print(
                        f"[Startup] Launching background resume for task {task_id}",
                        flush=True,
                    )
                    _start_background_thread(task_id)
        except Exception as e:
            print(
                f"[Startup] Error processing task folder {folder}: {e}",
                flush=True,
            )


def _start_background_thread(task_id):
    """Start a background execution thread for a task (if not already running)."""
    existing = active_threads.get(task_id)
    if existing and existing.is_alive():
        return

    def _run():
        try:
            background_execution_loop(task_id)
        except Exception as e:
            print(f"[Background] Loop crashed for {task_id}: {e}", flush=True)
            try:
                s = load_task_state(task_id)
                if s and s.get("status") not in ("completed", "failed"):
                    s["status"] = "failed"
                    s["details"] = f"Background loop error: {e}"
                    save_task_state(task_id, s)
            except Exception:
                pass

    ensure_task_stop_event(task_id)
    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
    active_threads[task_id] = thread


DIST_DIR = os.path.join(PROJECT_ROOT, "dist")


@app.route("/assets/<path:filename>")
def serve_frontend_assets(filename):
    assets_dir = os.path.join(DIST_DIR, "assets")
    file_path = os.path.abspath(os.path.join(assets_dir, filename))
    if not file_path.startswith(assets_dir):
        return "Forbidden", 403
    if not os.path.exists(file_path):
        return "Not found", 404
    mime_type, _ = mimetypes.guess_type(file_path)
    return send_file(file_path, mimetype=mime_type or "application/octet-stream")


@app.route("/", defaults={"rest": None})
@app.route("/<path:rest>")
def serve_frontend(rest):
    if rest is not None:
        file_path = os.path.abspath(os.path.join(DIST_DIR, rest))
        if file_path.startswith(DIST_DIR) and os.path.exists(file_path) and not os.path.isdir(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            return send_file(file_path, mimetype=mime_type or "application/octet-stream")
    return send_file(os.path.join(DIST_DIR, "index.html"))


if __name__ == "__main__":
    # Disable debug/reloader when running in production or under PM2.
    # We also disable the auto-reloader (use_reloader=False) to prevent loop restarts
    # when the agent writes workspace or memory files.
    flask_env = os.environ.get("FLASK_ENV", "development")
    debug_mode = flask_env == "development" and os.environ.get("DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", "5000"))

    # Resume any tasks that were left incomplete before starting Flask
    resume_incomplete_tasks()

    socketio.run(app, host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)
