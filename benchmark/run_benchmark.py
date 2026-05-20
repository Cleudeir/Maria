#!/usr/bin/env python3
import os
import sys
import json
import argparse
import time
import traceback

# Ensure the Maria project root is in the path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from maria.agent import MariaAgent
import benchmark.test_cases as test_cases

def load_tasks(tasks_file):
    with open(tasks_file, "r", encoding="utf-8") as f:
        return json.load(f)

def run_task(task, workspace_base, memory_dir, ollama_url, max_steps):
    task_id = task["id"]
    task_name = task["name"]
    difficulty = task["difficulty"]
    prompt = task["prompt"]
    
    task_workspace = os.path.join(workspace_base, f"benchmark_task_{task_id:03d}")
    os.makedirs(task_workspace, exist_ok=True)
    
    print(f"\n==========================================")
    print(f"🎬 Running Task {task_id}: {task_name} ({difficulty.upper()})")
    print(f"📁 Workspace: {task_workspace}")
    print(f"==========================================")
    
    agent = MariaAgent(task_workspace, memory_dir, ollama_url=ollama_url)
    
    start_time = time.time()
    agent_success = False
    error_msg = None
    
    try:
        agent_success = agent.run(prompt, max_steps=max_steps)
    except Exception as e:
        error_msg = f"Agent crashed with exception: {e}\n{traceback.format_exc()}"
        print(f"❌ {error_msg}")
    
    elapsed = time.time() - start_time
    
    # 2. Run Verification
    verification_success = False
    verification_error = None
    
    # Locate corresponding verification function in test_cases.py
    verifier_name = f"verify_task_{task_id}"
    verifier = getattr(test_cases, verifier_name, None)
    
    if not verifier:
        verification_error = f"Verifier function {verifier_name} not found in test_cases.py"
        print(f"⚠️ {verification_error}")
    else:
        print(f"🔍 Running verification function: {verifier_name}...")
        try:
            verifier(task_workspace)
            verification_success = True
            print("✅ Verification PASSED!")
        except AssertionError as e:
            verification_error = f"Assertion failed: {e}"
            print(f"❌ Verification FAILED: {verification_error}")
        except Exception as e:
            verification_error = f"Verification error: {e}\n{traceback.format_exc()}"
            print(f"❌ Verification FAILED with error: {verification_error}")
            
    # Load task_state.json if it exists to get more details (e.g. tool execution errors, steps count)
    state_path = os.path.join(task_workspace, "task_state.json")
    steps_count = 0
    errors_encountered = []
    
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                steps_count = state.get("step", 0)
                errors_encountered = state.get("errors_encountered", [])
        except Exception:
            pass
            
    return {
        "id": task_id,
        "name": task_name,
        "difficulty": difficulty,
        "agent_success": agent_success,
        "verification_success": verification_success,
        "elapsed_seconds": round(elapsed, 2),
        "steps_count": steps_count,
        "agent_errors": errors_encountered,
        "verification_error": verification_error,
        "crash_error": error_msg
    }

def print_summary_table(results):
    print("\n" + "=" * 80)
    print("BENCHMARK EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'ID':<4} | {'Task Name':<30} | {'Difficulty':<10} | {'Agent Status':<12} | {'Verify':<6} | {'Time':<6}")
    print("-" * 80)
    for r in results:
        agent_status = "SUCCESS" if r["agent_success"] else "FAILED"
        verify_status = "PASS" if r["verification_success"] else "FAIL"
        print(f"{r['id']:<4} | {r['name'][:30]:<30} | {r['difficulty'].upper():<10} | {agent_status:<12} | {verify_status:<6} | {r['elapsed_seconds']:<6}s")
    print("=" * 80)

