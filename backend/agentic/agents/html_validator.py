"""HTML/JS runtime validation using a headless browser.

After all files are generated, this module opens every HTML page in a real
browser (Chromium via Playwright) and collects:

- JavaScript runtime errors (uncaught exceptions, syntax errors)
- `console.error` / `console.warn` messages
- Failed network requests (404 on linked CSS/JS, broken images, etc.)
- Missing referenced local assets (e.g. `<link href="style.css">` but the
  file does not exist on disk)
- Page load lifecycle failures (DOMContentLoaded / load did not fire)

The output is a per-file list of human-readable issue strings that can be
fed back into the LLM as a fix context (mirroring the existing
`_retry_context` pattern in `verify_and_fix.py`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

try:
    from playwright.sync_api import (
        Error as PlaywrightError,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )

    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None  # type: ignore
    PlaywrightError = Exception  # type: ignore
    PlaywrightTimeoutError = Exception  # type: ignore


_MAX_VALIDATION_TIME_MS = 8000
_NAVIGATION_TIMEOUT_MS = 6000


def is_html_file(path: str) -> bool:
    p = path.lower().strip()
    return p.endswith(".html") or p.endswith(".htm")


def collect_html_files(file_paths: list[str]) -> list[str]:
    return [p for p in file_paths if is_html_file(p)]


def find_html_files_in_dir(output_dir: str) -> list[str]:
    if not output_dir or not os.path.isdir(output_dir):
        return []
    out: list[str] = []
    for root, _dirs, files in os.walk(output_dir):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, output_dir).replace(os.sep, "/")
            if is_html_file(rel):
                out.append(rel)
    return out


def _check_global_scope_collisions(output_dir: str) -> list[str]:
    """Detect duplicate top-level `const`, `let`, `class`, and `function` names
    across non-module JS files loaded by the same HTML page.

    When multiple `<script src="...">` (non-module) tags load JS files, they all
    share the same global scope. Declaring the same `const x` in two files will
    throw a SyntaxError.
    """
    html_re = re.compile(r'<script\s+(?:[^>]*?\s)?src=["\']([^"\']+\.(?:js|mjs))["\']', re.IGNORECASE)
    top_decl = re.compile(r'^\s*(?:const|let|var|class|function\s+\w+)\s+(\w+)', re.MULTILINE)

    for html_name in os.listdir(output_dir):
        if not html_name.endswith((".html", ".htm")):
            continue
        html_full = os.path.join(output_dir, html_name)
        try:
            html = Path(html_full).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        loaded_js: set[str] = set()
        for m in html_re.finditer(html):
            src = m.group(1).strip()
            if src.startswith(("http://", "https://", "//")):
                continue
            loaded_js.add(os.path.basename(src))

        js_files: list[str] = [
            js for js in loaded_js if os.path.isfile(os.path.join(output_dir, js))
        ]
        if len(js_files) < 2:
            continue

        for m in re.finditer(r'type\s*=\s*["\']module["\']', html, re.IGNORECASE):
            return []

        decl_map: dict[str, list[str]] = {}
        for js_name in js_files:
            try:
                content = Path(os.path.join(output_dir, js_name)).read_text(
                    encoding="utf-8", errors="replace"
                )
            except Exception:
                continue
            for m2 in top_decl.finditer(content):
                name = m2.group(1).strip()
                decl_map.setdefault(name, []).append(js_name)

        collisions = [(n, files) for n, files in decl_map.items() if len(files) > 1]
        if collisions:
            msgs: list[str] = []
            for name, files in collisions:
                msgs.append(
                    f"'{name}' is declared in {', '.join(files)} — "
                    f"the second file to load will crash with \"Cannot redeclare {name}\". "
                    f"FIX: wrap each file's code in `(() => {{ ... }})();` or move all "
                    f"declarations into a single file and reference them from the others."
                )
            return msgs
    return []


def _check_css_ids_not_in_html(output_dir: str) -> list[str]:
    """Detect CSS selectors referencing `#id` that don't match any element in the HTML."""
    id_in_css = re.compile(r'#([a-zA-Z_][\w-]*)')
    id_in_html = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']')

    issues: list[str] = []
    for html_name in os.listdir(output_dir):
        if not html_name.endswith((".html", ".htm")):
            continue
        html_full = os.path.join(output_dir, html_name)
        try:
            html = Path(html_full).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        html_ids = set()
        for m in id_in_html.finditer(html):
            html_ids.add(m.group(1))

        for css_name in os.listdir(output_dir):
            if not css_name.endswith(".css"):
                continue
            css_full = os.path.join(output_dir, css_name)
            try:
                css = Path(css_full).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for m in id_in_css.finditer(css):
                css_id = m.group(1).strip()
                if css_id not in html_ids:
                    issues.append(
                        f"CSS references id='{css_id}' but no element with that id exists in "
                        f"'{html_name}'. The CSS rules for that id will have no effect."
                    )
                    break
    return issues


