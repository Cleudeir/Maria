# Maria

Maria is a self-improving agentic SLM (Small Language Model) system that autonomously completes coding tasks using Ollama. It follows a multi-stage pipeline: planning, step creation, and execution, with self-improvement learning from errors.

## Features

- **Multi-stage pipeline**: Improves prompts, generates plans, breaks into steps, executes, and verifies
- **Execution mode**: `auto` (fully autonomous)
- **Tool use**: list_dir, read_file, write_file, finish_task
- **Self-improvement**: Learns from errors and stores lessons to prevent repeating mistakes
- **Memory system**: Persistent system prompts and lessons across runs
- **Task isolation**: Each task runs in its own workspace directory
- **Checkpoint & resume**: Tasks can be resumed from checkpoints after interruption
- **Web UI**: Flask-based dashboard for task management and monitoring

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

## Architecture

### Stages

1. **Improving Prompt** - Refines the user task for clarity and detail
2. **Generating Plan** - Creates a comprehensive implementation plan
3. **Creating Steps** - Breaks the plan into 3-5 high-level milestones
4. **Executing Steps** - Runs each step with tool calls (LLM-driven)
5. **Verifying** - Audits generated files against the plan
6. **Self-Improvement** - Extracts lessons from errors (background)

### Key Files

| File | Description |
|------|-------------|
| `server.py` | Flask web server with API routes |
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
| POST | `/api/tasks/<id>/continue` | Continue task |
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

## Tests

```bash
pytest tests/
```
