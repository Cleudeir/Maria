from typing import Optional, Callable

PROMPT = """You are a technical project manager. You have an initial implementation plan and a project structure that defines the exact file paths.

Your task: Rewrite the plan so that EVERY file reference uses the EXACT path from the project structure below.

PROJECT STRUCTURE (exact file paths to use):
---
{structure}
---

INITIAL PLAN:
---
{plan}
---

RULES:
- Use the EXACT file paths from the structure above (e.g. "class/BaseEntity.ts" NOT "BaseEntity.ts" or "src/BaseEntity.ts")
- Every time you mention a file, use its full path from the structure
- Keep the plan concise and actionable
- The plan must describe the APPROACH only. NEVER include code, pseudocode, or implementation text
- Group related files into logical steps
- Each step should reference specific files by their exact structure path

Output the rewritten plan only. No preamble, no other text."""


def regenerate_plan(
    plan: str,
    structure: str,
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    prompt = PROMPT.format(plan=plan, structure=structure)
    system_text = "You are a technical project manager. Rewrite plans to use exact file paths from the project structure."

    response = get_generate_fn(
        system_text=system_text,
        user_text=prompt,
        progress_callback=stream_callback,
    )
    return response.strip()