def generate_report(results, report_file):
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    total = len(results)
    agent_passed = sum(1 for r in results if r["agent_success"])
    verify_passed = sum(1 for r in results if r["verification_success"])
    
    # Breakdown by difficulty
    by_diff = {"simple": {"total": 0, "agent": 0, "verify": 0},
               "medium": {"total": 0, "agent": 0, "verify": 0},
               "expert": {"total": 0, "agent": 0, "verify": 0}}
               
    for r in results:
        d = r["difficulty"]
        by_diff[d]["total"] += 1
        if r["agent_success"]:
            by_diff[d]["agent"] += 1
        if r["verification_success"]:
            by_diff[d]["verify"] += 1
            
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# Maria Agent Benchmark Precision Report\n\n")
        f.write(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## Overview Metrics\n\n")
        f.write(f"- **Total Tasks Evaluated**: {total}\n")
        f.write(f"- **Agent Successful Runs**: {agent_passed}/{total} ({round(agent_passed/total*100, 1) if total > 0 else 0}%)\n")
        f.write(f"- **Verification Assertions Passed (Precision)**: {verify_passed}/{total} ({round(verify_passed/total*100, 1) if total > 0 else 0}%)\n\n")
        
        f.write("### Accuracy & Precision by Difficulty Tier\n\n")
        f.write("| Difficulty | Total Tasks | Agent Success Rate | Verification Pass Rate (Precision) |\n")
        f.write("| --- | --- | --- | --- |\n")
        for diff, stats in by_diff.items():
            tot = stats["total"]
            if tot > 0:
                agent_pct = f"{round(stats['agent']/tot*100, 1)}%"
                verify_pct = f"{round(stats['verify']/tot*100, 1)}%"
            else:
                agent_pct = "N/A"
                verify_pct = "N/A"
            f.write(f"| {diff.upper()} | {tot} | {stats['agent']}/{tot} ({agent_pct}) | {stats['verify']}/{tot} ({verify_pct}) |\n")
            
        f.write("\n## Detailed Results\n\n")
        for r in results:
            agent_status = "✅ SUCCESS" if r["agent_success"] else "❌ FAILED"
            verify_status = "✅ PASS" if r["verification_success"] else "❌ FAIL"
            f.write(f"### Task {r['id']}: {r['name']} ({r['difficulty'].upper()})\n\n")
            f.write(f"- **Agent Success**: {agent_status}\n")
            f.write(f"- **Verification Pass**: {verify_status}\n")
            f.write(f"- **Execution Time**: {r['elapsed_seconds']}s\n")
            f.write(f"- **Steps Taken**: {r['steps_count']}\n")
            
            if r["crash_error"]:
                f.write(f"#### Agent Crash Error\n```\n{r['crash_error']}\n```\n")
            elif r["agent_errors"]:
                f.write(f"#### Agent Step Execution Errors\n")
                for err in r["agent_errors"]:
                    f.write(f"- Step {err.get('step')}: {err.get('error') or err.get('message')}\n")
                    
            if r["verification_error"]:
                f.write(f"#### Verification Failure Detail\n```\n{r['verification_error']}\n```\n")
            f.write("\n---\n\n")
            
    print(f"📝 Benchmark Report written to: {report_file}")

def main():
    parser = argparse.ArgumentParser(description="Maria Benchmark Suite runner")
    parser.add_argument("--tasks-file", type=str, default=os.path.join(BASE_DIR, "benchmark", "tasks.json"), help="Path to tasks.json")
    parser.add_argument("--workspace", type=str, default=os.path.join(BASE_DIR, "workspace"), help="Path to workspace directory")
    parser.add_argument("--memory", type=str, default=os.path.join(BASE_DIR, "memory"), help="Path to memory directory")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--difficulty", type=str, choices=["simple", "medium", "expert", "all"], default="all", help="Filter tasks by difficulty")
    parser.add_argument("--task", type=int, help="Run a specific task by ID")
    parser.add_argument("--max-steps", type=int, default=20, help="Max steps per task")
    parser.add_argument("--report", type=str, default=os.path.join(BASE_DIR, "benchmark", "results", "report.md"), help="Path to output report.md")
    parser.add_argument("--verify-only", action="store_true", help="Run verifiers on already generated files without running the agent")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.tasks_file):
        print(f"Error: Tasks file {args.tasks_file} not found.", file=sys.stderr)
        sys.exit(1)
        
    tasks = load_tasks(args.tasks_file)
    
    # Filter tasks
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            print(f"Error: Task with ID {args.task} not found in database.", file=sys.stderr)
            sys.exit(1)
    elif args.difficulty and args.difficulty != "all":
        tasks = [t for t in tasks if t["difficulty"] == args.difficulty]
        
    print(f"Loaded {len(tasks)} tasks for execution.")
    
    results = []
    
    for task in tasks:
        if args.verify_only:
            # Only run verifiers on existing directories
            task_workspace = os.path.join(args.workspace, f"benchmark_task_{task['id']:03d}")
            verifier_name = f"verify_task_{task['id']}"
            verifier = getattr(test_cases, verifier_name, None)
            
            verification_success = False
            verification_error = None
            
            if not os.path.exists(task_workspace):
                verification_error = f"Workspace directory {task_workspace} does not exist"
            elif not verifier:
                verification_error = f"Verifier {verifier_name} not found"
            else:
                try:
                    verifier(task_workspace)
                    verification_success = True
                except AssertionError as e:
                    verification_error = str(e)
                except Exception as e:
                    verification_error = f"Error: {e}"
            
            results.append({
                "id": task["id"],
                "name": task["name"],
                "difficulty": task["difficulty"],
                "agent_success": os.path.exists(os.path.join(task_workspace, "verification_report.md")),
                "verification_success": verification_success,
                "elapsed_seconds": 0,
                "steps_count": 0,
                "agent_errors": [],
                "verification_error": verification_error,
                "crash_error": None
            })
        else:
            # Run task end-to-end
            res = run_task(task, args.workspace, args.memory, args.ollama_url, args.max_steps)
            results.append(res)
            
    print_summary_table(results)
    generate_report(results, args.report)

if __name__ == "__main__":
    main()
