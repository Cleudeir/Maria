from typing import Optional, Callable

SIMPLE_PROMPT = (
    "Implementation task: {task}\n\n"
    "IMPORTANT: Do exactly what is asked. Do NOT over-engineer.\n"
    "- Create only the files that are strictly necessary\n"
    "- Do not create extra folders, configs, or utilities unless explicitly asked\n"
    "- Keep everything in a single file if possible\n"
    "- No TDD, no tests, no architecture patterns unless asked\n"
    "- Just implement what the user requested"
)

COMPLEX_PROMPT = (
    "Generate a detailed implementation plan for: {task}\n\n"
    "ORGANIZATION RULES:\n"
    "- Split the code into separate files by domain and responsibility\n"
    "- Each file should contain only related functions that serve the same purpose\n"
    "- Each function must have a single, clear responsibility\n"
    "- Group utility functions separately from business logic\n"
    "- Keep configuration separate from code\n"
    "- Use clear, descriptive file and function names"
)

SIMPLE_SYSTEM = "You are a direct, no-nonsense coding assistant. Do exactly what is asked without over-engineering."
COMPLEX_SYSTEM = "You are a senior software engineer designing a well-structured implementation plan."


def generate_plan(
    task: str,
    get_generate_fn,
    stream_callback: Optional[Callable[[str], None]] = None,
    complexity: str = "complex",
) -> str:
    if complexity == "simple":
        prompt = SIMPLE_PROMPT.format(task=task)
        system_text = SIMPLE_SYSTEM
    else:
        prompt = COMPLEX_PROMPT.format(task=task)
        system_text = COMPLEX_SYSTEM

    response = get_generate_fn(
        system_text=system_text,
        user_text=prompt,
        progress_callback=stream_callback,
    )
    return response.strip()
