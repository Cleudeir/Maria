import os
import subprocess
import signal
import time
from maria.security import is_path_safe, is_command_critical, prompt_user_approval

# Track process groups for tasks so they can be terminated when a task is deleted.
task_process_groups = {}


def register_task_process_group(task_id: str, pgid: int):
    if not task_id:
        return
    groups = task_process_groups.setdefault(task_id, set())
    groups.add(pgid)


def unregister_task_process_group(task_id: str, pgid: int):
    if not task_id:
        return
    groups = task_process_groups.get(task_id)
    if not groups:
        return
    groups.discard(pgid)
    if not groups:
        task_process_groups.pop(task_id, None)


def terminate_task_process_groups(task_id: str):
    groups = task_process_groups.pop(task_id, None)
    if not groups:
        return

    for pgid in list(groups):
        try:
            if os.name == "nt":
                os.kill(pgid, signal.SIGTERM)
            else:
                os.killpg(pgid, signal.SIGTERM)
        except Exception:
            pass

    # Give processes a short grace period to exit before forcing them.
    time.sleep(0.25)
    for pgid in list(groups):
        try:
            if os.name == "nt":
                os.kill(pgid, signal.SIGKILL)
            else:
                os.killpg(pgid, signal.SIGKILL)
        except Exception:
            pass


class ToolExecutor:
    def __init__(self, workspace_dir: str, task_id: str = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.task_id = task_id
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
                # Hide internal task metadata files
                if item in ("task_state.json", "task_info.html"):
                    continue
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
            
        filename = os.path.basename(target_file)
        if filename in ("task_state.json", "task_info.html"):
            return "Error: Access Denied. Internal system file."

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
        
        filename = os.path.basename(target_file)
        if filename in ("task_state.json", "task_info.html"):
            return "Error: Access Denied. Internal system file."

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

        preexec_fn = None
        creationflags = 0
        if os.name != "nt":
            preexec_fn = os.setsid
        else:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        process = None
        pgid = None
        if self.task_id and os.name != "nt":
            # On POSIX, the process PID becomes the process group ID after setsid.
            pgid = None

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.workspace_dir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=preexec_fn,
                creationflags=creationflags,
            )

            if self.task_id:
                pgid = process.pid
                register_task_process_group(self.task_id, pgid)

            stdout, stderr = process.communicate(timeout=300)
            output = ""
            if stdout:
                output += stdout
            if stderr:
                output += f"\nStderr:\n{stderr}"

            if process.returncode != 0:
                return f"Error: Command exited with code {process.returncode}.\nOutput:\n{output.strip()}"

            return f"Success: Command executed successfully.\nOutput:\n{output.strip()}"

        except subprocess.TimeoutExpired:
            if process is not None:
                try:
                    if pgid is not None:
                        if os.name == "nt":
                            process.send_signal(signal.CTRL_BREAK_EVENT)
                        else:
                            os.killpg(pgid, signal.SIGTERM)
                    process.kill()
                except Exception:
                    pass
            return "Error: Command timed out after 300 seconds."
        except Exception as e:
            return f"Error: Failed to run command: {e}"
        finally:
            if self.task_id and pgid is not None:
                unregister_task_process_group(self.task_id, pgid)
