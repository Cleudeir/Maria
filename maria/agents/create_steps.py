import re
from typing import List

def create_steps(plan: str, get_generate_fn) -> List[str]:
    prompt = f"""You are a technical project manager. Read the implementation plan below and break it down into a list of specific, sequential, actionable steps.
Each step must:
- Be clear and focus on a single objective (e.g. "Create folder structure", "Implement factorial function in math_utils.py", "Create unit tests in test_math.py", "Run pytest and fix errors").
- Be numbered sequentially (e.g., 1., 2., 3.).

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
