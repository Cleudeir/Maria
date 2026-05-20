from typing import List, Dict, Optional, Callable

def improve_prompt(
    task: str,
    lessons: List[Dict[str, str]],
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    prompt = f"""Improve the following user task prompt to be clear, concise, and structured. Keep the original intent intact.

Original User Task:
{task}

Provide only the improved prompt. No preamble, no XML tags.
"""
    response = get_generate_fn(
        system_text="You are a prompt optimizer assistant.",
        user_text=prompt,
        progress_callback=stream_callback,
    )
    return response.strip()