def _check_module_mismatch(output_dir: str) -> list[str]:
    """Detect ES module `import` statements in JS files that are loaded
    via non-module <script> tags in the HTML. This causes a runtime
    SyntaxError: "Cannot use import statement outside a module".

    Two valid patterns:
    A) JS uses `import` -> HTML must use `<script type="module" src="...">`
    B) JS uses globals (window.X) -> HTML can use plain `<script src="...">`
    The check looks for `import` statements in JS files, then for how the
    HTML loads them.
    """
    js_files = [
        e for e in os.listdir(output_dir)
        if e.endswith((".js", ".mjs", ".jsx", ".ts", ".tsx"))
    ]
    issues: list[str] = []
    import_re = re.compile(r"^\s*import\s+", re.MULTILINE)
    for js_name in js_files:
        full = os.path.join(output_dir, js_name)
        if not os.path.isfile(full):
            continue
        try:
            content = Path(full).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not import_re.search(content):
            continue

        for html_name in os.listdir(output_dir):
            if not html_name.endswith((".html", ".htm")):
                continue
            html_full = os.path.join(output_dir, html_name)
            try:
                html = Path(html_full).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if js_name not in html:
                continue

            for m in re.finditer(
                r'<script\s+([^>]*?)src=["\']' + re.escape(js_name) + r'["\']([^>]*)>',
                html, re.IGNORECASE,
            ):
                attrs = (m.group(1) + " " + m.group(2)).lower()
                if "type=module" in attrs.replace('"', "").replace("'", "") or "type=\"module\"" in attrs or "type='module'" in attrs:
                    continue
                issues.append(
                    f"File '{js_name}' contains an `import` statement but the HTML loads it as "
                    f"<script src=\"{js_name}\"> (no type=\"module\"). This throws a "
                    f"SyntaxError: 'Cannot use import statement outside a module'. "
                    f"FIX: change the HTML to <script type=\"module\" src=\"{js_name}\"> "
                    f"(drop defer), or remove the import from '{js_name}' and use the global from the CDN script."
                )
                break
    return issues


def _check_bare_module_imports(output_dir: str) -> list[str]:
    """Detect ES module bare specifiers (e.g. `import x from 'foo'`) in JS files
    when there is no bundler config (no vite.config.*, webpack.config.*, etc.).
    Bare specifiers only work when served by a bundler; in a plain static
    page loaded via <script src="..."> they will throw a SyntaxError.
    """
    bundler_markers = (
        "vite.config",
        "vite.config.js",
        "vite.config.ts",
        "webpack.config",
        "rollup.config",
        "esbuild.config",
        "next.config",
        "nuxt.config",
        "svelte.config",
        "tsconfig.json",
    )
    has_bundler = False
    try:
        for entry in os.listdir(output_dir):
            if entry.startswith(bundler_markers) or entry in (
                "vite.config.js",
                "vite.config.ts",
                "webpack.config.js",
                "rollup.config.js",
            ):
                has_bundler = True
                break
    except Exception:
        pass

    if has_bundler:
        return []

    bare_re = re.compile(r"""import\s+(?:.+?\s+from\s+)?['"]([a-zA-Z@][^./'"][^'"]*)['"]""")
    issues: list[str] = []
    for entry in os.listdir(output_dir):
        if not entry.endswith((".js", ".mjs", ".jsx", ".ts", ".tsx")):
            continue
        full = os.path.join(output_dir, entry)
        if not os.path.isfile(full):
            continue
        try:
            content = Path(full).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in bare_re.finditer(content):
            spec = m.group(1).strip()
            if not spec or spec.startswith(("http://", "https://", "//", "node:", "file:")):
                continue
            if spec.startswith(".") or "/" not in spec and "." not in spec:
                if spec in ("three", "react", "vue", "express", "flask", "fastapi", "pygame"):
                    issues.append(
                        f"File '{entry}' uses bare import '{spec}' but the project has NO bundler "
                        f"(no vite.config / webpack.config / etc.). Plain <script src> cannot resolve "
                        f"bare specifiers. Either: (a) load this lib from a CDN, or (b) add a bundler."
                    )
                    break
    return issues


