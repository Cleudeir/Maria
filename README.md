# Maria

Maria is a self-improving agentic SLM (Small Language Model) system that autonomously completes coding tasks using Ollama. It follows a multi-stage pipeline: prompt improvement, planning, step creation, execution, verification, and supervisor review.

## Features

- **Multi-stage pipeline**: Improves prompts, generates plans, breaks into steps, executes, verifies, and reviews
- **Two execution modes**: `step` (manual approval per action) or `auto` (fully autonomous)
- **Tool use**: list_dir, read_file, write_file, run_command, finish_task
- **Self-improvement**: Learns from errors and stores lessons to prevent repeating mistakes
- **Memory system**: Persistent system prompts and lessons across runs
- **Task isolation**: Each task runs in its own workspace directory
- **Checkpoint & resume**: Tasks can be resumed from checkpoints after interruption
- **Web UI**: Flask-based dashboard for task management and monitoring
- **CLI**: Full command-line interface for all operations

## Requirements

- Python 3.9+
- Ollama running locally (default: `http://localhost:11434`)
- A supported model (e.g., `qwen3.5:4b`)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Web Server

```bash
python server.py
```

The web UI is available at `http://localhost:5002`.

### CLI

```bash
python cli.py <command> [options]
```

#### Commands

| Command | Description |
|---------|-------------|
| `create "task"` | Create a new task |
| `list` | List all tasks |
| `get <task_id>` | Get task details |
| `action <task_id> <action>` | Execute action (approve, modify, inject, resume, resume_auto, force_complete) |
| `pause <task_id>` | Pause a running task |
| `restart <task_id>` | Restart a failed task |
| `delete <task_id>` | Delete a task |
| `files <task_id> <view\|edit\|list>` | Manage task files |
| `memory <prompt\|lessons>` | Manage system memory |
| `dashboard` | Show dashboard statistics |

#### Examples

```bash
# Create a task and wait for completion
python cli.py create "Build a snake game in Python" --mode auto --wait

# Create a task in step mode (manual approval)
python cli.py create "Create a REST API with Flask" --mode step

# List all tasks
python cli.py list

# Get task details (raw JSON)
python cli.py get task_20260521_120000 --raw

# Approve next action in step mode
python cli.py action task_20260521_120000 approve

# Inject user instruction
python cli.py action task_20260521_120000 inject --user-prompt "Use pytest for testing"

# Modify and approve a tool call
python cli.py action task_20260521_120000 modify --modified-tool '{"name":"write_file","args":{"path":"main.py","content":"..."}}'

# Pause a running task
python cli.py pause task_20260521_120000

# Resume auto mode
python cli.py action task_20260521_120000 resume_auto --wait

# Restart a failed task
python cli.py restart task_20260521_120000

# View task files
python cli.py files task_20260521_120000 view plan/plan.md

# List task output files
python cli.py files task_20260521_120000 list

# Edit a file in task output
python cli.py files task_20260521_120000 edit output/main.py --content "print('hello')"

# Get system prompt
python cli.py memory prompt --get

# Set system prompt
python cli.py memory prompt --set "You are Maria, an agentic coding assistant."

# Get lessons
python cli.py memory lessons --get

# Show dashboard
python cli.py dashboard
```

### Direct Agent (no server)

```bash
python main.py "Build a calculator in Python" --max-steps 20 --workspace workspace --memory memory
```

## Architecture

### Stages

1. **Improving Prompt** - Refines the user task for clarity and detail
2. **Generating Plan** - Creates a comprehensive implementation plan
3. **Creating Steps** - Breaks the plan into 3-5 high-level milestones
4. **Executing Steps** - Runs each step with tool calls (LLM-driven)
5. **Verifying** - Audits generated files against the plan
6. **Supervisor Review** - Final pass/fail decision
7. **Self-Improvement** - Extracts lessons from errors (background)

### Key Files

| File | Description |
|------|-------------|
| `server.py` | Flask web server with API routes |
| `cli.py` | Command-line interface |
| `main.py` | Direct agent execution (no server) |
| `maria/agent.py` | MariaAgent class with stage methods |
| `maria/llm.py` | LLM client abstraction |
| `maria/tools.py` | Tool executor (file ops, commands) |
| `maria/memory.py` | Memory management (prompts, lessons) |
| `maria/self_improvement.py` | Self-improvement agent |

### Directory Structure

```
workspace/
  task_<timestamp>/
    task_state.json       # Current task state
    task_info.html        # Task info (legacy)
    plan/
      plan.md             # Implementation plan
      steps/
        step_001.md       # Step summaries
    output/               # Generated files
    verification_report.md
memory/
  system_prompt.md        # System prompt
  lessons.json            # Lessons learned
```

## API Routes

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/dashboard` | Dashboard stats |
| GET | `/api/tasks` | List tasks |
| POST | `/api/tasks` | Create task |
| GET | `/api/tasks/<id>` | Get task |
| POST | `/api/tasks/<id>/action` | Execute action |
| POST | `/api/tasks/<id>/pause` | Pause task |
| POST | `/api/tasks/<id>/restart` | Restart task |
| DELETE | `/api/tasks/<id>` | Delete task |
| GET | `/api/tasks/<id>/files/view?path=` | View file |
| GET | `/api/tasks/<id>/files/raw/<path>` | Raw file |
| POST | `/api/tasks/<id>/files/edit` | Edit file |
| GET/POST | `/api/memory/prompt` | Manage prompt |
| GET/POST | `/api/memory/lessons` | Manage lessons |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MARIA_SERVER` | - | Set to `1` to bypass security prompts |
| `FLASK_ENV` | `development` | Flask environment |
| `DEBUG` | `1` | Enable debug mode |

CLI options for `create`:

| Option | Default | Description |
|--------|---------|-------------|
| `--max-steps` | 20 | Maximum execution steps |
| `--mode` | step | `step` or `auto` |
| `--model-think` | true | Enable model thinking |
| `--no-model-think` | - | Disable model thinking |
| `--provider` | ollama | Provider type |
| `--wait` | false | Wait for completion |

## Tests

```bash
pytest tests/
```
