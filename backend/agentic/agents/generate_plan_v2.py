import json
import re
from collections.abc import Callable

from .prompts_v2 import (
    get_analysis_system_prompt,
    get_analysis_user_prompt,
    get_plan_v2_system_prompt,
    get_plan_v2_user_prompt,
)


def generate_analysis(
    task: str,
    get_generate_fn: Callable,
    stream_callback: Callable[[str], None] | None = None,
    lessons: str = "",
) -> dict | None:
    """Stage 0: ask the LLM to analyze the task and pick complexity/stack/deps.

    Returns a dict on success, or None on failure (the caller can fall back to
    sensible defaults and proceed).
    """
    response = get_generate_fn(
        system_text=get_analysis_system_prompt(),
        user_text=get_analysis_user_prompt(task, lessons),
        progress_callback=stream_callback,
    )
    if not response or not response.strip():
        return None
    data = _extract_analysis_json(response)
    if not data:
        return None
    return _normalize_analysis(data)


def _extract_analysis_json(text: str) -> dict | None:
    """Find the analysis JSON in the LLM response.

    Analysis shape: { complexity, architecture_rationale, project: {...},
                      dependencies: [...], install_commands: [...] }
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    for obj in _extract_all_json_objects(cleaned):
        if not isinstance(obj, dict):
            continue
        if "complexity" in obj and "project" in obj:
            return obj

    for obj in _extract_all_json_objects(cleaned):
        if not isinstance(obj, dict):
            continue
        if "project" in obj and "dependencies" in obj:
            return obj

    for obj in _extract_all_json_objects(cleaned):
        if isinstance(obj, dict) and obj.get("tool") == "write_file":
            return None

    return None


def _normalize_analysis(data: dict) -> dict:
    project = data.get("project", {}) or {}
    language = (project.get("language") or "javascript").strip().lower()
    framework = (project.get("framework") or "vanilla").strip().lower()
    complexity = (data.get("complexity") or "moderate").strip().lower()
    if complexity not in ("simple", "moderate", "complex", "advanced"):
        complexity = "moderate"

    raw_deps = data.get("dependencies") or []
    if not isinstance(raw_deps, list):
        raw_deps = []
    deps: list[dict] = []
    for d in raw_deps:
        if isinstance(d, dict):
            name = (d.get("name") or "").strip()
            if not name:
                continue
            deps.append({
                "name": name,
                "manager": (d.get("manager") or "npm").strip().lower(),
                "purpose": (d.get("purpose") or "").strip(),
                "version": (d.get("version") or "").strip(),
            })
        elif isinstance(d, str) and d.strip():
            deps.append({"name": d.strip(), "manager": "npm", "purpose": "", "version": ""})

    raw_cmds = data.get("install_commands") or []
    if not isinstance(raw_cmds, list):
        raw_cmds = []
    cmds = [str(c).strip() for c in raw_cmds if str(c).strip()]

    return {
        "complexity": complexity,
        "architecture_rationale": (data.get("architecture_rationale") or "").strip(),
        "project": {
            "name": (project.get("name") or "task").strip(),
            "description": (project.get("description") or "").strip(),
            "language": language,
            "framework": framework,
        },
        "dependencies": deps,
        "install_commands": cmds,
        "execution_strategy": (data.get("execution_strategy") or "").strip(),
        "file_structure_notes": (data.get("file_structure_notes") or "").strip(),
    }


def _analysis_to_prompt_block(analysis: dict) -> str:
    deps_lines = []
    for d in analysis.get("dependencies", []):
        v = f"@{d['version']}" if d.get("version") else ""
        deps_lines.append(f"  - {d['name']}{v} (manager={d['manager']}): {d.get('purpose', '')}")
    deps_text = "\n".join(deps_lines) if deps_lines else "  (none)"

    cmds = analysis.get("install_commands", []) or []
    cmds_text = "\n".join(f"  {i+1}. `{c}`" for i, c in enumerate(cmds)) if cmds else "  (none)"

    proj = analysis.get("project", {})
    return (
        f"complexity: {analysis.get('complexity', 'moderate')}\n"
        f"framework: {proj.get('framework', 'vanilla')}\n"
        f"language: {proj.get('language', 'javascript')}\n"
        f"project_name: {proj.get('name', 'task')}\n"
        f"architecture_rationale: {analysis.get('architecture_rationale', '')}\n"
        f"\n"
        f"dependencies:\n{deps_text}\n"
        f"\n"
        f"install_commands (in order):\n{cmds_text}\n"
        f"\n"
        f"execution_strategy: {analysis.get('execution_strategy', '')}\n"
        f"file_structure_notes: {analysis.get('file_structure_notes', '')}\n"
    )


def generate_plan_v2(
    task: str,
    get_generate_fn: Callable,
    stream_callback: Callable[[str], None] | None = None,
    system_prompt: str = "",
    lessons: str = "",
    complexity: str = "complex",
    analysis: dict | None = None,
) -> str:
    system_text = system_prompt or get_plan_v2_system_prompt()

    analysis_block = _analysis_to_prompt_block(analysis) if analysis else ""

    user_text = get_plan_v2_user_prompt(task, lessons, analysis_block)

    response = get_generate_fn(
        system_text=system_text,
        user_text=user_text,
        progress_callback=stream_callback,
    )

    if not response or not response.strip():
        return ""

    plan_json = _extract_json(response)

    return plan_json


def _extract_json(text: str) -> str:
    if not text or not text.strip():
        return ""

    cleaned = text.strip()

    # Remove markdown fences
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    json_objects = _extract_all_json_objects(cleaned)

    # Priority 1: Look for a proper project plan with files
    for data in json_objects:
        if isinstance(data, dict) and "project" in data and "files" in data:
            return json.dumps(data, indent=2)

    # Priority 2: Look for write_file tool calls
    for data in json_objects:
        if isinstance(data, dict) and data.get("tool") == "write_file":
            return _make_plan_from_tool_call(data)

    # Priority 3: Look for arrays of tool calls
    for data in json_objects:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("tool") == "write_file":
                    return _make_plan_from_tool_call(item)

    # Priority 4: Finish_task - synthesize a real plan from the analysis
    for data in json_objects:
        if isinstance(data, dict) and data.get("tool") == "finish_task":
            summary = data.get("args", {}).get("summary", "")
            single_match = re.search(r'[\w/]+\.\w+', summary)
            if single_match:
                return _make_plan_from_tool_call({"args": {"path": single_match.group()}})
            return ""

    return ""


def _extract_all_json_objects(text: str) -> list:
    results = []
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            break
        depth = 0
        in_str = False
        escape = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end != -1:
            try:
                obj = json.loads(text[start:end+1])
                if isinstance(obj, (dict, list)):
                    results.append(obj)
            except json.JSONDecodeError:
                pass
        idx = start + 1 if end == -1 else end + 1
    return results


def _make_plan_from_tool_call(data: dict) -> str:
    args = data.get("args", {})
    path = args.get("path", data.get("path", "output.py"))
    content = args.get("content", data.get("content", ""))
    lang = "python"
    if path.endswith(".js") or path.endswith(".ts"):
        lang = "javascript"
    elif path.endswith(".html"):
        lang = "html"
    elif path.endswith(".css"):
        lang = "css"

    plan = {
        "project": {
            "name": "task",
            "description": "Generated implementation",
            "language": lang,
            "framework": "vanilla",
        },
        "files": [
            {
                "path": path,
                "description": f"Generated {path}",
                "type": "module",
                "imports": [],
                "functions": [],
                "constants": [],
                "dependencies": [],
                "_pre_generated_content": content,
            }
        ],
        "entrypoint": path,
    }
    return json.dumps(plan, indent=2)


def _make_plan_from_paths(paths: list) -> str:
    lang = "python"
    if any(p.endswith(".js") for p in paths):
        lang = "javascript"
    elif any(p.endswith(".html") for p in paths):
        lang = "html"

    files = [
        {
            "path": p,
            "description": f"Generated {p}",
            "type": "module",
            "imports": [],
            "functions": [],
            "constants": [],
            "dependencies": [],
        }
        for p in paths
    ]
    plan = {
        "project": {
            "name": "task",
            "description": "Generated implementation",
            "language": lang,
            "framework": "vanilla",
        },
        "files": files,
        "entrypoint": paths[0] if paths else "",
    }
    return json.dumps(plan, indent=2)