def _check_game_content_quality(output_dir: str, html_path: str) -> list[str]:
    """Check that game/environment generation produces non-trivial content.

    Catches the common case where the LLM generates a spinning cube but nothing
    resembling the requested game (LEGO city, GTA driving, etc.).
    Only fires when the task or file analysis suggests a game context.
    """
    if not html_path or not html_path.endswith((".html", ".htm")):
        return []

    html_full = os.path.join(output_dir, html_path)
    if not os.path.isfile(html_full):
        return []

    try:
        html = Path(html_full).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    js_files = []
    for match in re.finditer(r'<script\s[^>]*src=["\']([^"\']+\.js)["\']', html, re.IGNORECASE):
        src = match.group(1).strip()
        if not src.startswith(("http://", "https://", "//")):
            js_files.append(os.path.basename(src))

    combined_code = ""
    for js_name in js_files:
        js_full = os.path.join(output_dir, js_name)
        if os.path.isfile(js_full):
            try:
                combined_code += Path(js_full).read_text(encoding="utf-8", errors="replace") + "\n"
            except Exception:
                pass

    if not combined_code and os.path.isfile(html_full):
        combined_code = html

    if not combined_code.strip():
        return []

    code_lower = combined_code.lower()

    checks: list[tuple[str, str, str]] = [
        ("city", "No city generation found (expected buildings, streets, blocks).",
         r"build(?:ing|ings?)|street|road|block|grid|city|scene\.add"),
        ("vehicle", "No vehicle or car created (expected driving mechanics).",
         r"car|vehicle|wheel|chassis|body\.add|vehic"),
        ("controls", "No keyboard/mouse controls found (expected WASD/arrows for driving).",
         r"keyboard|keydown|keyup|keyCode|addEventListener\('key|onkey|isKeyDown|keys\["),
        ("multiple_entities", "Output only has a single object (cube), not a real game scene.",
         r"for\s*\(|\.push\(|geometry|material|Mesh\(|\.add\(|scene\.add"),
        ("physics", "No physics or movement logic found (expected acceleration, steering, collision).",
         r"velocity|acceleration|speed|friction|brake|steer|force|position\.x|position\.z|physics|collision|intersect"),
        ("ground", "No ground plane or road surface found.",
         r"ground|plane|floor|road|PlaneGeometry|RingGeometry|street"),
    ]
    issues: list[str] = []
    for _key, message, pattern in checks:
        if not re.search(pattern, combined_code, re.IGNORECASE | re.DOTALL):
            issues.append(message)

    cube_only_pattern = r"BoxGeometry\s*\([^)]*\)\s*.*\s*.*new\s+THREE\.Mesh"
    single_cube = re.search(cube_only_pattern, combined_code, re.DOTALL)
    has_additional_shapes = bool(re.search(r"(?:Box|Sphere|Cylinder|Cone|Torus|Capsule)Geometry", combined_code))
    if single_cube and not has_additional_shapes:
        issues.append("Output only contains a single BoxGeometry/THREE.Mesh — need buildings, vehicles, and a city layout in a 3D game.")

    building_count = len(re.findall(r"(?:BoxGeometry|CylinderGeometry)\s*\(", combined_code))
    if building_count < 3:
        issues.append(f"Only {building_count} geometry shape(s) created — a game with a city needs at least multiple buildings/entities.")

    return issues


def _check_missing_assets(html_path: str, output_dir: str) -> list[str]:
    """Static check: local <link>/<script>/<img> targets that do not exist."""
    full = os.path.join(output_dir, html_path)
    if not os.path.isfile(full):
        return [f"File does not exist on disk: {html_path}"]

    try:
        html = Path(full).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [f"Could not read file: {e}"]

    html_dir = os.path.dirname(full) or output_dir
    issues: list[str] = []

    existing_local: set[str] = set()
    try:
        for entry in os.listdir(output_dir):
            existing_local.add(entry)
    except Exception:
        pass

    for match in re.finditer(
        r"""<link[^>]+href=["']([^"']+)["']""", html, re.IGNORECASE
    ):
        href = match.group(1).strip()
        if not href or href.startswith(("http://", "https://", "//", "data:")):
            continue
        target = os.path.normpath(os.path.join(html_dir, href))
        if not os.path.isfile(target):
            basename = os.path.basename(href)
            suggestion = _suggest_closest(basename, existing_local)
            hint = f" (did you mean '{suggestion}'?)" if suggestion else ""
            issues.append(
                f"<link href=\"{href}\"> references missing file{hint}. "
                f"Files in output dir: {sorted(existing_local) or 'none'}"
            )

    for match in re.finditer(
        r"""<script[^>]+src=["']([^"']+)["']""", html, re.IGNORECASE
    ):
        src = match.group(1).strip()
        if not src or src.startswith(("http://", "https://", "//", "data:")):
            continue
        target = os.path.normpath(os.path.join(html_dir, src))
        if not os.path.isfile(target):
            basename = os.path.basename(src)
            suggestion = _suggest_closest(basename, existing_local)
            hint = f" (did you mean '{suggestion}'?)" if suggestion else ""
            issues.append(
                f"<script src=\"{src}\"> references missing file{hint}. "
                f"Files in output dir: {sorted(existing_local) or 'none'}"
            )

    for match in re.finditer(
        r"""<img[^>]+src=["']([^"']+)["']""", html, re.IGNORECASE
    ):
        src = match.group(1).strip()
        if not src or src.startswith(("http://", "https://", "//", "data:")):
            continue
        target = os.path.normpath(os.path.join(html_dir, src))
        if not os.path.isfile(target):
            issues.append(f"<img src=\"{src}\"> references missing file")

    return issues


