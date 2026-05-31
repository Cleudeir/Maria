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
from maria.provider.base import LoopDetectedError
from maria.step_checkpoint import (
    save_checkpoint,
    load_checkpoint,
    restore_checkpoint_into_state,
    clear_checkpoint,
)
from maria.agents.analyze_parallelism import analyze_parallelism

MAX_STAGE_RETRIES = 3

# Set server environment variable for bypassing security console prompts
os.environ["MARIA_SERVER"] = "1"

app = Flask(__name__)

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


def get_task_lock(task_id):
    if task_id not in task_locks:
        task_locks[task_id] = threading.Lock()
    return task_locks[task_id]


def get_task_path(task_id):
    return os.path.join(WORKSPACE_DIR, task_id)


def load_task_state(task_id):
    path = os.path.join(get_task_path(task_id), "task_state.json")
    with get_task_lock(task_id):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None


def save_task_state(task_id, state):
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
                if current_disk_state.get("status") in ("completed", "failed"):
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
    prompt_lines = [
        "Use only the minimum context required for this step. Do not resend the entire conversation history.",
        "You are an agentic assistant executing a single step at a time.",
        "You should output your reasoning and the next tool action in JSON format.",
        "\n",
        "Task:\n" + task_prompt,
        f"\nCurrent step: {state.get('step', 0) + 1} of {state.get('max_steps', 0)}.\n",
        "ORGANIZATION: Split code into separate files by domain/responsibility. "
        "Each file should contain related functions with a single purpose. "
        "Each function must have one clear responsibility.",
    ]

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
    if "verification_report" not in state:
        state["verification_report"] = None
    if "verification_verdict" not in state:
        state["verification_verdict"] = None

    if "stage_retries" not in state:
        state["stage_retries"] = 0

    if state["status"] not in (
        "running",
        "awaiting_intervention",
        "auto",
        "processando",
    ):
        if action != "inject":
            return state
        if state["status"] in ("completed", "failed"):
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
            state["verification_report"] = None
            state["verification_verdict"] = None
            state["errors_encountered"] = []
            state["details"] = None
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
            if state.get("mode") == "auto":
                state["status"] = "running"
            else:
                state["status"] = "awaiting_intervention"
            # Delete old state file so save_task_state's completed/failed guard
            # does not override the status back to completed/failed
            task_state_file = os.path.join(get_task_path(task_id), "task_state.json")
            if os.path.exists(task_state_file):
                os.remove(task_state_file)
            save_task_state(task_id, state)
            return state

    if action in ("inject", "approve", "modify"):
        state["status"] = "processando"
        save_task_state(task_id, state)

    workspace_path = get_task_path(task_id)
    executor = ToolExecutor(workspace_path)
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

            # Transition to creating steps
            state["stage"] = "creating_steps"
            state["stage_retries"] = 0
            state["proposed_tool"] = {
                "name": "create_steps",
                "args": {},
            }
            if state["mode"] != "auto":
                state["status"] = "awaiting_intervention"
            else:
                state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, task_id, state)
        except LoopDetectedError as e:
            state["stage_retries"] += 1
            if state["stage_retries"] >= MAX_STAGE_RETRIES:
                state["status"] = "failed"
                state["proposed_tool"] = None
                state["details"] = f"Failed to generate plan: {e}"
            else:
                state["details"] = (
                    f"Retry {state['stage_retries']}/{MAX_STAGE_RETRIES} - {e}"
                )
                state["status"] = "running"
            print(
                f"[Stage] generating_plan loop detected for {task_id}: retry {state['stage_retries']}/{MAX_STAGE_RETRIES}",
                flush=True,
            )
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to generate plan: {e}"
            print(f"[Stage] generating_plan failed for {task_id}: {e}", flush=True)

    elif state["stage"] == "creating_steps":
        try:
            callback = _start_streaming()
            try:
                plan_for_steps = state["plan"]
                if state.get("last_user_intervention"):
                    plan_for_steps += f"\n\nAdditional instructions: {state['last_user_intervention']}"
                steps = agent.create_steps(plan_for_steps, stream_callback=callback, complexity=state.get("complexity", "complex"))
            finally:
                _stop_streaming()
            state["steps"] = steps
            try:
                save_execution_plan_steps(workspace_path, steps)
            except Exception:
                pass
            steps_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"🛠️ Stage 2 Complete: Execution Steps:\n{steps_str}",
                }
            )

            if not steps:
                raise ValueError("No steps were generated by the LLM.")

            # Transition to analyzing parallelism (or directly to executing_steps for simple tasks)
            if state.get("complexity") == "simple":
                state["stage"] = "executing_steps"
                state["parallel_groups"] = [[i] for i in range(len(steps))]
            else:
                state["stage"] = "analyzing_parallelism"
            state["stage_retries"] = 0
            state["current_step_idx"] = 0
            state["completed_step_summaries"] = []

            state["proposed_tool"] = {
                "name": "execute_step",
                "args": {"step_num": 1, "description": steps[0]},
            }
            if state["mode"] != "auto":
                state["status"] = "awaiting_intervention"
            else:
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
            print(
                f"[Stage] creating_steps loop detected for {task_id}: retry {state['stage_retries']}/{MAX_STAGE_RETRIES}",
                flush=True,
            )
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to create steps: {e}"
            print(f"[Stage] creating_steps failed for {task_id}: {e}", flush=True)

    elif state["stage"] == "analyzing_parallelism":
        try:
            callback = _start_streaming()
            try:
                parallel_groups = analyze_parallelism(
                    state["steps"], get_generate_fn=client.provider.generate, stream_callback=callback
                )
            finally:
                _stop_streaming()
            state["parallel_groups"] = parallel_groups
            groups_str = ", ".join([str(g) for g in parallel_groups])
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"🔀 Stage 2.5 Complete: Parallel Groups: {groups_str}",
                }
            )
            # Transition to executing steps
            state["stage"] = "executing_steps"
            state["stage_retries"] = 0
            state["current_step_idx"] = 0
            state["completed_step_summaries"] = []
            state["proposed_tool"] = {
                "name": "execute_step",
                "args": {"step_num": 1, "description": state["steps"][0]},
            }
            if state["mode"] != "auto":
                state["status"] = "awaiting_intervention"
            else:
                state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, task_id, state)
        except LoopDetectedError as e:
            state["stage_retries"] += 1
            if state["stage_retries"] >= MAX_STAGE_RETRIES:
                state["status"] = "failed"
                state["proposed_tool"] = None
                state["details"] = f"Failed to analyze parallelism: {e}"
            else:
                state["details"] = f"Retry {state['stage_retries']}/{MAX_STAGE_RETRIES} - {e}"
                state["status"] = "running"
            print(f"[Stage] analyzing_parallelism loop detected for {task_id}: retry {state['stage_retries']}/{MAX_STAGE_RETRIES}", flush=True)
        except Exception as e:
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = f"Failed to analyze parallelism: {e}"
            print(f"[Stage] analyzing_parallelism failed for {task_id}: {e}", flush=True)

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
                    state["stage"] = "verifying"
                    state["messages"] = []

                save_checkpoint(WORKSPACE_DIR, task_id, state)

            else:
                # Sequential execution (single step)
                completed_context = ""
                if state["completed_step_summaries"]:
                    completed_context = "\nPreviously completed steps:\n"
                    for idx, summary in enumerate(state["completed_step_summaries"], 1):
                        completed_context += f"Step {idx}: {summary}\n"

                state["messages"] = [
                    {"role": "system", "content": system_message},
                    {
                        "role": "user",
                        "content": f"""We are executing a multi-stage plan.
Complete Plan:
{state["plan"]}
{completed_context}
Current Step: Step {step_num} of {total_steps}
Step Description: {steps[curr_idx]}

{"Do exactly what is asked. Do NOT over-engineer. Do NOT create extra files or architecture." if state.get("complexity") == "simple" else "ORGANIZATION RULE:\n- Split code into separate files by domain/responsibility\n- Each file should contain related functions with a single purpose\n- Each function must have one clear responsibility"}

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
                    tool_result = execute_tool_call(executor, tool_name, args)
                else:
                    applied_action_descr = "Approved & continued"

            elif action == "modify" and modified_tool:
                tool_name = modified_tool.get("name")
                args = modified_tool.get("args", {})
                applied_action_descr = f"Modified & Executed: {tool_name} {args}"
                tool_result = execute_tool_call(executor, tool_name, args)

            if tool_result is not None:
                if tool_result.startswith("Error:"):
                    state["errors_encountered"].append(
                        {
                            "step": state["step"],
                            "tool": tool_name,
                            "args": args,
                            "error": tool_result,
                        }
                    )
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
                    if "exited with code 127" in tool_result:
                        tool_content += (
                            f"\n\nADVICE: The command was not found (exit code 127). "
                            f"This means the executable is not installed or not in PATH.\n"
                            f"SOLUTIONS:\n"
                            f"1. Use npx to run local packages: e.g., 'npx jest' instead of 'jest'\n"
                            f"2. Install dependencies first: 'npm install' or 'npm ci'\n"
                            f"3. Check if the command name is correct\n"
                            f"4. For test runners, always use npx: 'npx jest', 'npx vitest', etc.\n"
                            f"Do NOT retry the same command - it will fail again. Try a different approach."
                        )
                    else:
                        tool_content += (
                            f"\n\nADVICE: The tool execution failed. "
                            f"Check the error and path and try a different approach. "
                            f"If a file does not exist, create it first with write_file (parent dirs are auto-created). "
                            f"Review what went wrong and correct your approach."
                        )
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
        try:
            callback = _start_streaming()
            try:
                plan_for_verify = state["plan"]
                if state.get("last_user_intervention"):
                    plan_for_verify += f"\n\nAdditional instructions from user: {state['last_user_intervention']}"
                verdict, report = agent.verify_execution(
                    plan_for_verify, state["steps"], stream_callback=callback
                )
            finally:
                _stop_streaming()
            state["execution_log"].append(
                {
                    "step": state["step"],
                    "role": "system",
                    "content": f"🔍 Stage 3 Complete: Final Verification Report:\n{report}\n\nVerdict: {verdict}",
                }
            )

            try:
                with open(
                    os.path.join(workspace_path, "verification_report.md"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(f"# Verification Report\n\nVerdict: {verdict}\n\n{report}")
            except Exception:
                pass

            state["proposed_tool"] = None
            state["verification_report"] = report
            state["verification_verdict"] = verdict
            if state.get("verification_verdict") == "SUCCESS":
                state["status"] = "completed"
                state["details"] = "Verification passed."
                try:
                    add_task_history(
                        MEMORY_DIR, state["task"], "SUCCESS", "Verification passed."
                    )
                except Exception:
                    pass
            else:
                state["status"] = "failed"
                state["details"] = f"Verification failed. Verdict: {state.get('verification_verdict')}"
                try:
                    add_task_history(
                        MEMORY_DIR,
                        state["task"],
                        "FAILED",
                        f"Verdict: {state.get('verification_verdict')}",
                    )
                except Exception:
                    pass
            save_checkpoint(WORKSPACE_DIR, task_id, state)
            trigger_self_improvement(task_id, state)
        except LoopDetectedError as e:
            state["stage_retries"] += 1
            if state["stage_retries"] >= MAX_STAGE_RETRIES:
                state["status"] = "failed"
                state["details"] = f"Failed to verify execution: {e}"
                trigger_self_improvement(task_id, state)
            else:
                state["details"] = (
                    f"Retry {state['stage_retries']}/{MAX_STAGE_RETRIES} - {e}"
                )
                state["status"] = "running"
            print(
                f"[Stage] verifying loop detected for {task_id}: retry {state['stage_retries']}/{MAX_STAGE_RETRIES}",
                flush=True,
            )
        except Exception as e:
            state["status"] = "failed"
            state["details"] = f"Failed to verify execution: {e}"
            trigger_self_improvement(task_id, state)

    save_task_state(task_id, state)
    return state


def run_llm_for_tool(state, client):
    """
    Helper function to query LLM for the next tool call during step execution.
    Handles finish_task to transition steps or stages.
    """
    max_retries = 10

    # Loop detection: track recent tool calls to detect repeated patterns
    if "_recent_tool_calls" not in state:
        state["_recent_tool_calls"] = []
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

        try:
            response_text = client.chat(
                state["messages"],
                temperature=0.1,
                stream_callback=_streaming_callback,
            )
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

            # Also detect if no finish_task after 5 tool calls in same step
            non_finish_calls = [c for c in recent_tool_calls if not c.startswith("finish_task:")]
            if len(non_finish_calls) >= 5:
                # Check if any file writing actually happened
                write_calls = [c for c in non_finish_calls if c.startswith("write_file:") or c.startswith("edit_file:")]
                if len(write_calls) == 0:
                    curr_idx = state.get("current_step_idx", 0)
                    step_desc = state["steps"][curr_idx] if state.get("steps") else "current step"
                    nudge_msg = (
                        f"WARNING: You have made {len(non_finish_calls)} tool calls without writing any files "
                        f"or calling finish_task. You are likely stuck in an analysis loop.\n\n"
                        f"CURRENT STEP: {step_desc}\n\n"
                        f"If you have enough information, start implementing by calling write_file or edit_file. "
                        f"If the step is already complete, call finish_task immediately."
                    )
                    state["messages"].append({"role": "user", "content": nudge_msg})
                    state["execution_log"].append(
                        {
                            "step": state["step"],
                            "role": "tool_result",
                            "content": f"WARNING: Analysis loop detected - nudging toward implementation.",
                        }
                    )
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
                f"Available tools: list_dir, read_file, write_file, edit_file, edit_lines, grep, find_in_files, grep_output, run_command, finish_task\n\n"
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

            state["status"] = "awaiting_intervention"
            state["proposed_tool"] = None
            return state

        if tool_name == "finish_task":
            recent_tool_calls.clear()
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
                if state.get("mode") != "auto":
                    state["status"] = "awaiting_intervention"
                else:
                    state["status"] = "running"
            else:
                state["stage"] = "verifying"
                state["stage_retries"] = 0
                state["proposed_tool"] = {
                    "name": "verify_execution",
                    "args": {},
                }
                if state.get("mode") != "auto":
                    state["status"] = "awaiting_intervention"
                else:
                    state["status"] = "running"
            save_checkpoint(WORKSPACE_DIR, state["task_id"], state)
            return state

        state["proposed_tool"] = {"name": tool_name, "args": args}
        if state.get("mode") != "auto":
            state["status"] = "awaiting_intervention"
        else:
            state["status"] = "running"
        save_checkpoint(WORKSPACE_DIR, state["task_id"], state)
        return state


def execute_tool_call(executor, name, args):
    if name == "list_dir":
        return executor.list_dir(args.get("path", "."))
    elif name == "read_file":
        return executor.read_file(args.get("path", ""))
    elif name == "write_file":
        return executor.write_file(args.get("path", ""), args.get("content", ""))
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
    elif name == "run_command":
        return executor.run_command(args.get("command", ""))
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


def background_execution_loop(task_id):
    """Loop execution steps in background for auto mode"""
    while True:
        if is_task_stopped(task_id):
            break
        state = load_task_state(task_id)
        if not state or state["status"] != "running":
            break

        if not state.get("proposed_tool"):
            state = run_agent_step_sync(task_id, action="inject", user_prompt=None)
            if is_task_stopped(task_id):
                break
            if (
                not state
                or state["status"] != "running"
                or not state.get("proposed_tool")
            ):
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
        else:
            state = run_agent_step_sync(task_id, action="approve")

        if not state or state["status"] in (
            "completed",
            "failed",
            "awaiting_intervention",
        ):
            break

        time.sleep(0.5)


# --- Flask API Routes ---


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
    model_think = data.get("model_think", False)
    provider_type = data.get("provider_type", "llamacpp")
    complexity = data.get("complexity", "complex")  # 'simple' or 'complex'

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
        "status": "running",  # always start running; step mode will pause after first stage
        "stage": "generating_plan",
        "step": 0,
        "max_steps": max_steps,
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
        "verification_report": None,
        "verification_verdict": None,
    }

    save_task_state(task_id, state)
    save_plan_overview(task_path, task_prompt, created_time_str)

    # 5. Always auto-start first step in background (both auto and step modes).
    # Step mode will pause at awaiting_intervention after the first stage completes.
    def _initial_step():
        try:
            run_agent_step_sync(task_id, action="approve")
            # For auto mode, continue the full loop after the first step
            if mode == "auto":
                background_execution_loop(task_id)
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

    ensure_task_stop_event(task_id)
    thread = threading.Thread(target=_initial_step)
    thread.daemon = True
    thread.start()
    active_threads[task_id] = thread

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
                "max_steps": 20,
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
                "verification_report": None,
                "verification_verdict": None,
            }
        else:
            return jsonify({"error": "Task not found"}), 404

    # Include output-only file tree for workspace pane
    state["file_tree"] = build_output_file_tree(get_task_path(task_id))
    state["current_streaming_response"] = state.get("current_streaming_response", "")
    state["is_streaming"] = state.get("is_streaming", False)
    return jsonify(state)


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    signal_task_stop(task_id)
    clear_checkpoint(WORKSPACE_DIR, task_id)
    task_path = get_task_path(task_id)
    if os.path.exists(task_path):
        try:
            shutil.rmtree(task_path)
        except Exception as e:
            return jsonify({"error": f"Failed to remove task directory: {str(e)}"}), 500
    active_threads.pop(task_id, None)
    task_stop_events.pop(task_id, None)
    task_locks.pop(task_id, None)
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

        if state.get("mode") == "auto":
            state["status"] = "running"
            save_task_state(task_id, state)
            _start_background_thread(task_id)
        else:
            state["status"] = "awaiting_intervention"
            save_task_state(task_id, state)

        return jsonify(state)

    # Handle inject on completed/failed tasks: reset and re-run with new prompt
    if action == "inject" and state.get("status") in ("completed", "failed"):
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
        state["verification_report"] = None
        state["verification_verdict"] = None
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
        state["execution_log"].append(
            {
                "step": 0,
                "role": "system",
                "content": f"🔄 Task re-initialized with new prompt: {user_prompt}",
            }
        )
        if state.get("mode") == "auto":
            state["status"] = "running"
        else:
            state["status"] = "awaiting_intervention"

        # Delete old state file so save_task_state's completed/failed guard
        # does not override the status back to completed/failed
        task_state_file = os.path.join(get_task_path(task_id), "task_state.json")
        if os.path.exists(task_state_file):
            os.remove(task_state_file)
        save_task_state(task_id, state)

        # For auto mode, kick off the background loop
        if state.get("mode") == "auto":
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
            and result.get("mode") == "auto"
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
        state["status"] = "awaiting_intervention"
        save_task_state(task_id, state)

    return jsonify(state)


@app.route("/api/tasks/<task_id>/continue", methods=["POST"])
def continue_task(task_id):
    state = load_task_state(task_id)
    if not state:
        return jsonify({"error": "Task not found"}), 404

    # Only allow continue for failed tasks
    if state.get("status") not in ("failed",):
        return jsonify({"error": "Only failed tasks can be continued"}), 400

    # Kill any old thread (best-effort)
    if task_id in active_threads:
        del active_threads[task_id]

    # Reset execution state but keep task description, mode and logs
    state["status"] = "running"
    state["stage"] = "generating_plan"
    state["stage_retries"] = 0
    state["step"] = 0
    state["messages"] = []
    state["errors_encountered"] = []
    state["proposed_tool"] = {
        "name": "generate_plan",
        "args": {},
    }
    state["last_raw_response"] = None
    state["last_tool_result"] = None
    state["last_user_intervention"] = None
    state["plan"] = None
    state["steps"] = []
    state["current_step_idx"] = 0
    state["completed_step_summaries"] = []
    state["current_streaming_response"] = ""
    state["is_streaming"] = False
    state["verification_report"] = None
    state["verification_verdict"] = None
    state["details"] = None
    state["execution_log"].append(
        {
            "step": 0,
            "role": "system",
            "content": "🔄 Task continued by user.",
        }
    )

    # Remove the old state file so save_task_state's override logic
    # (which forces status back to the on-disk value for completed/failed tasks)
    # does not undo the status reset.
    task_state_file = os.path.join(get_task_path(task_id), "task_state.json")
    if os.path.exists(task_state_file):
        os.remove(task_state_file)

    save_task_state(task_id, state)

    mode = state.get("mode", "step")

    def _continue_initial_step():
        try:
            run_agent_step_sync(task_id, action="approve")
            if mode == "auto":
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


def mark_incomplete_task_after_restart(task_id, state):
    """
    Mark a task incomplete when the application restarts.
    If a checkpoint exists, restores the checkpoint for seamless resume.
    Otherwise, falls back to safe defaults.
    """
    mode = state.get("mode", "step")
    state["is_streaming"] = False

    # Try to restore from checkpoint for granular resume
    checkpoint = load_checkpoint(WORKSPACE_DIR, task_id)
    if checkpoint:
        restore_checkpoint_into_state(checkpoint, state)
        # Clear proposed_tool to force LLM to re-evaluate on resume
        # (avoids re-executing a tool that may have already been applied)
        state["proposed_tool"] = None
        state["is_streaming"] = False

        if mode == "auto":
            state["status"] = "running"
            state["details"] = (
                "Task was interrupted by application restart. "
                "Auto-resuming from last checkpoint."
            )
            print(
                f"[Startup] Restored auto task {task_id} from checkpoint, resuming...",
                flush=True,
            )
        else:
            state["status"] = "awaiting_intervention"
            state["details"] = (
                "Task was interrupted by application restart. "
                "Checkpoint restored. Please review and resume execution."
            )
            print(
                f"[Startup] Restored step task {task_id} from checkpoint, awaiting user...",
                flush=True,
            )

        clear_checkpoint(WORKSPACE_DIR, task_id)
    else:
        if mode == "auto":
            state["status"] = "failed"
            state["proposed_tool"] = None
            state["details"] = (
                "Task was interrupted by application restart. "
                "No checkpoint available. Please restart the task manually."
            )
            print(
                f"[Startup] Marked auto task {task_id} as failed (no checkpoint)",
                flush=True,
            )
        else:
            state["status"] = "awaiting_intervention"
            state["details"] = (
                "Task was interrupted by application restart. "
                "No checkpoint available. Please review and resume execution manually."
            )
            print(
                f"[Startup] Reset step task {task_id} to awaiting_intervention (no checkpoint)",
                flush=True,
            )

    save_task_state(task_id, state)


def resume_incomplete_tasks():
    """
    Scans workspace for incomplete tasks and resumes them from checkpoints.
    Auto-mode tasks with checkpoints are automatically restarted in the background.
    Step-mode tasks are reset to awaiting_intervention for manual recovery.
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

                # For auto tasks that were successfully restored to running,
                # start a background execution thread
                restored = load_task_state(task_id)
                if restored and restored.get("status") == "running" and mode == "auto":
                    print(
                        f"[Startup] Launching background resume for auto task {task_id}",
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




if __name__ == "__main__":
    # Disable debug/reloader when running in production or under PM2.
    # We also disable the auto-reloader (use_reloader=False) to prevent loop restarts
    # when the agent writes workspace or memory files.
    flask_env = os.environ.get("FLASK_ENV", "development")
    debug_mode = flask_env == "development" and os.environ.get("DEBUG", "1") == "1"

    # Resume any tasks that were left incomplete before starting Flask
    resume_incomplete_tasks()

    app.run(host="0.0.0.0", port=5000, debug=debug_mode, use_reloader=False)
