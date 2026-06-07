ANALYSIS_SYSTEM_PROMPT = """You are a software architect doing the first step of planning: REQUIREMENTS & STACK ANALYSIS.

Given a task, you must output ONLY a JSON object describing your analysis.
NO tool calls, NO code, NO markdown fences, NO explanations — just JSON.

Your job is to make four key decisions and justify them:
1. complexity — how big is this task?
2. framework + language — what's the best stack?
3. dependencies — what packages must be installed?
4. install_commands — exact shell commands to run, in order

BE OPINIONATED. Almost every real task needs a real framework/library:
- 3D / GTA-style / open-world / city / driving / shooter / simulator games → three.js
- 2D web games / arcade / platformer / pixel art → phaser
- Interactive UI / dashboard / SPA → react, vue, or svelte
- Real-time chat / multiplayer → socket.io on express
- HTTP / REST API in Python → fastapi (preferred) or flask
- ML / data analysis / training → numpy + scikit-learn or torch
- Web app with server-side rendering → next, nuxt
- CLI / script → plain language, vanilla is OK here

ONLY pick "vanilla" for trivial single-file scripts (a hello-world, a regex tester, a one-liner). For anything more complex, ALWAYS pick a real framework. If you must pick vanilla, you MUST justify it in `architecture_rationale`."""


ANALYSIS_USER_PROMPT = """Task: {task}

{lessons}

Produce your analysis as JSON in EXACTLY this shape:

{{
  "complexity": "simple | moderate | complex | advanced",
  "architecture_rationale": "1-3 sentences explaining your stack choice",
  "project": {{
    "name": "snake_case_project_name",
    "description": "one-sentence description",
    "language": "javascript | typescript | python | html | cpp | go | rust",
    "framework": "three.js | phaser | pixi.js | babylon.js | p5.js | react | vue | svelte | angular | solid | next | nuxt | express | fastify | vite | socket.io | fastapi | flask | django | streamlit | gradio | pygame | arcade | numpy | pandas | scikit-learn | torch | vanilla"
  }},
  "dependencies": [
    {{"name": "package_name", "manager": "npm | pip | npx", "purpose": "what it does", "version": "optional, e.g. ^1.0.0"}}
  ],
  "install_commands": [
    "exact shell command 1",
    "exact shell command 2"
  ],
  "test_commands": [
    "exact shell command to run tests, lint, or build verification"
  ],
  "execution_strategy": "how to verify this works (e.g. 'open index.html and check canvas', 'curl /todos returns []', 'python main.py runs without error')",
  "file_structure_notes": "any layout constraints (e.g. 'web game must split into index.html + style.css + game.js')"
}}

TASK-PATTERN HINTS (use these to pick the right stack):
- "GTA", "open world", "city", "driving", "3D", "shooter", "racing" → three.js (NOT vanilla, NOT phaser)
- "2D game", "platformer", "arcade", "pixel" → phaser
- "dashboard", "form", "admin panel", "todo app" → react or vue with vite
- "REST API", "backend", "endpoint", "server" → fastapi (Python) or express (Node)
- "ML", "training", "model", "data analysis" → numpy + scikit-learn or torch
- "chat", "realtime", "multiplayer" → socket.io
- "mobile app" → react-native or flutter
- If the task says "HTML" or "browser" but is essentially a game/simulator/visual app → three.js

COMPLEXITY GUIDE (pick one):
- simple: single file, no deps. (rare — only for trivial scripts and CLIs)
- moderate: 2-4 files, 0-2 packages. (small apps, single-page games)
- complex: multi-file app with a build/dev server or framework. (Flask API, React+Vite app, full game engine)
- advanced: full-stack, 3D, audio, multiple services, several libraries. (rare)

INSTALL COMMAND RULES:
- Allowed managers ONLY: npm, npx, pnpm, yarn, pip, pip3, python -m pip
- If you pick three.js/phaser/react/vue/express/flask/fastapi or ANY real framework, you MUST include the install command.
- If truly vanilla with no imports, set install_commands: [] and explain in architecture_rationale.

TEST COMMAND RULES (you MUST follow):
- `test_commands` is a list of shell commands that VERIFY the implementation works (compile, lint, run unit tests, type-check, build).
- EVERY task MUST have at least one test command. Pick the command(s) that match your stack:
  - Python project → ["python -m pytest -q"] or ["python -m py_compile <entrypoint>"]
  - Node/Vite project → ["npm run build"] or ["npm test"]
  - TypeScript → ["npx tsc --noEmit"]
  - HTML/JS web game → ["node -e 'require(\"fs\").readFileSync(\"index.html\")'"] or a DOM validation script
  - Python web (Flask/FastAPI) → ["python -m py_compile app.py"] + ["python -m pytest -q"] if tests exist
  - For ANY task, include AT LEAST one verification command (compile, lint, or build).
- The shell will run these AFTER files are generated. If a command exits non-zero, the system will auto-fix the implementation. Keep commands short and fast.
- NEVER set test_commands to []. Every task must be verifiable.

CRITICAL FORMAT:
- Output ONLY valid JSON. No markdown fences. No backticks. No prose.
- NO tool calls. NO "tool" or "args" fields.
- Start with {{ and end with }}."""


