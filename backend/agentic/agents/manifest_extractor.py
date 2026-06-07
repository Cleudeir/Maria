import json
import re
from typing import List, Dict, Tuple, Optional


VALID_FRAMEWORKS = frozenset({
    "vanilla", "react", "vue", "svelte", "angular", "solid",
    "express", "fastify", "koa", "next", "nuxt", "remix", "vite",
    "three.js", "babylon.js", "phaser", "pixi.js", "p5.js",
    "pygame", "arcade", "fastapi", "flask", "django", "starlette",
    "tornado", "aiohttp", "numpy", "pandas", "scikit-learn", "torch",
    "tensorflow", "transformers", "langchain", "gradio", "streamlit",
    "node", "deno", "bun", "electron", "tauri", "gtk", "qt",
    "tkinter", "customtkinter", "kivy", "flet",
})

VALID_COMPLEXITY = frozenset({"simple", "moderate", "complex", "advanced"})


def validate_plan_quality(plan: dict) -> list[str]:
    """Return a list of issues with the plan. Empty list = plan is acceptable.

    The plan is REJECTED if:
    - It has no files
    - It has only one file (unless complexity is "simple")
    - Every file is empty
    - It mixes an HTML entrypoint with no CSS/JS siblings
    - It declares an external import / dep but no install command
    - It picked a framework whose name we don't recognize
    """
    issues: list[str] = []
    files = plan.get("files", [])
    if not isinstance(files, list) or not files:
        return ["plan has no files"]

    complexity = (plan.get("complexity") or "").lower().strip()
    framework = (plan.get("project", {}).get("framework") or "").lower().strip()
    rationale = (plan.get("architecture_rationale") or "").strip()

    if complexity and complexity not in VALID_COMPLEXITY:
        issues.append(
            f"complexity must be one of {sorted(VALID_COMPLEXITY)}, got '{complexity}'"
        )
    if not complexity:
        issues.append("plan is missing the 'complexity' field (simple | moderate | complex | advanced)")

    if not framework:
        issues.append("plan is missing project.framework — pick a real framework (vanilla, react, vue, fastapi, etc.)")
    elif framework not in VALID_FRAMEWORKS:
        issues.append(
            f"framework '{framework}' is not recognized. Pick from: {', '.join(sorted(VALID_FRAMEWORKS))}"
        )
    elif framework == "vanilla" and not rationale:
        issues.append("if you pick framework='vanilla' you must include architecture_rationale explaining why")

    if len(files) < 2 and complexity not in ("", "simple"):
        issues.append(
            f"plan has only {len(files)} file(s) but complexity='{complexity}' — multi-file projects are required"
        )

    empty_files: list[str] = []
    has_html = False
    has_css = False
    has_js = False
    has_non_html = False

    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path", "")
        if not path:
            continue
        pl = path.lower()
        if pl.endswith(".html") or pl.endswith(".htm"):
            has_html = True
        elif pl.endswith(".css"):
            has_css = True
        elif pl.endswith(".js") or pl.endswith(".ts") or pl.endswith(".jsx") or pl.endswith(".tsx"):
            has_js = True
        else:
            has_non_html = True

        funcs = f.get("functions", []) or []
        imps = f.get("imports", []) or []
        consts = f.get("constants", []) or []
        desc = (f.get("description") or "").strip()

        if not funcs and not imps and not consts and not desc:
            empty_files.append(path)

    if empty_files and len(empty_files) == len(files):
        issues.append(
            "every file in the plan is empty (no functions, imports, constants, or description) — "
            "this is a placeholder/stub plan, not a real design"
        )
    elif empty_files:
        issues.append(
            f"these files are empty placeholders: {', '.join(empty_files)}"
        )

    if has_html and not has_css and not has_js and not has_non_html:
        issues.append(
            "HTML entrypoint exists but the plan has no CSS, no JS, and no other files — "
            "interactive web pages need separated style.css and game.js/app.js"
        )

    declared_deps = plan.get("dependencies", []) or []
    install_cmds = plan.get("install_commands", []) or []
    external_imports: set[str] = set()
    for f in files:
        if not isinstance(f, dict):
            continue
        for imp in f.get("imports", []) or []:
            if isinstance(imp, dict) and imp.get("external", True):
                module = (imp.get("module") or "").strip()
                if module and not module.startswith("."):
                    external_imports.add(module.split("/")[0].split("@")[0])

    if external_imports and not install_cmds and framework != "vanilla":
        declared_names = {(d.get("name") or "").lower() for d in declared_deps if isinstance(d, dict)}
        for imp in external_imports:
            if imp.lower() not in declared_names and imp not in ("react", "react-dom"):
                issues.append(
                    f"file imports external module '{imp}' but no install_commands are declared. "
                    f"Add an install command (e.g. 'npm install {imp}') or remove the import."
                )
                break

    return issues


