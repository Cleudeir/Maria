import os
import re
from typing import List, Dict, Tuple, Any
from maria.llm import OllamaClient
from maria.memory import load_system_prompt, load_lessons, add_task_history
from maria.tools import ToolExecutor

def parse_agent_response(response_text: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Parses agent response using regex to extract thoughts and XML-like tool calls.
    """
    # Find thought - match until closing tag, or next tag, or end of response
    thought_match = re.search(r"<thought>(.*?)</thought>", response_text, re.DOTALL | re.IGNORECASE)
    if not thought_match:
        thought_match = re.search(r"<thought>(.*?)(?:<tool|\Z)", response_text, re.DOTALL | re.IGNORECASE)
    thought = thought_match.group(1).strip() if thought_match else ""
    
    # Find tool call name
    tool_match = re.search(r"<tool\s+name=[\"']([^\"']+)[\"']\s*>", response_text, re.IGNORECASE)
    if not tool_match:
        return thought, "", {}
        
    tool_name = tool_match.group(1).strip().lower()
    args = {}
    
    # Extract path if relevant - match until the next '<' character to handle closing tag typos
    if tool_name in ("list_dir", "read_file", "write_file"):
        path_match = re.search(r"<path>([^<]*)", response_text, re.IGNORECASE)
        args["path"] = path_match.group(1).strip() if path_match else ""
        
    # Extract content if write_file - match until closing tag or end of text
    if tool_name == "write_file":
        content_match = re.search(r"<content>(.*?)(?:</content>|\Z)", response_text, re.DOTALL | re.IGNORECASE)
        args["content"] = content_match.group(1) if content_match else ""
        
    # Extract command if run_command - match until next '<' character
    if tool_name == "run_command":
        command_match = re.search(r"<command>([^<]*)", response_text, re.IGNORECASE)
        args["command"] = command_match.group(1).strip() if command_match else ""
        
    # Extract summary if finish_task
    if tool_name == "finish_task":
        summary_match = re.search(r"<summary>(.*?)(?:</summary>|\Z)", response_text, re.DOTALL | re.IGNORECASE)
        args["summary"] = summary_match.group(1).strip() if summary_match else ""
        
    return thought, tool_name, args

class MariaAgent:
    def __init__(self, workspace_dir: str, memory_dir: str, ollama_url: str = "http://localhost:11434"):
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.memory_dir = os.path.abspath(memory_dir)
        self.client = OllamaClient(base_url=ollama_url)
        self.executor = ToolExecutor(self.workspace_dir)
        self.execution_log = []
        self.errors_encountered = []

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
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Your task is:\n{task}"}
        ]
        
        step = 0
        success = False
        completion_summary = ""
        
        while step < max_steps:
            step += 1
            print(f"\n--- STEP {step}/{max_steps} ---")
            
            try:
                # Call LLM
                response_text = self.client.chat(messages, temperature=0.1)
            except Exception as e:
                err_msg = f"LLM error: {e}"
                print(f"❌ {err_msg}")
                self.errors_encountered.append({"step": step, "type": "llm_error", "message": err_msg})
                break
                
            # Log turn
            self.execution_log.append({"step": step, "role": "assistant", "content": response_text})
            
            # Parse response
            thought, tool_name, args = parse_agent_response(response_text)
            
            if thought:
                print(f"💭 Thought:\n{thought}")
            else:
                print("💭 Thought: (none expressed)")
                
            if not tool_name:
                print("⚠️ Formatting error: The model did not output a valid tool call tag structure.")
                err_msg = "Format error: You must output <thought>...</thought> followed by exactly one <tool name='...'>...</tool>."
                self.errors_encountered.append({"step": step, "type": "format_error", "message": err_msg})
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user", "content": f"ERROR:\n{err_msg}"})
                self.execution_log.append({"step": step, "role": "tool_result", "content": f"ERROR: {err_msg}"})
                continue
                
            print(f"🛠️ Tool Call: {tool_name} with args: {args}")
            
            # Execute tool
            tool_result = ""
            if tool_name == "list_dir":
                tool_result = self.executor.list_dir(args.get("path", "."))
            elif tool_name == "read_file":
                tool_result = self.executor.read_file(args.get("path", ""))
            elif tool_name == "write_file":
                tool_result = self.executor.write_file(args.get("path", ""), args.get("content", ""))
            elif tool_name == "run_command":
                tool_result = self.executor.run_command(args.get("command", ""))
            elif tool_name == "finish_task":
                success = True
                completion_summary = args.get("summary", "Task finished.")
                print(f"✅ Finish Task Signal received: {completion_summary}")
                break
            else:
                tool_result = f"Error: Tool '{tool_name}' is not supported. Use only available tools."
                
            # Check for tool errors
            if tool_result.startswith("Error:"):
                print(f"❌ Tool Execution Error:\n{tool_result}")
                self.errors_encountered.append({
                    "step": step,
                    "tool": tool_name,
                    "args": args,
                    "error": tool_result
                })
            else:
                print(f"🔍 Tool Result:\n{tool_result[:300] + '...' if len(tool_result) > 300 else tool_result}")
                
            # Update history
            messages.append({"role": "assistant", "content": response_text})
            messages.append({"role": "user", "content": f"TOOL RESULT:\n{tool_result}"})
            self.execution_log.append({"step": step, "role": "tool_result", "content": tool_result})
            
        # 5. Record final task status in HTML memory
        status_str = "SUCCESS" if success else "FAILED"
        details_str = completion_summary if success else f"Terminated after {step} steps. Errors: {len(self.errors_encountered)}"
        try:
            add_task_history(self.memory_dir, task, status_str, details_str)
        except Exception as e:
            print(f"⚠️ Failed to write task history: {e}")
            
        return success
