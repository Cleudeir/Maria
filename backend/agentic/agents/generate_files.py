import json
import os
import re
from collections.abc import Callable

from .manifest_extractor import get_file_spec
from .prompts_v2 import get_file_generation_prompt


def generate_all_files(
    manifest: dict,
    generation_order: list[str],
    task: str,
    system_prompt: str,
    get_generate_fn: Callable,
    stream_callback: Callable[[str], None] | None,
    output_dir: str,
) -> list[dict]:
    results = []
    project = manifest.get("project", {})
    language = project.get("language", "python")
    framework = project.get("framework", "vanilla")

    for file_path in generation_order:
        file_spec = get_file_spec(manifest, file_path)
        if not file_spec:
            results.append({
                "path": file_path,
                "success": False,
                "error": "File not found in manifest",
                "content": None,
                "functions_generated": [],
            })
            continue

        all_files = manifest.get("files", [])
        sibling_files = [f for f in all_files if f.get("path") != file_path]

        max_attempts = 2
        for attempt in range(max_attempts):
            result = generate_single_file(
                file_spec=file_spec,
                task=task,
                system_prompt=system_prompt,
                get_generate_fn=get_generate_fn,
                stream_callback=stream_callback,
                output_dir=output_dir,
                language=language,
                framework=framework,
                project_files=sibling_files,
            )

            if result["success"]:
                is_valid, errors = validate_generated_code(
                    result.get("content", ""), file_spec, framework
                )
                if is_valid:
                    result["functions_generated"] = _extract_function_names(
                        result.get("content", ""), language
                    )
                    results.append(result)
                    break
                else:
                    if attempt < max_attempts - 1:
                        file_spec_copy = dict(file_spec)
                        file_spec_copy["_retry_context"] = (
                            f"Previous attempt failed validation: {'; '.join(errors)}"
                        )
                        file_spec = file_spec_copy
                    else:
                        result["error"] = f"Validation failed after {max_attempts} attempts: {'; '.join(errors)}"
                        result["success"] = False
                        result["functions_generated"] = _extract_function_names(
                            result.get("content", ""), language
                        )
                        results.append(result)
            else:
                if attempt >= max_attempts - 1:
                    results.append(result)
                else:
                    file_spec_copy = dict(file_spec)
                    file_spec_copy["_retry_context"] = (
                        f"Previous attempt failed: {result.get('error', 'unknown')}"
                    )
                    file_spec = file_spec_copy

    return results


def generate_single_file(
    file_spec: dict,
    task: str,
    system_prompt: str,
    get_generate_fn: Callable,
    stream_callback: Callable[[str], None] | None,
    output_dir: str,
    language: str = "python",
    framework: str = "vanilla",
    project_files: list = None,
) -> dict:
    file_path = file_spec.get("path", "")
    file_lang = _detect_lang(file_path) or language

    pre_gen_content = file_spec.get("_pre_generated_content")
    if pre_gen_content:
        code = _clean_pre_generated(pre_gen_content)
        full_output_path = os.path.join(output_dir, file_path)
        try:
            os.makedirs(os.path.dirname(full_output_path), exist_ok=True)
            with open(full_output_path, "w", encoding="utf-8") as f:
                f.write(code)
        except OSError as e:
            return {"path": file_path, "success": False, "error": f"Failed to write file: {e!s}", "content": code, "functions_generated": []}

        return {"path": file_path, "success": True, "error": None, "content": code, "functions_generated": _extract_function_names(code, file_lang)}

    context = build_file_context(file_spec, task, file_lang, framework, project_files)

    try:
        response = get_generate_fn(
            system_text=system_prompt,
            user_text=context,
            progress_callback=stream_callback,
        )
    except Exception as e:
        return {
            "path": file_path,
            "success": False,
            "error": f"LLM error: {e!s}",
            "content": None,
            "functions_generated": [],
        }

    code = _extract_code(response, file_lang)

    if not code or not code.strip():
        return {
            "path": file_path,
            "success": False,
            "error": "Empty response from LLM",
            "content": None,
            "functions_generated": [],
        }

    code_stripped = code.strip()
    if code_stripped.startswith('{') and '"tool"' in code_stripped:
        return {
            "path": file_path,
            "success": False,
            "error": "LLM returned tool call instead of code",
            "content": None,
            "functions_generated": [],
        }

    full_output_path = os.path.join(output_dir, file_path)
    try:
        os.makedirs(os.path.dirname(full_output_path), exist_ok=True)
        with open(full_output_path, "w", encoding="utf-8") as f:
            f.write(code)
    except OSError as e:
        return {
            "path": file_path,
            "success": False,
            "error": f"Failed to write file: {e!s}",
            "content": code,
            "functions_generated": [],
        }

    return {
        "path": file_path,
        "success": True,
        "error": None,
        "content": code,
        "functions_generated": [],
    }


def build_file_context(
    file_spec: dict, task: str, language: str = "python", framework: str = "vanilla",
    project_files: list = None,
) -> str:
    retry_context = file_spec.get("_retry_context", "")

    prompt = get_file_generation_prompt(file_spec, task, language, framework, project_files)

    if retry_context:
        prompt += f"\n\nPREVIOUS ATTEMPT ISSUES:\n{retry_context}\nPlease fix these issues in your new implementation."

    return prompt


def validate_generated_code(code: str, file_spec: dict, framework: str = "vanilla") -> tuple:
    errors = []

    missing_functions = check_functions_exist(code, file_spec)
    if missing_functions:
        errors.append(f"Missing functions: {', '.join(missing_functions)}")

    missing_imports = check_imports(code, file_spec, framework)
    if missing_imports:
        errors.append(f"Missing imports: {', '.join(missing_imports)}")

    return (len(errors) == 0, errors)


