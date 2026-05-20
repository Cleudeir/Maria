from typing import List, Dict

def improve_prompt(task: str, lessons: List[Dict[str, str]], get_generate_fn) -> str:
    prompt = f"""Improve the following user task prompt to be clear, concise, and structured. Keep the original intent intact.

Original User Task:
{task}

Provide only the improved prompt. No preamble, no XML tags.
"""
    response = get_generate_fn(
        system_text="You are a prompt optimizer assistant.",
        user_text=prompt,
    )
    return response.strip()