def _suggest_closest(target: str, candidates: set[str]) -> str | None:
    if not candidates:
        return None
    t = target.lower()
    for c in candidates:
        if c.lower() == t:
            return c
    for c in candidates:
        cl = c.lower()
        if cl.startswith(t[: max(1, len(t) - 2)]) or t.startswith(cl[: max(1, len(cl) - 2)]):
            return c
    from difflib import get_close_matches
    matches = get_close_matches(target, list(candidates), n=1, cutoff=0.5)
    return matches[0] if matches else None


def _open_in_browser(file_url: str, on_console=None, on_pageerror=None, on_requestfailed=None) -> tuple[bool, list[str], list[str], list[str]]:
    """Open a URL in headless Chromium and collect diagnostics.

    Returns (loaded, console_errors, page_errors, network_errors).
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return False, ["Playwright not available"], [], []

    console_errors: list[str] = []
    page_errors: list[str] = []
    network_errors: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()

                def _console(msg):
                    try:
                        if msg.type in ("error", "warning"):
                            console_errors.append(f"[{msg.type}] {msg.text}")
                    except Exception:
                        pass

                def _pageerror(err):
                    try:
                        page_errors.append(str(err))
                    except Exception:
                        pass

                def _requestfailed(req):
                    try:
                        failure = req.failure or "unknown"
                        network_errors.append(
                            f"{req.method} {req.url} -> {failure}"
                        )
                    except Exception:
                        pass

                page.on("console", _console)
                page.on("pageerror", _pageerror)
                page.on("requestfailed", _requestfailed)

                page.set_default_navigation_timeout(_NAVIGATION_TIMEOUT_MS)
                try:
                    page.goto(file_url, wait_until="load", timeout=_NAVIGATION_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    console_errors.append("Page load timed out")
                except PlaywrightError as e:
                    console_errors.append(f"Navigation error: {e}")

                try:
                    page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass

                try:
                    page.wait_for_timeout(500)
                except Exception:
                    pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception as e:
        return False, [f"Browser launch failed: {e}"], [], []

    return True, console_errors, page_errors, network_errors


def validate_html_file(
    file_path: str,
    output_dir: str,
    progress_callback: Callable[[str], None] | None = None,
) -> list[str]:
    """Validate a single HTML file. Returns a list of issue strings (empty = OK)."""
    full = os.path.join(output_dir, file_path)
    if not os.path.isfile(full):
        return [f"File does not exist: {file_path}"]

    issues: list[str] = []
    issues.extend(_check_missing_assets(file_path, output_dir))
    issues.extend(_check_bare_module_imports(output_dir))
    issues.extend(_check_module_mismatch(output_dir))
    issues.extend(_check_global_scope_collisions(output_dir))
    issues.extend(_check_css_ids_not_in_html(output_dir))
    issues.extend(_check_game_content_quality(output_dir, file_path))

    if progress_callback:
        progress_callback(f"Opening {file_path} in headless browser...")

    file_url = "file://" + os.path.abspath(full)
    loaded, console_errs, page_errs, net_errs = _open_in_browser(file_url)

    if not loaded and console_errs:
        issues.extend(console_errs)
        return issues

    for e in page_errs:
        issues.append(f"JavaScript error: {e}")
    for e in console_errs:
        if "[error]" in e.lower() or "error" in e.lower() or "uncaught" in e.lower():
            issues.append(f"Console: {e}")
    for e in net_errs:
        url = e.split(" -> ")[0] if " -> " in e else e
        if any(local in url for local in (file_path, os.path.basename(file_path))):
            continue
        if "favicon" in url.lower():
            continue
        issues.append(f"Network failure: {e}")

    return issues


def validate_html_files(
    file_paths: list[str],
    output_dir: str,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, list[str]]:
    """Validate every HTML file in `file_paths`. Returns {file_path: [issues]}.

    Files with no issues are NOT included in the returned dict.
    """
    html_files = collect_html_files(file_paths)
    if not html_files:
        return {}

    results: dict[str, list[str]] = {}
    for path in html_files:
        try:
            issues = validate_html_file(path, output_dir, progress_callback)
        except Exception as e:
            issues = [f"Validator crashed: {e}"]
        if issues:
            results[path] = issues
    return results