PLAN_V2_SYSTEM_PROMPT = """You are a software architect. You are given:
1. A TASK to implement
2. A PRE-ANALYSIS that already chose the complexity, framework, language, dependencies, and install commands

Your job is to produce a JSON IMPLEMENTATION PLAN: the list of files, their responsibilities, imports, and functions. You MUST respect the pre-analysis — do not pick a different framework or change the stack.

NO tool calls, NO code, NO markdown. Just the JSON plan."""


PLAN_V2_USER_PROMPT = """TASK:
{task}

{lessons}

PRE-ANALYSIS (you MUST follow this exactly):
{analysis}

Now produce the implementation plan as JSON in EXACTLY this shape:

{{
  "project": {{
    "name": "<copy from analysis.project.name>",
    "description": "<copy from analysis.project.description>",
    "language": "<copy from analysis.project.language>",
    "framework": "<copy from analysis.project.framework>"
  }},
  "files": [
    {{
      "path": "relative/file/path",
      "description": "what this file does",
      "type": "module | component | config | entrypoint | style | test",
      "imports": [
        {{"module": "module_name", "items": ["item1"], "external": true}}
      ],
      "functions": [
        {{
          "name": "function_name",
          "description": "what it does (1 sentence)",
          "inputs": [
            {{"name": "param_name", "type": "type", "required": true, "description": "what it is"}}
          ],
          "outputs": [
            {{"name": "return_name", "type": "type", "description": "what it returns"}}
          ],
          "calls": []
        }}
      ],
      "constants": [],
      "dependencies": []
    }}
  ],
  "entrypoint": "main/file/path"
}}

HARD RULES (your plan is rejected if any of these are violated):
1. framework, language, and project.name MUST match the pre-analysis verbatim.
2. Every file in `files` MUST have at least 3 functions, OR at least 2 imports, OR substantial content (CSS rules, HTML structure). Empty placeholder files are FORBIDDEN.
3. For game / interactive UI / web app tasks, the plan MUST split into at least: `index.html`, `style.css`, and `game.js` or `app.js`.
4. Functions MUST have non-empty `description` strings and at least one input or output. Stub functions are FORBIDDEN.
5. If any file declares an external import, that package MUST appear in pre-analysis.dependencies.
6. NO "Output Page" / "Hello World" placeholders. Every file must do real work.
7. TDD REQUIREMENT: The plan MUST include at least one test/validation file (type: "test"). For web tasks, include a `test.html` that validates the DOM structure, or a lint/typecheck config. For Python, include `test_*.py`. For JS/TS, include `*.test.js` or validation scripts. Test files are NOT optional — every plan must define how the implementation will be verified.

CRITICAL FORMAT:
- Output ONLY valid JSON. No markdown fences. No backticks. No explanations.
- NO tool calls. NO "tool" or "args" fields.
- Start and end with curly braces."""

def get_plan_v2_system_prompt():
    return PLAN_V2_SYSTEM_PROMPT

def get_plan_v2_user_prompt(task, lessons="", analysis=""):
    lessons_text = lessons if lessons else "No previous lessons."
    analysis_text = analysis if analysis else "(no pre-analysis provided — pick a sensible stack yourself)"
    return PLAN_V2_USER_PROMPT.format(task=task, lessons=lessons_text, analysis=analysis_text)


