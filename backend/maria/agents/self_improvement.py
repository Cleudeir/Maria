import re
from typing import List, Dict, Any
from maria.llm import LLMClient
from maria.memory import load_system_prompt, load_lessons, add_lesson, save_system_prompt, save_lessons
from maria.agents.utils import parse_self_improvement_response, parse_compacted_lessons_response


class SelfImprovementAgent:
    def __init__(self, memory_dir: str, base_url: str = "http://localhost:11434", model_think: bool = False):
        self.memory_dir = memory_dir
        self.client = LLMClient(base_url=base_url, model_think=model_think, provider_type="llamacpp")

    def improve(
        self,
        task: str,
        execution_log: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
        compaction_threshold: int = 10,
    ) -> bool:
        """
        Analyzes the execution, saves lessons learned, and refines the system prompt.
        """
        print("\n🧠 Running Self-Improvement Meta-Agent...")

        # Load current state
        try:
            current_prompt = load_system_prompt(self.memory_dir)
        except Exception as e:
            print(f"Error loading system prompt for self-improvement: {e}")
            return False

        existing_lessons = load_lessons(self.memory_dir)

        # Format the log and errors for context (with truncation to avoid exceeding context window)
        trace_str = ""
        trace_char_limit = 30000
        for turn in execution_log:
            role = "Agent" if turn["role"] == "assistant" else "Tool/System"
            content = turn['content']
            if len(content) > 500:
                content = content[:250] + "\n... [truncated] ...\n" + content[-250:]
            trace_str += f"\n[{role}]:\n{content}\n"
            if len(trace_str) > trace_char_limit:
                trace_str = trace_str[:trace_char_limit] + "\n... [trace truncated due to length] ...\n"
                break

        errors_str = ""
        if errors:
            for i, err in enumerate(errors, 1):
                errors_str += f"\nError {i}:\n"
                if "tool" in err:
                    errors_str += f"  Tool: {err['tool']}\n"
                    errors_str += f"  Arguments: {str(err['args'])[:200]}\n"
                errors_str += f"  Message: {(err.get('error') or err.get('message'))[:500]}\n"
                if len(errors_str) > 5000:
                    errors_str += "\n... [remaining errors omitted] ...\n"
                    break
        else:
            errors_str = (
                "None. The task completed successfully without tool or formatting errors."
            )

        # Format existing lessons
        existing_lessons_str = ""
        if existing_lessons:
            for i, l in enumerate(existing_lessons, 1):
                existing_lessons_str += f"Lesson {i}: {l['title']}\n  Error: {l['error']}\n  Resolution: {l['resolution']}\n"
        else:
            existing_lessons_str = "No lessons learned logged yet."

        # Meta prompt
        # Estimate total meta_prompt size; if too large, truncate further
        meta_prompt_preview = f"""You are the Self-Improvement Meta-Agent for Maria (an agentic AI assistant powered by Qwen 3.5 4B).
Your job is to analyze the agent's performance on its last task and help it improve.

Here is the task Maria worked on:
---
{task}
---

Here is the trace of Maria's steps:
---
{trace_str}
---

Here are the specific errors encountered:
---
{errors_str}
---

Here is Maria's current System Prompt:
---
{current_prompt}
---

Here are Maria's existing Lessons Learned:
---
{existing_lessons_str}
---

YOUR MISSION:
1. Analyze Maria's performance. Focus on what caused errors or inefficiencies.
2. If there were errors:
   - Formulate new Lessons Learned to prevent these errors in future runs.
   - For each lesson, write:
     * A clear Title describing the error situation.
     * The Error message that occurred.
     * The Resolution / actionable guidance for the agent.
3. Review the current System Prompt. Refine it if necessary. Add specific rules, tips, or clarifications to avoid the errors seen in this run, while keeping the JSON structure, TDD rules, and available tools exactly the same.
   Note: Your improved system prompt should focus on the '## DYNAMIC GUIDELINES & LESSONS LEARNED:' section. You may output just the refined guidelines or the complete prompt, but the base tools and JSON rules must be preserved.

Output your response using the following XML tags:

<analysis>
Describe your analysis of Maria's performance, why the errors occurred, and how they can be fixed.
</analysis>

<new_lessons>
  <lesson>
    <title>Lesson Title</title>
    <error>Error description or message</error>
    <resolution>Actionable advice on what to do instead or how to avoid the error</resolution>
  </lesson>
  <!-- Add more lessons if there were multiple distinct errors -->
</new_lessons>

<improved_system_prompt>
Write the updated dynamic guidelines or the complete system prompt here. Focus on the rules under '## DYNAMIC GUIDELINES & LESSONS LEARNED:'.
</improved_system_prompt>
"""

        try:
            # Query the model for self-improvement
            response_text = self.client.generate(
                system=None,
                prompt=meta_prompt,
            )

            analysis, new_lessons, improved_prompt = (
                parse_self_improvement_response(response_text)
            )

            print("\n🔍 Meta-Agent Analysis:")
            print(analysis)

            # Save new lessons
            if new_lessons:
                print(f"\n📝 Logged {len(new_lessons)} new lesson(s) to memory:")
                for lesson in new_lessons:
                    print(f"  - Title: {lesson['title']}")
                    print(f"    Error: {lesson['error']}")
                    print(f"    Resolution: {lesson['resolution']}")
                    add_lesson(
                        self.memory_dir,
                        lesson["title"],
                        lesson["error"],
                        lesson["resolution"],
                    )
            else:
                print("\nℹ️ No new lessons were logged.")

            # Update system prompt if modified, keeping base prompt safe
            if improved_prompt and improved_prompt != current_prompt:
                marker = "## DYNAMIC GUIDELINES & LESSONS LEARNED:"
                if marker in improved_prompt:
                    dynamic_part = improved_prompt.split(marker)[1].strip()
                else:
                    dynamic_part = improved_prompt.strip()

                if dynamic_part:
                    # Extract static base prompt
                    if marker in current_prompt:
                        base_prompt = current_prompt.split(marker)[0] + marker + "\n"
                    else:
                        base_prompt = current_prompt.rstrip() + "\n\n" + marker + "\n"

                    final_prompt = base_prompt + dynamic_part
                    print("\n✨ Updating System Prompt with improvements...")
                    save_system_prompt(self.memory_dir, final_prompt)
                else:
                    print("\nℹ️ System prompt remains unchanged (empty dynamic section).")
            else:
                print("\nℹ️ System prompt remains unchanged.")

            # Trigger automatic memory compaction if threshold exceeded
            all_lessons = load_lessons(self.memory_dir)
            if len(all_lessons) > compaction_threshold:
                self.compact_lessons(all_lessons, compaction_threshold)

            print("✅ Self-improvement completed.")
            return True

        except Exception as e:
            print(f"❌ Self-improvement failed: {e}")
            return False

    def _update_system_prompt_with_lessons(
        self, lessons_list: List[Dict[str, str]]
    ) -> None:
        try:
            current_prompt = load_system_prompt(self.memory_dir)
            marker = "## DYNAMIC GUIDELINES & LESSONS LEARNED:"
            if marker in current_prompt:
                base_prompt = current_prompt.split(marker)[0] + marker + "\n"
            else:
                base_prompt = current_prompt.rstrip() + "\n\n" + marker + "\n"

            dynamic_part = ""
            for lesson in lessons_list:
                dynamic_part += f"### {lesson['title']}\n"
                if lesson.get("error"):
                    dynamic_part += f"- Typical Error: {lesson['error']}\n"
                dynamic_part += f"- Resolution: {lesson['resolution']}\n\n"

            final_prompt = base_prompt + dynamic_part.strip()
            save_system_prompt(self.memory_dir, final_prompt)
            print("✨ System prompt dynamic guidelines updated.")
        except Exception as pe:
            print(f"Warning: Failed to update system prompt: {pe}")

    def compact_lessons(
        self, lessons: List[Dict[str, str]], compaction_threshold: int = 10
    ) -> bool:
        """
        Uses the LLM to consolidate and compact the list of lessons learned.
        """
        print(
            f"\n🧹 Compacting and consolidating lessons learned list (current count: {len(lessons)})..."
        )

        # Deduplicate lessons by title first to reduce context size
        unique_lessons = []
        seen_titles = set()
        for l in lessons:
            t_lower = l["title"].lower().strip()
            if t_lower not in seen_titles:
                seen_titles.add(t_lower)
                unique_lessons.append(l)

        # If deduplication brings count to threshold or fewer, apply and return
        if len(unique_lessons) <= compaction_threshold:
            print(
                f"✅ Programmatic deduplication reduced lessons to {len(unique_lessons)} (<= {compaction_threshold}). Bypassing LLM compaction."
            )
            save_lessons(self.memory_dir, unique_lessons)
            self._update_system_prompt_with_lessons(unique_lessons)
            return True

        # Otherwise, run LLM-based compaction on the unique lessons list
        lessons_str = ""
        for i, l in enumerate(unique_lessons, 1):
            lessons_str += f"Lesson {i}: {l['title']}\n  Error: {l['error']}\n  Resolution: {l['resolution']}\n\n"

        compact_prompt = f"""You are the Memory Compactor for Maria (an agentic AI assistant powered by Qwen 3.5 4B).
The lessons learned list has grown too long. Your goal is to review the current list of lessons and merge redundant items, group related topics, and synthesize them into a concise, unified list of key lessons (aim for 4 to 6 high-quality, comprehensive lessons instead of many duplicate or overlapping ones).

Here is the current list of lessons learned:
---
{lessons_str}
---

MISSION:
- Analyze all lessons.
- Identify duplicate or overlapping rules (e.g. multiple lessons about JSON formatting, multiple lessons about TDD flow, multiple lessons about folder paths).
- Merge them into single, comprehensive lessons with clear Titles, summary of Errors, and consolidated Resolutions.
- Keep the guidance actionable and precise.

Output your response using the following XML format:
<compacted_lessons>
  <lesson>
    <title>Consolidated Lesson Title</title>
    <error>Summary of typical error messages (e.g. directory traversal, invalid tags)</error>
    <resolution>Actionable, comprehensive resolution guidance</resolution>
  </lesson>
  <!-- Repeat for other consolidated lessons (aim for 4-6 lessons total) -->
</compacted_lessons>
"""
        try:
            response_text = self.client.generate(
                system=None,
                prompt=compact_prompt,
            )
            compacted_lessons = parse_compacted_lessons_response(response_text)

            if compacted_lessons:
                print(
                    f"✅ Successfully compacted lessons from {len(lessons)} to {len(compacted_lessons)}."
                )
                save_lessons(self.memory_dir, compacted_lessons)
                self._update_system_prompt_with_lessons(compacted_lessons)
                return True
            else:
                print(
                    "⚠️ Memory Compaction returned no valid consolidated lessons. Falling back to unique deduplicated lessons."
                )
                save_lessons(self.memory_dir, unique_lessons)
                self._update_system_prompt_with_lessons(
                    unique_lessons[:10]
                )  # Keep prompt compact
                return False
        except Exception as e:
            print(
                f"❌ Memory Compaction failed: {e}. Falling back to unique deduplicated lessons."
            )
            save_lessons(self.memory_dir, unique_lessons)
            self._update_system_prompt_with_lessons(
                unique_lessons[:10]
            )  # Keep prompt compact
            return False
