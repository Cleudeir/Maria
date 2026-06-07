from collections.abc import Callable

from .generate_files import generate_single_file
from .html_validator import (
    collect_html_files,
    is_html_file,
    validate_html_file,
)
from .manifest_extractor import get_file_spec


_MAX_FIX_RETRIES = 3
_CONTENT_QUALITY_KEYWORDS = (
    "city", "vehicle", "controls", "keyboard", "physics",
    "single cube", "no building", "no car",
    "multiple entities", "ground plane",
)


def _is_content_quality_issue(issues: list[str]) -> bool:
    return any(kw in issue.lower() for issue in issues for kw in _CONTENT_QUALITY_KEYWORDS)


def _make_retry_context(issues: list[str], attempt: int, max_retries: int) -> str:
    base = "Verification found issues:\n" + "\n".join(f"- {iss}" for iss in issues)
    if attempt == 0:
        base += (
            "\n\nFIX THE CODE ABOVE. The game is too minimal — missing world buildings, "
            "vehicle, or controls. Generate a complete working implementation with real "
            "city blocks, a drivable car, WASD controls, and a proper 3D scene. "
            "Do NOT just rotate a cube. Use functions like createCity, createVehicle, "
            "setupControls, updateVehicle, and animate."
        )
    elif attempt == 1:
        base += (
            "\n\nURGENT: The previous fix was STILL insufficient. You MUST generate a "
            "complete game scene — at least 5 buildings arranged in a city grid, "
            "a ground plane, a car/vehicle on the ground, WASD/arrow key controls, "
            "and a game loop with real physics. The variable names and function "
            "signatures must match what was requested. NO spinning cube."
        )
    else:
        base += (
            "\n\nCRITICAL: This is your LAST attempt. The output keeps being a stub. "
            "Write a complete game NOW. Multiple buildings at different positions. "
            "A vehicle with steering/acceleration/braking. Keyboard event listeners. "
            "A ground plane. Responsive resize. Real 3D scene with lights and shadows. "
            "Do NOT regenerate stub code."
        )
    return base


def verify_all_files(
    manifest: dict,
    files_generated: list[dict],
    task: str,
    system_prompt: str,
    get_generate_fn: Callable,
    stream_callback: Callable[[str], None] | None,
    output_dir: str,
    run_html_validation: bool = True,
) -> list[dict]:
    project = manifest.get("project", {})
    language = project.get("language", "python")
    framework = project.get("framework", "vanilla")

    final_results = []

    for result in files_generated:
        file_path = result.get("path", "")
        content = result.get("content", "")

        if not result.get("success"):
            final_results.append(result)
            continue

        file_spec = get_file_spec(manifest, file_path)
        if not file_spec:
            final_results.append(result)
            continue

        current_result = result
        fix_retry_count = 0

        while fix_retry_count <= _MAX_FIX_RETRIES:
            issues = []

            missing_funcs = check_functions_exist(current_result.get("content", ""), file_spec)
            if missing_funcs:
                issues.append(f"Missing functions: {', '.join(missing_funcs)}")

            missing_imports = check_imports(current_result.get("content", ""), file_spec, framework)
            if missing_imports:
                issues.append(f"Missing imports: {', '.join(missing_imports)}")

            if run_html_validation and is_html_file(file_path):
                try:
                    browser_issues = validate_html_file(
                        file_path=file_path,
                        output_dir=output_dir,
                        progress_callback=stream_callback,
                    )
                except Exception as e:
                    browser_issues = [f"HTML validation crashed: {e}"]

                if browser_issues:
                    issues.append(
                        "Browser validation found errors in this page: "
                        + " | ".join(browser_issues)
                    )

            if not issues:
                final_results.append(current_result)
                break

            non_cosmetic = [i for i in issues if "CSS reference" not in i.lower()]
            if non_cosmetic:
                if fix_retry_count >= _MAX_FIX_RETRIES:
                    current_result["warning"] = (
                        f"Could not fix after {_MAX_FIX_RETRIES+1} attempts. "
                        f"Last issues: {'; '.join(issues[:3])}"
                    )
                    final_results.append(current_result)
                    break
            else:
                current_result.setdefault("notice", []).extend(issues)
                final_results.append(current_result)
                break

            file_spec_copy = dict(file_spec)
            file_spec_copy["_retry_context"] = _make_retry_context(
                issues, fix_retry_count, _MAX_FIX_RETRIES
            )

            fixed_result = generate_single_file(
                file_spec=file_spec_copy,
                task=task,
                system_prompt=system_prompt,
                get_generate_fn=get_generate_fn,
                stream_callback=stream_callback,
                output_dir=output_dir,
                language=language,
                framework=framework,
            )

            if not fixed_result.get("success"):
                current_result["warning"] = f"Fix attempt {fix_retry_count+1} failed: {fixed_result.get('error', 'unknown')}"
                final_results.append(current_result)
                break

            current_result = fixed_result
            fix_retry_count += 1

    return final_results


def check_functions_exist(code: str, file_spec: dict) -> list[str]:
    from .generate_files import check_functions_exist as _check
    return _check(code, file_spec)


def check_imports(code: str, file_spec: dict, framework: str = "vanilla") -> list[str]:
    from .generate_files import check_imports as _check
    return _check(code, file_spec, framework)
