import re
from typing import List, Optional, Callable

def create_steps(
    plan: str,
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> List[str]:
    prompt = f"""You are a technical project manager. Read the implementation plan below and break it down into a list of specific, sequential, actionable steps.
Each step must:
- Be clear and focus on a single objective (e.g. "Create folder structure", "Implement factorial function in math_utils.py", "Create unit tests in test_math.py", "Run pytest and fix errors").
- Be numbered sequentially (e.g., 1., 2., 3.).

CRITICAL REQUIREMENT:
The list of steps must be extremely concise and contain at most 3 to 5 high-level sequential milestones. Do not create micro-steps (like editing a single line, styling a button, or writing individual files). Group related activities together into broad phases (for example: Phase 1: Implement HTML/CSS structure and core JavaScript logic; Phase 2: Run verification and fix bugs; Phase 3: Finalize). Fewer steps are highly preferred to minimize transitions.

Implementation Plan:
---
{plan}
---

Response Format:
Provide ONLY the numbered list of steps (e.g. "1. Step description\n2. Step description\n..."). No preamble, no other text.
"""
    response = get_generate_fn(
        system_text="You are a project manager assistant.",
        user_text=prompt,
        progress_callback=stream_callback,
    )

    response_cleaned = response.strip()

    # Parse numbered list
    steps = []
    for line in response_cleaned.splitlines():
        line = line.strip()
        # Match lines starting with a number followed by a dot or parenthesis, e.g., 1. or 1)
        match = re.match(r"^\d+[\.\)]\s*(.*)", line)
        if match:
            step_desc = match.group(1).strip()
            if step_desc:
                steps.append(step_desc)
        elif line and not line.startswith(("#", "-", "*")):
            # Fallback if no numbers but has text
            steps.append(line)
    return steps
