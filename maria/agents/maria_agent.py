import os
from typing import List, Dict, Tuple

from maria.llm import LLMClient
from maria.memory import load_system_prompt, load_lessons, add_task_history
from maria.tools import ToolExecutor

from maria.agents.utils import parse_agent_response, is_llm_response
from maria.agents.improve_prompt import improve_prompt
from maria.agents.generate_plan import generate_plan
from maria.agents.create_steps import create_steps
from maria.agents.verify_execution import verify_execution
from maria.agents.execute_steps import execute_steps


class MariaAgent:
    def __init__(
        self,
        workspace_dir: str,
        memory_dir: str,
        ollama_url: str = "http://localhost:11434",
        model_think: bool = False,
        provider_type: str = "ollama",
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.memory_dir = os.path.abspath(memory_dir)
        self.client = LLMClient(
            base_url=ollama_url,
            model_think=model_think,
            provider_type=provider_type,
        )
        self.executor = ToolExecutor(self.workspace_dir)
        self.execution_log = []
        self.errors_encountered = []

    def improve_prompt(self, task: str, lessons: List[Dict[str, str]], stream_callback=None) -> str:
        return improve_prompt(
            task, lessons,
            get_generate_fn=self.client.provider.generate,
            stream_callback=stream_callback,
        )

    def generate_plan(self, improved_prompt: str, stream_callback=None) -> str:
        return generate_plan(improved_prompt, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback)

    def create_steps(self, plan: str, stream_callback=None) -> List[str]:
        return create_steps(plan, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback)

    def execute_steps(
        self,
        steps: List[str],
        plan: str,
        system_message: str,
        stream_callback=None,
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
        )

    def verify_execution(self, plan: str, steps: List[str], stream_callback=None) -> Tuple[str, str]:
        return verify_execution(self.workspace_dir, plan, steps, get_generate_fn=self.client.provider.generate, stream_callback=stream_callback)

    def run(self, task: str, max_steps: int = 20) -> bool:
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
            base_prompt = "You are Maria, an agentic coding assistant. Use TDD."

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

        # --- Stage 1: Improve Prompt ---
        print("💡 Stage 1: Improving user prompt...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 1: Improving user prompt...",
            }
        )
        improved_prompt = self.improve_prompt(task, lessons)
        print(f"Improved Prompt:\n{improved_prompt}\n")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": f"Improved Prompt:\n{improved_prompt}",
            }
        )

        # --- Stage 2: Generate Plan ---
        print("📋 Stage 2: Generating complete plan...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 2: Generating complete plan...",
            }
        )
        plan = self.generate_plan(improved_prompt)
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

        # --- Stage 3: Create Steps ---
        print("🛠️ Stage 3: Creating execution steps...")
        self.execution_log.append(
            {
                "step": 0,
                "role": "system",
                "content": "Stage 3: Creating execution steps...",
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

        # --- Stage 5: Final Verification ---
        print("\n🔍 Stage 5: Verifying all plan was executed...")
        self.execution_log.append(
            {
                "step": len(self.execution_log),
                "role": "system",
                "content": "Stage 5: Verifying all plan was executed...",
            }
        )

        verdict, analysis_report = self.verify_execution(plan, steps)
        print(f"Analysis Report:\n{analysis_report}\n")
        print(f"Final Verdict: {verdict}")

        self.execution_log.append(
            {
                "step": len(self.execution_log),
                "role": "system",
                "content": f"Analysis Report:\n{analysis_report}\n\nFinal Verdict: {verdict}",
            }
        )

        # Save verification report
        try:
            with open(
                os.path.join(self.workspace_dir, "verification_report.md"),
                "w",
                encoding="utf-8",
            ) as f:
                f.write(
                    f"# Verification Report\n\nVerdict: {verdict}\n\n{analysis_report}"
                )
        except Exception as e:
            print(f"⚠️ Warning: Could not write verification_report.md: {e}")

        success = verdict == "SUCCESS"

        # 5. Record final task status in HTML memory
        status_str = "SUCCESS" if success else "FAILED"
        details_str = (
            analysis_report if success else f"Verification failed. Verdict: {verdict}"
        )
        try:
            add_task_history(self.memory_dir, task, status_str, details_str[:200])
        except Exception as e:
            print(f"⚠️ Failed to write task history: {e}")

        return success
