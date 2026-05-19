import os
import subprocess
from maria.security import is_path_safe, is_command_critical, prompt_user_approval

class ToolExecutor:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        # Ensure workspace directory exists
        os.makedirs(self.workspace_dir, exist_ok=True)

    def list_dir(self, path: str = ".") -> str:
        """
        Lists files in path relative to workspace.
        """
        if not is_path_safe(self.workspace_dir, path):
            return "Error: Access Denied. Path is outside workspace."
        
        target_dir = os.path.abspath(os.path.join(self.workspace_dir, path))
        if not os.path.exists(target_dir):
            return f"Error: Path '{path}' does not exist."
        if not os.path.isdir(target_dir):
            return f"Error: Path '{path}' is not a directory."
            
        try:
            items = os.listdir(target_dir)
            result = []
            for item in sorted(items):
                item_path = os.path.join(target_dir, item)
                is_dir = os.path.isdir(item_path)
                result.append(f"{'[DIR]' if is_dir else '[FILE]'} {item}")
            return "\n".join(result) if result else "(Empty directory)"
        except Exception as e:
            return f"Error: Failed to list directory: {e}"

    def read_file(self, path: str) -> str:
        """
        Reads contents of file relative to workspace.
        """
        if not is_path_safe(self.workspace_dir, path):
            return "Error: Access Denied. Path is outside workspace."
            
        target_file = os.path.abspath(os.path.join(self.workspace_dir, path))
        if not os.path.exists(target_file):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(target_file):
            return f"Error: Path '{path}' is a directory, not a file."
            
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: Failed to read file: {e}"

    def write_file(self, path: str, content: str) -> str:
        """
        Writes content to file relative to workspace.
        """
        if not is_path_safe(self.workspace_dir, path):
            return "Error: Access Denied. Path is outside workspace."
            
        target_file = os.path.abspath(os.path.join(self.workspace_dir, path))
        
        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Success: File '{path}' written successfully."
        except Exception as e:
            return f"Error: Failed to write file: {e}"

    def run_command(self, command: str) -> str:
        """
        Runs command inside workspace directory, with security controls.
        """
        # Command checks
        if is_command_critical(command):
            # Prompt the user for approval
            approved = prompt_user_approval(command)
            if not approved:
                return "Error: Command execution rejected by user."
                
        try:
            # Run the command with cwd set to workspace
            # We run in shell=True to support piping, redirects, etc.
            # Timeout of 60s to prevent hanging
            process = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_dir,
                text=True,
                capture_output=True,
                timeout=60
            )
            
            output = ""
            if process.stdout:
                output += process.stdout
            if process.stderr:
                output += f"\nStderr:\n{process.stderr}"
                
            if process.returncode != 0:
                return f"Error: Command exited with code {process.returncode}.\nOutput:\n{output.strip()}"
            
            return f"Success: Command executed successfully.\nOutput:\n{output.strip()}"
            
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds."
        except Exception as e:
            return f"Error: Failed to run command: {e}"