def check_functions_exist(code: str, file_spec: dict) -> list[str]:
    functions = file_spec.get("functions", [])
    if not functions:
        return []

    code_normalized = code.strip()
    missing = []

    for fn in functions:
        name = fn.get("name", "")
        if not name:
            continue

        patterns = [
            rf"\bdef {re.escape(name)}\b",
            rf"\bfunc {re.escape(name)}\b",
            rf"\bfunction {re.escape(name)}\b",
            rf"\bconst {re.escape(name)}\s*=\s*(?:async\s*)?\(",
            rf"\bconst {re.escape(name)}\s*=\s*(?:async\s*)?\(?.*?\)?\s*=>",
            rf"\b{re.escape(name)}\s*=\s*(?:async\s*)?\(",
            rf"\bclass {re.escape(name)}\b",
            rf"export\s+(?:default\s+)?(?:async\s+)?function\s+{re.escape(name)}\b",
            rf"export\s+(?:default\s+)?\s*{re.escape(name)}\b",
        ]

        found = any(re.search(p, code_normalized, re.MULTILINE) for p in patterns)
        if not found:
            missing.append(name)

    return missing


def check_imports(code: str, file_spec: dict, framework: str = "vanilla") -> list[str]:
    imports = file_spec.get("imports", [])
    if not imports:
        return []

    cdn_frameworks = {"three.js", "phaser", "pixi.js", "babylon.js", "p5.js"}
    is_cdn = framework.lower() in cdn_frameworks

    missing = []
    for imp in imports:
        module = imp.get("module", "")
        if not module:
            continue

        if is_cdn and module in ("three", "phaser", "pixi", "babylon", "p5"):
            cdn_patterns = [
                rf"\bwindow\.{module}\b",
                rf"\bwindow\.THREE\b",
                rf"const\s+.*?=\s*window\.",
                rf"\.src\s*=\s*.*cdn\.jsdelivr\.net.*{re.escape(module)}",
            ]
            found = any(re.search(p, code, re.IGNORECASE | re.MULTILINE) for p in cdn_patterns)
            if found:
                continue

        es_patterns = [
            rf"\bimport\s+{re.escape(module)}\b",
            rf"\bfrom\s+{re.escape(module)}\s+import\b",
            rf"\brequire\s*\(\s*['\"]{re.escape(module)}['\"]",
            rf"\bimport\s+.*?\b{re.escape(module)}\b",
        ]
        found = any(re.search(p, code, re.MULTILINE) for p in es_patterns)
        if not found:
            missing.append(module)

    return missing


def _extract_code(text: str, language: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()

    for fmt_lang in [language, "html", "css", "js", "javascript", "python", "typescript", None]:
        if fmt_lang:
            pattern = rf"```(?:{re.escape(fmt_lang)})?\s*\n(.*?)\n```"
        else:
            pattern = r"```\s*\n(.*?)\n```"
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            inner = match.group(1).strip()
            inner_parsed = _try_extract_json_code(inner)
            if inner_parsed:
                return inner_parsed
            return inner

    fence_match = re.search(r"```(?:\w+)?\s*\n?(.*?)(?:```|$)", cleaned, re.DOTALL)
    if fence_match:
        inner = fence_match.group(1).strip()
        inner_parsed = _try_extract_json_code(inner)
        if inner_parsed:
            return inner_parsed
        return inner

    inner_parsed = _try_extract_json_code(cleaned)
    if inner_parsed:
        return inner_parsed

    return cleaned


def _try_extract_json_code(text: str) -> str | None:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("tool") == "write_file":
                args = data.get("args", {})
                content = args.get("content") or data.get("content", "")
                if content:
                    return _clean_content(content)
            content = data.get("content") or data.get("args", {}).get("content", "")
            if content:
                return _clean_content(content)
    except json.JSONDecodeError:
        pass
    return None


def _clean_content(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\s*", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    return cleaned


def _detect_lang(path: str) -> str | None:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    mapping = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "jsx": "javascript",
        "tsx": "typescript",
        "html": "html",
        "htm": "html",
        "css": "css",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "md": "markdown",
        "sql": "sql",
        "sh": "bash",
        "bat": "batch",
        "rb": "ruby",
        "go": "go",
        "rs": "rust",
        "java": "java",
        "cpp": "cpp",
        "c": "c",
        "h": "c",
        "hpp": "cpp",
    }
    return mapping.get(ext)


def _extract_function_names(code: str, language: str) -> list[str]:
    names = []

    if language in ("python",):
        matches = re.findall(r"^def (\w+)", code, re.MULTILINE)
        names.extend(matches)
    elif language in ("javascript", "typescript", "ts", "js"):
        matches = re.findall(r"\bfunction\s+(\w+)", code)
        names.extend(matches)
        matches = re.findall(r"\bconst\s+(\w+)\s*=\s*(?:async\s*)?\(", code)
        names.extend(matches)
        matches = re.findall(r"(\w+)\s*=\s*(?:async\s*)?\(", code)
        names.extend(matches)
        matches = re.findall(r"class\s+(\w+)", code)
        names.extend(matches)

    return list(set(names))


def _clean_pre_generated(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\s*", "", cleaned)
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    if cleaned.startswith("{") and '"content"' in cleaned:
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                inner = parsed.get("content", parsed.get("args", {}).get("content", ""))
                if inner:
                    cleaned = inner
        except json.JSONDecodeError:
            pass

    return cleaned
