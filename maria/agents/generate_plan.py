from typing import Optional, Callable

def generate_plan(
    task: str,
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    prompt = (
        f"Generate a detailed implementation plan for: {task}\n\n"
        "ORGANIZATION RULES:\n"
        "- Split the code into separate files by domain and responsibility\n"
        "- Each file should contain only related functions that serve the same purpose\n"
        "- Each function must have a single, clear responsibility\n"
        "- Group utility functions separately from business logic\n"
        "- Keep configuration separate from code\n"
        "- Use clear, descriptive file and function names"
    )
    response = get_generate_fn(
        system_text="You are a senior software engineer designing a well-structured implementation plan.",
        user_text=prompt,
        progress_callback=stream_callback,
    )
    return response.strip()