def extract_manifest(plan_json: str) -> Tuple[Dict, List[str]]:
    if not plan_json or not plan_json.strip():
        raise ValueError("plan_json is empty")

    cleaned = plan_json.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("JSON root must be a mapping")

    project = data.get("project", {})
    if not isinstance(project, dict):
        raise ValueError("project must be a mapping")

    project_name = project.get("name", "unnamed")
    project_desc = project.get("description", "")
    language = project.get("language", "python")
    raw_framework = (project.get("framework") or "").strip()
    framework = raw_framework.lower() or "vanilla"

    complexity = (data.get("complexity") or "").strip().lower() or "moderate"
    if complexity not in VALID_COMPLEXITY:
        complexity = "moderate"
    architecture_rationale = (data.get("architecture_rationale") or "").strip()

    dependencies = data.get("dependencies", []) or []
    if not isinstance(dependencies, list):
        dependencies = []
    normalized_deps: list[dict] = []
    for d in dependencies:
        if isinstance(d, dict):
            normalized_deps.append({
                "name": (d.get("name") or "").strip(),
                "manager": (d.get("manager") or "npm").strip().lower(),
                "purpose": (d.get("purpose") or "").strip(),
            })
        elif isinstance(d, str):
            normalized_deps.append({"name": d.strip(), "manager": "npm", "purpose": ""})
    dependencies = [d for d in normalized_deps if d["name"]]

    install_commands = data.get("install_commands", []) or []
    if not isinstance(install_commands, list):
        install_commands = []
    install_commands = [str(c).strip() for c in install_commands if str(c).strip()]

    test_commands = data.get("test_commands", []) or []
    if not isinstance(test_commands, list):
        test_commands = []
    test_commands = [str(c).strip() for c in test_commands if str(c).strip()]

    files = data.get("files", [])
    if not isinstance(files, list) or not files:
        raise ValueError("files must be a non-empty list")

    entrypoint = data.get("entrypoint", "")

    validated_files = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path", "")
        if not path:
            continue

        deps_raw = f.get("dependencies", [])
        if not isinstance(deps_raw, list):
            deps_raw = []
        normalized_deps = []
        for d in deps_raw:
            if isinstance(d, str):
                normalized_deps.append(d)
            elif isinstance(d, dict):
                name = d.get("name") or d.get("module") or ""
                if name:
                    normalized_deps.append(str(name).strip())
        file_spec = {
            "path": path,
            "description": f.get("description", ""),
            "type": f.get("type", "module"),
            "imports": _normalize_imports(f.get("imports", [])),
            "functions": _normalize_functions(f.get("functions", [])),
            "constants": f.get("constants", []),
            "dependencies": normalized_deps,
        }
        pre_gen = f.get("_pre_generated_content")
        if pre_gen:
            file_spec["_pre_generated_content"] = pre_gen

        validated_files.append(file_spec)

    if not validated_files:
        raise ValueError("No valid files found in plan")

    manifest = {
        "complexity": complexity,
        "architecture_rationale": architecture_rationale,
        "project": {
            "name": project_name,
            "description": project_desc,
            "language": language,
            "framework": framework,
        },
        "dependencies": dependencies,
        "install_commands": install_commands,
        "test_commands": test_commands,
        "files": validated_files,
        "entrypoint": entrypoint or (validated_files[0]["path"] if validated_files else ""),
    }

    generation_order = topological_sort(validated_files)

    return manifest, generation_order


def topological_sort(files: List[Dict]) -> List[str]:
    indegree = {f["path"]: 0 for f in files}
    adjacency = {f["path"]: [] for f in files}

    for f in files:
        for dep in f.get("dependencies", []):
            if dep in indegree:
                adjacency[dep].append(f["path"])
                indegree[f["path"]] += 1

    queue = [path for path, deg in indegree.items() if deg == 0]
    sorted_paths = []

    while queue:
        current = queue.pop(0)
        sorted_paths.append(current)
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)

    all_paths = {f["path"] for f in files}
    sorted_set = set(sorted_paths)

    for path in all_paths - sorted_set:
        sorted_paths.append(path)

    # Move test files to the front (TDD: tests before implementation)
    def is_test_file(path: str) -> bool:
        pl = path.lower()
        return pl.startswith("test") or "_test." in pl or ".test." in pl or pl.endswith("test.html") or pl.endswith("spec.js") or pl.endswith("spec.ts")

    tests = [p for p in sorted_paths if is_test_file(p)]
    non_tests = [p for p in sorted_paths if not is_test_file(p)]
    return tests + non_tests


def get_file_spec(manifest: Dict, file_path: str) -> Optional[Dict]:
    if not manifest:
        return None
    files = manifest.get("files", [])
    for f in files:
        if f.get("path") == file_path:
            return f
    return None


def _normalize_imports(imports) -> List[Dict]:
    result = []
    for imp in imports:
        if isinstance(imp, str):
            result.append({"module": imp, "items": [], "external": True})
        elif isinstance(imp, dict):
            result.append({
                "module": imp.get("module", imp.get("name", "")),
                "items": imp.get("items", []) or [],
                "external": imp.get("external", True),
            })
    return result


def _normalize_functions(functions) -> List[Dict]:
    result = []
    for fn in functions:
        if not isinstance(fn, dict):
            continue
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "inputs": fn.get("inputs", []) or [],
            "outputs": fn.get("outputs", []) or [],
            "calls": fn.get("calls", []) or [],
        })
    return result
