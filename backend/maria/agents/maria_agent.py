import os
from typing import List, Dict, Optional, Tuple

from maria.llm import LLMClient
from maria.memory import load_system_prompt, load_lessons, add_task_history
from maria.tools import ToolExecutor

from maria.agents.utils import parse_agent_response, is_llm_response
from maria.agents.generate_plan import generate_plan
from maria.agents.generate_structure import generate_structure
from maria.agents.regenerate_plan import regenerate_plan
from maria.agents.create_steps import create_steps
from maria.agents.execute_steps import execute_steps


class MariaAgent:
    def __init__(
        self,
        workspace_dir: str,
        memory_dir: str,
        base_url: Optional[str] = None,
        model_think: bool = False,
        provider_type: str = "llamacpp",
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.memory_dir = os.path.abspath(memory_dir)
        self.client = LLMClient(
            base_url=base_url,
            model_think=model_think,
            provider_type=provider_type,
        )
        self.executor = ToolExecutor(self.workspace_dir)
        self.execution_log = []
        self.errors_encountered = []

    def generate_plan(self, task: str, stream_callback=None, complexity: str = "complex") -> str:
        return generate_plan(task, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback, complexity=complexity)

    def generate_structure(self, plan: str, stream_callback=None, complexity: str = "complex") -> str:
        return generate_structure(plan, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback, complexity=complexity)

    def regenerate_plan(self, plan: str, structure: str, stream_callback=None) -> str:
        return regenerate_plan(plan, structure, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback)

    def create_steps(self, plan: str, stream_callback=None, complexity: str = "complex") -> List[str]:
        return create_steps(plan, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback, complexity=complexity)

    def execute_steps(
        self,
        steps: List[str],
        plan: str,
        system_message: str,
        stream_callback=None,
        complexity: str = "complex",
        on_file_created=None,
    ) -> Tuple[bool, List[str]]:
        return execute_steps(
            steps=steps,
            plan=plan,
            system_message=system_message,
            executor=self.executor,
            execution_log=self.execution_log,
            errors_encountered=self.errors_encountered,
            get_generate_fn=self.client.provider.generate,
            stream_callback=stream_callback,
            complexity=complexity,
            on_file_created=on_file_created,
        )

    def run(self, task: str) -> bool:
        """
        Runs the agentic loop to solve a task.
        """
        print(f"🚀 Starting Maria Agent...")
        print(f"📂 Workspace: {self.workspace_dir}")
        print(f"🧠 Memory: {self.memory_dir}")
        print(f"📋 Task: {task}\n")

        self.execution_log = []
        self.errors_encountered = []

        # 1. Load memories
        try:
            base_prompt = load_system_prompt(self.memory_dir)
        except Exception as e:
            print(f"⚠️ Error loading system prompt, using fallback. Error: {e}")
            base_prompt = "You are Maria, an agentic coding assistant."

        lessons = load_lessons(self.memory_dir)
        lessons_prompt = ""
        if lessons:
            lessons_prompt = "\n\nCRITICAL: Lessons learned from previous runs to prevent repeating mistakes:\n"
            for i, l in enumerate(lessons, 1):
                lessons_prompt += f"Lesson {i}: {l['title']}\n"
                if l.get("error"):
                    lessons_prompt += f"  Previous Error: {l['error']}\n"
                lessons_prompt += f"  Correction/Resolution: {l['resolution']}\n"

        system_message = base_prompt + lessons_prompt

        # --- Stage 1: Generate Plan ---
        print("📋 Stage 1: Generating complete plan...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 1: Generating complete plan...",
            }
        )
        plan = self.generate_plan(task)
        print(f"Complete Plan:\n{plan}\n")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"Complete Plan:\n{plan}"}
        )

        # Save plan overview to file for compatibility
        try:
            plan_dir = os.path.join(self.workspace_dir, "plan")
            os.makedirs(plan_dir, exist_ok=True)
            with open(os.path.join(plan_dir, "plan.md"), "w", encoding="utf-8") as f:
                f.write(plan)
        except Exception as e:
            print(f"⚠️ Warning: Could not write plan.md: {e}")

        # --- Stage 2: Create Steps ---
        print("🛠️ Stage 2: Creating execution steps...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 2: Creating execution steps...",
            }
        )
        steps = self.create_steps(plan)
        steps_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
        print(f"Execution Steps:\n{steps_str}\n")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"Execution Steps:\n{steps_str}"}
        )

        if not steps:
            print("❌ No execution steps generated. Aborting.")
            return False

        # --- Stage 4: Execute Steps ---
        overall_success, completed_step_summaries = self.execute_steps(
            steps=steps,
            plan=plan,
            system_message=system_message,
        )

        if not overall_success:
            print("❌ Execution interrupted due to step failure.")
            # Record final status
            try:
                add_task_history(
                    self.memory_dir,
                    task,
                    "FAILED",
                    f"Step execution failed at step {len(completed_step_summaries) + 1}",
                )
            except Exception:
                pass
            return False

        # Record final task status in HTML memory
        try:
            add_task_history(
                self.memory_dir, task, "SUCCESS",
                f"All {len(steps)} steps executed successfully."
            )
        except Exception as e:
            print(f"⚠️ Failed to write task history: {e}")

        return True
