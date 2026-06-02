import re
from typing import Optional, Callable

PROMPT = """You are a project architect. Based on the implementation plan below, list all files that will be created.

Rules:
- List every file that needs to be created
- Use a JSON array of relative file path strings
- Do NOT include directories, only files

Example output:
PROJECT_STRUCTURE: ["src/main.py", "src/utils.py", "tests/test_main.py", "README.md"]

Implementation Plan:
---
{plan}
---

Response: Output ONLY the PROJECT_STRUCTURE: line with the JSON array. No other text."""


def generate_structure(
    plan: str,
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    prompt = PROMPT.format(plan=plan)
    system_text = "You are a project architect assistant."

    response = get_generate_fn(
        system_text=system_text,
        user_text=prompt,
        progress_callback=stream_callback,
    )

    # Extract the PROJECT_STRUCTURE JSON array
    match = re.search(
        r"PROJECT_STRUCTURE:\s*(\[[\s\S]*?\])",
        response,
    )
    if match:
        return match.group(1).strip()
    # Fallback: return the whole response cleaned
    return response.strip()