def get_analysis_system_prompt():
    return ANALYSIS_SYSTEM_PROMPT

def get_analysis_user_prompt(task, lessons=""):
    lessons_text = lessons if lessons else "No previous lessons."
    return ANALYSIS_USER_PROMPT.format(task=task, lessons=lessons_text)


FILE_GENERATION_PROMPT = """Write the code for {file_path} in {language}.

File: {file_path}
Description: {file_description}

Framework: {framework}
{fw_guidance}

Imports needed:
{imports_list}

Functions to implement:
{functions_spec}

Constants:
{constants_spec}

Project files (and where they live — use the EXACT path):
{project_files}

CRITICAL FORMATTING RULES (HARD):
1. The other files in this project live at these exact paths: {project_file_paths}.
2. From the HTML entry point, link CSS as a sibling: <link rel="stylesheet" href="style.css">.
   For JS, you MUST pick ONE pattern and use it consistently:
   (A) PURE SCRIPT pattern (no `import` in JS files):
       - HTML: <script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
              <script src="game.js" defer></script>
       - JS:   const THREE = window.THREE;  (no import statements)
   (B) ES MODULE pattern (JS uses `import`):
       - HTML: <script type="module" src="game.js"></script>  (NO defer, NO .min in CDN path)
       - JS:   import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';
   NEVER mix: if the JS uses `import`, the HTML MUST use `type="module"`. If the HTML uses `defer` (no type), the JS MUST NOT use `import`.
3. Do NOT use bare specifiers like `import 'three'` or `import 'react'` — there is no bundler.
4. Do NOT use subfolders like "css/styles.css" or "js/app.js" — the file structure puts all files at the project root.
5. If this is an HTML file, the title and content should match the task — not a generic "Output Page".
6. If framework is {framework}, follow that framework's idioms.
7. FOR NON-MODULE <script src> FILES (the PURE SCRIPT pattern above):
   All `<script>` tags run in the SHARED global scope — they do NOT get their own scope.
   Therefore: every `const`, `let`, `class`, and top-level `function` name must be globally UNIQUE.
   Two files declaring `const scene = ...` will crash the page with "redeclaration of const scene".
   To avoid this: wrap each file in `(() => {{ ... }})();` or keep your declarations in a single file.
8. When generating an HTML file: only write CSS class/id references if the corresponding element actually exists in the HTML. Matching CSS selectors to nonexistent DOM elements will produce no visual effect.
9. TDD FIRST: If this is a test file, write the test assertions first. If this is an implementation file, it will be verified against the test file. Ensure all exports and APIs match what the test expects.

Output ONLY the {language} code. No explanations, no markdown, no JSON, no tool calls.
Just raw code."""

_FRAMEWORK_GUIDANCE: dict[str, str] = {
    "react": "Use JSX/TSX. Default-export a function component. Use hooks (useState, useEffect, useRef) for state. Import other modules via ES `import`.",
    "vue": "Use Vue 3 Single File Component style if file is .vue, otherwise use Composition API (`setup()`, `ref`, `reactive`). Use `<template>`, `<script setup>`, `<style scoped>` for SFCs.",
    "svelte": "Use Svelte 4/5 syntax. Use reactive `$:` declarations or runes (`$state`, `$derived`). One component per .svelte file.",
    "angular": "Use Angular standalone components. Decorate with `@Component`. Use `@Input()` / `@Output()` for bindings.",
    "express": "Use CommonJS or ES modules consistently. Export a router or app via `module.exports` / `export default`. Use middleware pattern.",
    "fastapi": "Use type hints, Pydantic models, and `APIRouter`. Decorate endpoints with `@router.get/@router.post`. Return Pydantic models or dicts.",
    "flask": "Use Flask blueprints for modularity. Decorate routes with `@app.route` or `@blueprint.route`. Use Jinja2 templates if needed.",
    "django": "Use Django app structure: models in `models.py`, views in `views.py`, urls in `urls.py`. Use Django ORM, never raw SQL.",
    "pygame": "Initialize with `pygame.init()`. Use a main loop with `pygame.event.get()` for events and `pygame.display.flip()` to render. Use `Surface` and `Rect` for drawing.",
    "three.js": "Import `THREE` (or `* as THREE`). Set up scene, camera, renderer. Use a render loop with `requestAnimationFrame`.",
    "phaser": "Extend `Phaser.Scene` and use `preload()`, `create()`, `update()` lifecycle. Configure in `Phaser.Game` config object.",
    "next": "Use the App Router (`app/` directory). Default-export React components from `page.tsx` files. Mark server components explicitly when needed.",
    "vite": "Use ES modules. The entry HTML lives in the project root. Vite serves the project; just write idiomatic JS/TS.",
    "streamlit": "Call `st.set_page_config()` early. Use `st.title`, `st.write`, `st.sidebar`, widgets like `st.slider`/`st.button`. Cache heavy work with `@st.cache_data`.",
    "gradio": "Define a `gr.Interface` or `gr.Blocks`. Decorate functions and pass them to components. Launch with `demo.launch()`.",
    "node": "Plain Node.js with built-in modules. Use ES modules (`import`) or CommonJS (`require`) consistently.",
}


