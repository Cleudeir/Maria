import argparse
import os
import sys
from maria.agents import MariaAgent, SelfImprovementAgent

def main():
    parser = argparse.ArgumentParser(description="Maria: Self-Improving Agentic SLM System (Qwen3.5:4b)")
    parser.add_argument("task", type=str, help="The task for Maria to perform.")
    parser.add_argument("--workspace", type=str, default="workspace", help="Path to workspace directory.")
    parser.add_argument("--memory", type=str, default="memory", help="Path to memory directory.")
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum execution steps.")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama API base URL.")
    parser.add_argument("--isolate", action="store_true", default=True, help="Isolate task in its own workspace subfolder.")
    parser.add_argument("--no-isolate", dest="isolate", action="store_false", help="Do not isolate task in its own subfolder.")
    parser.add_argument("--compaction-threshold", type=int, default=10, help="Number of lessons before triggering memory compaction.")
    
    args = parser.parse_args()
    
    # Resolve absolute paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.abspath(os.path.join(base_dir, args.workspace))
    memory_dir = os.path.abspath(os.path.join(base_dir, args.memory))
    
    # Isolate task in separate folder if requested
    if args.isolate:
        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        task_folder_name = f"task_{timestamp}"
        workspace_dir = os.path.join(workspace_dir, task_folder_name)
        os.makedirs(workspace_dir, exist_ok=True)
        print(f"📁 Isolated Task Workspace created: {workspace_dir}")
        
        # Write task info file when start (in HTML format)
        info_path = os.path.join(workspace_dir, "task_info.html")
        created_time = time.strftime('%Y-%m-%d %H:%M:%S')
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Maria - Task Information</title>
    <style>
        body {{
            font-family: 'Outfit', 'Inter', sans-serif;
            background-color: #0f172a;
            color: #e2e8f0;
            padding: 40px;
            max-width: 800px;
            margin: auto;
        }}
        .container {{
            background-color: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 30px;
            border-left: 4px solid #38bdf8;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        h1 {{
            color: #38bdf8;
            margin-top: 0;
            border-bottom: 2px solid #334155;
            padding-bottom: 10px;
        }}
        .meta {{
            color: #94a3b8;
            font-size: 0.9em;
            margin-bottom: 20px;
            line-height: 1.6;
        }}
        .task-description {{
            background-color: #0f172a;
            padding: 20px;
            border-radius: 6px;
            border: 1px solid #334155;
            white-space: pre-wrap;
            font-family: monospace;
            font-size: 1.05em;
            line-height: 1.5;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Maria Task Info</h1>
        <div class="meta">
            <strong>Created:</strong> {created_time}<br>
            <strong>Workspace:</strong> {workspace_dir}
        </div>
        <h3>Task Description:</h3>
        <div class="task-description">{args.task}</div>
    </div>
</body>
</html>
"""
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
    # Initialize agents
    agent = MariaAgent(workspace_dir, memory_dir, ollama_url=args.ollama_url)
    meta_agent = SelfImprovementAgent(memory_dir, ollama_url=args.ollama_url)
    
    # Run agent task
    try:
        success = agent.run(args.task, max_steps=args.max_steps)
        print("\n" + "=" * 60)
        if success:
            print("🎉 TASK COMPLETED SUCCESSFULLY!")
        else:
            print("❌ TASK FAILED OR REACHED MAX STEPS.")
        print("=" * 60)
        
        # Self improvement loop
        meta_agent.improve(args.task, agent.execution_log, agent.errors_encountered, compaction_threshold=args.compaction_threshold)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n👋 Execution interrupted by user.")
        # Attempt self-improvement anyway with what we have
        if agent.execution_log:
            meta_agent.improve(args.task, agent.execution_log, agent.errors_encountered, compaction_threshold=args.compaction_threshold)
        sys.exit(130)

if __name__ == "__main__":
    main()
