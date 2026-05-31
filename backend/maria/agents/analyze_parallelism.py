import json
import re
from typing import List, Optional, Callable


def analyze_parallelism(
    steps: List[str],
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> List[List[int]]:
    """
    Analyzes steps and groups them into parallel batches.
    Returns a list of groups, e.g. [[0,1], [2], [3,4]] means:
    - Steps 0 and 1 can run in parallel
    - Step 2 runs alone
    - Steps 3 and 4 can run in parallel
    """
    steps_text = "\n".join(f"{i}. {step}" for i, step in enumerate(steps))

    prompt = f"""Given these execution steps, group them into parallel batches.
Steps that are independent of each other (don't depend on each other's output) can run in parallel.
Steps that depend on previous steps must run sequentially.

Steps:
{steps_text}

Return a JSON array of arrays. Each inner array contains step indices that can run in parallel.
Example: [[0,1],[2],[3,4]] means steps 0,1 parallel, then step 2, then steps 3,4 parallel.

Return ONLY the JSON array. No other text."""

    response = get_generate_fn(
        system_text="You are a parallel execution planner. Analyze step dependencies and group independent steps for parallel execution.",
        user_text=prompt,
        progress_callback=stream_callback,
    )

    # Parse the response
    response = response.strip()

    # Try to extract JSON array from response
    try:
        # Find JSON array in response
        match = re.search(r'\[[\s\S]*\]', response)
        if match:
            groups = json.loads(match.group())
            # Validate structure
            if isinstance(groups, list) and all(isinstance(g, list) for g in groups):
                # Ensure all indices are valid
                valid_groups = []
                for group in groups:
                    valid_indices = [i for i in group if isinstance(i, int) and 0 <= i < len(steps)]
                    if valid_indices:
                        valid_groups.append(valid_indices)
                if valid_groups:
                    return valid_groups
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: sequential execution (each step alone)
    return [[i] for i in range(len(steps))]
