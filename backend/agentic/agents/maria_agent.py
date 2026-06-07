import contextlib
import os

from agentic.agents.generate_files import generate_all_files
from agentic.agents.generate_plan_v2 import generate_analysis, generate_plan_v2
from agentic.agents.install_runner import run_test_commands
from agentic.agents.manifest_extractor import extract_manifest
from agentic.agents.verify_and_fix import verify_all_files
from agentic.llm import LLMClient
from agentic.memory import add_task_history, load_lessons, load_system_prompt
from agentic.tools import ToolExecutor


class MariaAgent:
    def __init__(
        self,
        workspace_dir: str,
        memory_dir: str,
        base_url: str | None = None,
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

    def generate_analysis(
        self,
        task: str,
        stream_callback=None,
        lessons: str = "",
    ) -> dict | None:
        return generate_analysis(
            task,
            get_generate_fn=self.client.provider.generate,
            stream_callback=stream_callback,
            lessons=lessons,
        )

    def generate_plan_v2(
        self,
        task: str,
        stream_callback=None,
        system_prompt: str = "",
        lessons: str = "",
        complexity: str = "complex",
        analysis: dict | None = None,
    ) -> str:
        return generate_plan_v2(
            task,
            get_generate_fn=self.client.provider.generate,
            stream_callback=stream_callback,
            system_prompt=system_prompt,
            lessons=lessons,
            complexity=complexity,
            analysis=analysis,
        )

    def extract_manifest(self, plan_yaml: str):
        return extract_manifest(plan_yaml)

    def generate_files_v2(
        self,
        manifest,
        generation_order,
        task: str,
        system_message: str,
        stream_callback=None,
        output_dir: str = "",
    ):
        if not output_dir:
            output_dir = os.path.join(self.workspace_dir, "output")
        return generate_all_files(
            manifest=manifest,
            generation_order=generation_order,
            task=task,
            system_prompt=system_message,
            get_generate_fn=self.client.provider.generate,
            stream_callback=stream_callback,
            output_dir=output_dir,
        )

    def verify_and_fix(
        self,
        manifest,
        files_generated,
        task: str,
        system_message: str,
        stream_callback=None,
        output_dir: str = "",
    ):
        if not output_dir:
            output_dir = os.path.join(self.workspace_dir, "output")
        return verify_all_files(
            manifest=manifest,
            files_generated=files_generated,
            task=task,
            system_prompt=system_message,
            get_generate_fn=self.client.provider.generate,
            stream_callback=stream_callback,
            output_dir=output_dir,
        )


    def run(self, task: str) -> bool:
        return self.run_v2(task)

    def run_v2(self, task: str) -> bool:
        print("🚀 Starting Maria Agent V2...")
        print(f"📂 Workspace: {self.workspace_dir}")
        print(f"🧠 Memory: {self.memory_dir}")
        print(f"📋 Task: {task}\n")

        self.execution_log = []
        self.errors_encountered = []

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

        # Stage 1: Generate YAML Plan
        print("📋 Stage 1: Generating YAML plan...")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": "Stage 1: Generating YAML plan..."}
        )
        plan_yaml = self.generate_plan_v2(
            task,
            system_prompt=base_prompt,
            lessons=lessons_prompt,
        )
        print(f"YAML Plan:\n{plan_yaml}\n")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"YAML Plan:\n{plan_yaml}"}
        )

        if not plan_yaml:
            print("❌ Empty plan generated. Aborting.")
            return False

        # Stage 2: Extract Manifest
        print("📊 Stage 2: Extracting manifest...")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": "Stage 2: Extracting manifest..."}
        )
        try:
            manifest, generation_order = self.extract_manifest(plan_yaml)
        except ValueError as e:
            print(f"❌ Failed to extract manifest: {e}")
            self.errors_encountered.append({"step": 0, "type": "manifest_error", "message": str(e)})
            return False
        print(f"Files to generate ({len(generation_order)}): {', '.join(generation_order)}")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"Generation order ({len(generation_order)} files): {', '.join(generation_order)}"}
        )

        # Stage 3: Generate Files
        print("🔨 Stage 3: Generating files...")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": "Stage 3: Generating files..."}
        )
        output_dir = os.path.join(self.workspace_dir, "output")
        results = self.generate_files_v2(
            manifest=manifest,
            generation_order=generation_order,
            task=task,
            system_message=system_message,
            output_dir=output_dir,
        )
        for r in results:
            status = "✅" if r["success"] else "❌"
            print(f"  {status} {r['path']}")
            if r.get("error"):
                print(f"    Error: {r['error']}")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": f"Generated {len(results)} files: {len([r for r in results if r['success']])} succeeded, {len([r for r in results if not r['success']])} failed."}
        )

        # Stage 4: Verify and Fix
        print("🔍 Stage 4: Verifying...")
        self.execution_log.append(
            {"step": 0, "role": "system", "content": "Stage 4: Verifying..."}
        )
        final = self.verify_and_fix(
            manifest=manifest,
            files_generated=results,
            task=task,
            system_message=system_message,
            output_dir=output_dir,
        )

        # Stage 5: Run tests (if the plan declared any)
        test_commands = manifest.get("test_commands", []) or []
        test_passed = True
        test_report = None
        if test_commands:
            print(f"🧪 Stage 5: Running {len(test_commands)} test command(s)...")
            self.execution_log.append(
                {
                    "step": 0,
                    "role": "system",
                    "content": f"Stage 5: Running {len(test_commands)} test command(s)...",
                }
            )
            try:
                test_report_obj = run_test_commands(
                    commands=test_commands,
                    working_dir=output_dir,
                )
                test_report = test_report_obj.to_dict()
                test_passed = test_report_obj.all_succeeded
                for r in test_report_obj.results:
                    tag = "✅" if r.success else "❌"
                    print(f"  {tag} {r.command} (exit {r.returncode})")
                    tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
                    if tail:
                        for ln in tail:
                            print(f"    | {ln}")
                if not test_passed:
                    failed = [r for r in test_report_obj.results if not r.success]
                    err = failed[-1] if failed else None
                    err_msg = (err.stderr or err.stdout) if err else "test failed"
                    print(f"❌ Tests failed: {err_msg[:300]}")
                    self.execution_log.append(
                        {
                            "step": 0,
                            "role": "system",
                            "content": (
                                f"❌ Tests failed: "
                                f"{(err.command if err else '?')} (exit {err.returncode if err else '?'})\n"
                                + (err_msg[:1000] if err_msg else "")
                            ),
                        }
                    )
                    self.errors_encountered.append(
                        {"step": 0, "type": "test_failure", "message": err_msg[:500] if err_msg else ""}
                    )
            except Exception as e:
                print(f"⚠️ Test runner crashed: {e}")
                test_passed = False
                self.errors_encountered.append(
                    {"step": 0, "type": "test_runner_error", "message": str(e)}
                )
        else:
            print("🧪 Stage 5: No test_commands declared, skipping.")

        all_success = all(r["success"] for r in final)
        if all_success and test_passed:
            print("✅ All files generated, verified, and tests passed.")
            try:
                add_task_history(
                    self.memory_dir, task, "SUCCESS",
                    f"All {len(final)} files generated and tests passed."
                )
            except Exception as e:
                print(f"⚠️ Failed to write task history: {e}")
            return True
        elif not test_passed:
            print("⚠️ Completed with failing tests. Pausing for review.")
            with contextlib.suppress(Exception):
                add_task_history(
                    self.memory_dir, task, "FAILED",
                    f"Tests failed: {len([r for r in (test_report or {}).get('results', []) if not r.get('success')])} of {len(test_commands)}."
                )
            return False
        else:
            failed = [r for r in final if not r["success"]]
            print(f"⚠️ Completed with {len(failed)} file(s) having issues.")
            with contextlib.suppress(Exception):
                add_task_history(
                    self.memory_dir, task, "SUCCESS",
                    f"Generated {len(final)} files ({len(failed)} with issues)."
                )
            return True
