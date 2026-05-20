def generate_plan(improved_prompt: str, get_generate_fn) -> str:
    prompt = f"""You are a senior software architect. Based on the following detailed task description, generate a complete, comprehensive implementation plan.
The plan must describe:
1. Architecture & Design Choices
2. Target File Structure (files to create, files to modify)
3. Step-by-step implementation strategy
4. Testing strategy (how to verify each component)

Important: The plan should be descriptive only. Do not include code snippets, pseudocode, or direct implementation commands. Explain what to do, but do not write the code itself.

Detailed Task Description:
---
{improved_prompt}
---

Response Format:
Provide the complete plan in clear Markdown. No conversational preamble.
"""
    response = get_generate_fn(
        system_text="You are a software architect assistant.",
        user_text=prompt,
    )
    return response.strip()