def get_file_generation_prompt(file_spec, task, language=None, framework=None, project_files=None):
    lang = language or file_spec.get("language", "python")
    fmwk = (framework or file_spec.get("framework") or "vanilla").lower()
    fw_guidance = _FRAMEWORK_GUIDANCE.get(fmwk, "")

    imports_list = _format_imports(file_spec.get("imports", []))
    functions_spec = _format_functions(file_spec.get("functions", []))
    constants_spec = _format_constants(file_spec.get("constants", []))
    project_files_str = _format_project_files(project_files)
    project_file_paths = get_project_file_paths(project_files)

    return FILE_GENERATION_PROMPT.format(
        language=lang,
        framework=fmwk,
        fw_guidance=fw_guidance or "No specific framework guidance — write idiomatic code for the language.",
        file_path=file_spec.get("path", "unknown"),
        file_description=file_spec.get("description", "No description"),
        imports_list=imports_list,
        functions_spec=functions_spec,
        constants_spec=constants_spec,
        project_files=project_files_str,
        project_file_paths=project_file_paths,
    )


def _format_imports(imports):
    if not imports:
        return "None"
    lines = []
    for imp in imports:
        module = imp.get("module", "")
        items = imp.get("items", [])
        external = imp.get("external", True)
        tag = "(external)" if external else "(internal)"
        if items:
            lines.append(f"  - {module} -> {', '.join(items)} {tag}")
        else:
            lines.append(f"  - {module} {tag}")
    return "\n".join(lines)


def _format_functions(functions):
    if not functions:
        return "None"
    lines = []
    for fn in functions:
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        inputs = fn.get("inputs", [])
        outputs = fn.get("outputs", [])
        calls = fn.get("calls", [])

        inp_str = ", ".join(
            f"{p.get('name')}: {p.get('type')}" + ("" if p.get("required", True) else " (optional)")
            for p in inputs
        ) if inputs else "None"
        out_str = ", ".join(
            f"{p.get('name')}: {p.get('type')}"
            for p in outputs
        ) if outputs else "None"
        calls_str = ", ".join(calls) if calls else "None"

        lines.append(f"  Function: {name}")
        lines.append(f"    Description: {desc}")
        lines.append(f"    Inputs: {inp_str}")
        lines.append(f"    Outputs: {out_str}")
        lines.append(f"    Internal calls: {calls_str}")
        lines.append("")
    return "\n".join(lines)


def _format_constants(constants):
    if not constants:
        return "None"
    lines = []
    for c in constants:
        name = c.get("name", "")
        typ = c.get("type", "")
        val = c.get("value", "")
        desc = c.get("description", "")
        lines.append(f"  {name}: {typ} = {val} ({desc})")
    return "\n".join(lines)


def _format_project_files(files):
    if not files:
        return "None"
    lines = ["Other files in this project:"]
    for f in files:
        path = f.get("path", "")
        desc = f.get("description", "")
        ftype = f.get("type", "")
        lines.append(f"  - {path} ({ftype}): {desc}")
    return "\n".join(lines)


def get_project_file_paths(files) -> str:
    if not files:
        return "none"
    return ", ".join(f.get("path", "") for f in files if f.get("path"))
