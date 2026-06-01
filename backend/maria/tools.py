import os
import re
import select
import socket
import subprocess
import signal
import sys
import threading
import time
from maria.security import is_path_safe, is_command_critical, prompt_user_approval

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pyc", ".pyo", ".pyd",
    ".db", ".sqlite", ".sqlite3",
})


def is_binary_file(file_path: str, sample_size: int = 8192) -> bool:
    _, ext = os.path.splitext(file_path)
    if ext.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(sample_size)
        return b"\0" in chunk
    except Exception:
        return False


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


# Track HTTP servers started by the agent so they can be stopped/killed.
# Structure: { task_id: { server_id: { "port": int, "process": Popen, "path": str, "started_at": float } } }
task_http_servers: dict = {}
_http_server_lock = threading.Lock()
_http_server_counter = 0


def _allocate_server_id(task_id: str) -> str:
    global _http_server_counter
    with _http_server_lock:
        _http_server_counter += 1
        return f"srv_{task_id or 'global'}_{_http_server_counter}"


def _is_port_free(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a TCP port is free on the given host."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def list_http_servers(task_id: str | None = None) -> list:
    """
    Return a list of dictionaries describing active HTTP servers.
    If task_id is provided, only servers started for that task are returned.
    """
    with _http_server_lock:
        result = []
        for tid, servers in task_http_servers.items():
            if task_id and tid != task_id:
                continue
            for sid, info in servers.items():
                proc = info.get("process")
                if proc and proc.poll() is not None:
                    continue
                result.append(
                    {
                        "server_id": sid,
                        "task_id": tid,
                        "port": info.get("port"),
                        "path": info.get("path"),
                        "url": f"http://localhost:{info.get('port')}/",
                        "started_at": info.get("started_at"),
                        "alive": True,
                    }
                )
        return result


def stop_http_server(server_id: str, task_id: str | None = None) -> bool:
    """Stop a single HTTP server by id. Returns True if it was running and stopped."""
    with _http_server_lock:
        if task_id:
            servers = task_http_servers.get(task_id, {})
            info = servers.pop(server_id, None)
        else:
            info = None
            for tid, servers in task_http_servers.items():
                if server_id in servers:
                    info = servers.pop(server_id)
                    task_id = tid
                    break
        if not info:
            return False
        if not servers and task_id:
            task_http_servers.pop(task_id, None)

    proc = info.get("process")
    if not proc:
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    return True


def terminate_task_http_servers(task_id: str) -> int:
    """Stop all HTTP servers belonging to a task. Returns the count of stopped servers."""
    with _http_server_lock:
        servers = task_http_servers.pop(task_id, None)
    if not servers:
        return 0
    count = 0
    for sid, info in list(servers.items()):
        proc = info.get("process")
        if not proc:
            continue
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            count += 1
        except Exception:
            pass
    return count


class ToolExecutor:
    def __init__(self, workspace_dir: str, task_id: str = None, output_callback=None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.task_id = task_id
        self.output_callback = output_callback
        # Ensure workspace directory exists
        os.makedirs(self.workspace_dir, exist_ok=True)
        os.makedirs(os.path.join(self.workspace_dir, "output"), exist_ok=True)

    @staticmethod
    def _normalize_path(path: str) -> str:
        """
        Normalize a path by converting absolute-looking paths (starting with '/')
        to relative paths (starting with './').
        """
        if path.startswith("/") and not path.startswith("//"):
            return "." + path
        return path

    def _resolve_output_path(self, path: str) -> tuple[str, str | None]:
        """
        Resolve a relative path under the workspace output directory.
        Returns (absolute_path, error_message).
        """
        path = self._normalize_path(path)
        if os.path.isabs(path):
            return "", "Error: Access Denied. Absolute paths are not allowed."

        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        if path in ("", ".", "./", "output"):
            target = output_dir
        else:
            normalized_path = path
            if normalized_path.startswith("output" + os.sep):
                normalized_path = normalized_path[len("output" + os.sep) :]
            target = os.path.abspath(os.path.join(output_dir, normalized_path))

        if not is_path_safe(output_dir, target):
            return "", "Error: Access Denied. Path is outside output directory."
        return target, None

    def list_dir(self, path: str = ".") -> str:
        """
        Lists files and subdirectories in the workspace output directory.
        """
        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        if path in (".", "", "output"):
            target_dir = output_dir
        else:
            if path.startswith("output" + os.sep):
                path = path[len("output" + os.sep) :]
            target_dir = os.path.abspath(os.path.join(output_dir, path))

        if not is_path_safe(output_dir, target_dir):
            return "Error: Access Denied. Path is outside output directory."
        if not os.path.exists(target_dir):
            if target_dir == output_dir:
                os.makedirs(output_dir, exist_ok=True)
            else:
                return f"Error: Path '{path}' does not exist."
        if not os.path.isdir(target_dir):
            return f"Error: Path '{path}' is not a directory."

        try:
            result = []
            for root, dirs, files in os.walk(target_dir):
                # Prune unwanted/large directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in ("node_modules", "__pycache__", ".venv", "venv")
                ]
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    rel_path = os.path.relpath(dir_path, target_dir)
                    result.append(f"[DIR] {rel_path}")
                for f in files:
                    if f.startswith(".") or f in ("task_state.json", "task_info.html"):
                        continue
                    file_path = os.path.join(root, f)
                    rel_path = os.path.relpath(file_path, target_dir)
                    result.append(f"[FILE] {rel_path}")
            result.sort()
            return "\n".join(result) if result else "(Empty directory)"
        except Exception as e:
            return f"Error: Failed to list directory: {e}"

    def read_file(self, path: str) -> str:
        """
        Reads contents of a file inside the workspace output directory.
        """
        target_file, error = self._resolve_output_path(path)
        if error:
            return error

        if not os.path.exists(target_file):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(target_file):
            return f"Error: Path '{path}' is a directory, not a file."

        filename = os.path.basename(target_file)
        if filename in ("task_state.json", "task_info.html"):
            return "Error: Access Denied. Internal system file."

        if is_binary_file(target_file):
            return f"Error: Cannot read '{path}': binary files are not supported."

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error: Failed to read file: {e}"

    def write_file(self, path: str, content: str) -> str:
        """
        Writes content to a file in the workspace output directory.
        """
        path = self._normalize_path(path)
        if os.path.isabs(path):
            return "Error: Access Denied. Absolute paths are not allowed."

        if path in ("", ".", "./"):
            return "Error: Invalid path. Please specify a file path under the output directory."

        normalized_path = path
        if (
            not normalized_path.startswith("output" + os.sep)
            and normalized_path != "output"
        ):
            normalized_path = os.path.join("output", normalized_path)

        if not is_path_safe(self.workspace_dir, normalized_path):
            return "Error: Access Denied. Path is outside workspace."

        target_file = os.path.abspath(os.path.join(self.workspace_dir, normalized_path))

        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        if not is_path_safe(output_dir, target_file):
            return "Error: Access Denied. Output files must be saved within the 'output' directory or its subfolders."

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

    def find_in_files(self, query: str, path: str = ".") -> str:
        """
        Finds occurrences of a query (string or regex) inside files under the workspace output directory.
        """
        target_dir, error = self._resolve_output_path(path)
        if error:
            return error
        if not os.path.exists(target_dir):
            return f"Error: Path '{path}' does not exist."

        try:
            pattern = re.compile(query)
        except Exception:
            pattern = None

        results = []
        try:
            for root, dirs, files in os.walk(target_dir):
                # Exclude hidden files/dirs and some standard big folders to keep it fast
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in ("node_modules", "__pycache__", ".venv", "venv")
                ]
                for file in files:
                    if file.startswith(".") or file in (
                        "task_state.json",
                        "task_info.html",
                    ):
                        continue
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.workspace_dir)
                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            for lineno, line in enumerate(f, 1):
                                match = False
                                if pattern:
                                    if pattern.search(line):
                                        match = True
                                elif query in line:
                                    match = True

                                if match:
                                    results.append(
                                        f"{rel_path}:{lineno}: {line.strip()}"
                                    )
                                    if len(results) >= 200:
                                        return (
                                            "\n".join(results)
                                            + "\n(Truncated, too many results)"
                                        )
                    except Exception:
                        continue
            return "\n".join(results) if results else "No matches found."
        except Exception as e:
            return f"Error: Failed to search files: {e}"

    def grep_output(self, query: str) -> str:
        """
        Searches for a query (string or regex) inside files in the 'output' directory of the workspace.
        """
        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        if not os.path.exists(output_dir):
            return "Error: Output directory does not exist yet."

        try:
            pattern = re.compile(query)
        except Exception:
            pattern = None

        results = []
        try:
            for root, dirs, files in os.walk(output_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.workspace_dir)
                    try:
                        with open(
                            file_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            for lineno, line in enumerate(f, 1):
                                match = False
                                if pattern:
                                    if pattern.search(line):
                                        match = True
                                elif query in line:
                                    match = True

                                if match:
                                    results.append(
                                        f"{rel_path}:{lineno}: {line.strip()}"
                                    )
                                    if len(results) >= 200:
                                        return (
                                            "\n".join(results)
                                            + "\n(Truncated, too many results)"
                                        )
                    except Exception:
                        continue
            return (
                "\n".join(results) if results else "No matches found in output folder."
            )
        except Exception as e:
            return f"Error: Failed to grep output directory: {e}"

    def grep(self, path: str, pattern: str) -> str:
        """
        Searches for a regex pattern inside a specific file and returns matching lines with line numbers.
        """
        target_file, error = self._resolve_output_path(path)
        if error:
            return error

        if not os.path.exists(target_file):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(target_file):
            return f"Error: Path '{path}' is a directory, not a file."

        filename = os.path.basename(target_file)
        if filename in ("task_state.json", "task_info.html"):
            return "Error: Access Denied. Internal system file."

        try:
            compiled = re.compile(pattern)
        except Exception:
            return f"Error: Invalid regex pattern '{pattern}'."

        try:
            results = []
            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if compiled.search(line):
                        results.append(f"{lineno}: {line.rstrip()}")
            return "\n".join(results) if results else "No matches found."
        except Exception as e:
            return f"Error: Failed to read file: {e}"

    def edit_lines(self, path: str, start_line: int, end_line: int, replacement: str) -> str:
        """
        Replaces a range of lines (from start_line to end_line inclusive) in a file with the given replacement text.
        Lines are 1-indexed.
        """
        target_file, error = self._resolve_output_path(path)
        if error:
            return error

        if not os.path.exists(target_file):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(target_file):
            return f"Error: Path '{path}' is a directory, not a file."

        filename = os.path.basename(target_file)
        if filename in ("task_state.json", "task_info.html"):
            return "Error: Access Denied. Internal system file."

        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        if not is_path_safe(output_dir, target_file):
            return "Error: Access Denied. Edited files must be within the output directory."

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total = len(lines)
            if start_line < 1 or start_line > total:
                return f"Error: start_line {start_line} is out of range (file has {total} lines)."
            if end_line < start_line or end_line > total:
                return f"Error: end_line {end_line} is out of range (file has {total} lines)."

            new_lines = lines[: start_line - 1] + [replacement + "\n" if not replacement.endswith("\n") else replacement] + lines[end_line:]

            with open(target_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            return f"Success: Lines {start_line}-{end_line} in '{path}' replaced."
        except Exception as e:
            return f"Error: Failed to edit file: {e}"

    def edit_file(self, path: str, target: str, replacement: str) -> str:
        """
        Edits a file inside the workspace output directory by replacing a target block of text with a replacement block.
        """
        target_file, error = self._resolve_output_path(path)
        if error:
            return error

        if not os.path.exists(target_file):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(target_file):
            return f"Error: Path '{path}' is a directory, not a file."

        filename = os.path.basename(target_file)
        if filename in ("task_state.json", "task_info.html"):
            return "Error: Access Denied. Internal system file."

        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        if not is_path_safe(output_dir, target_file):
            return "Error: Access Denied. Edited files must be saved within the 'output' directory or its subfolders."

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                content = f.read()

            if target not in content:
                return f"Error: Target text not found in '{path}'. Please ensure the target text matches exactly."

            new_content = content.replace(target, replacement)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"Success: File '{path}' edited successfully."
        except Exception as e:
            return f"Error: Failed to edit file: {e}"

    COMMAND_TIMEOUT = 600

    def run_command(self, command: str) -> str:
        """
        Runs command inside the workspace output directory, with security controls.
        """
        # Command checks
        if is_command_critical(command):
            # Prompt the user for approval
            approved = prompt_user_approval(command)
            if not approved:
                return "Error: Command execution rejected by user."

        output_dir = os.path.abspath(os.path.join(self.workspace_dir, "output"))
        os.makedirs(output_dir, exist_ok=True)

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

        start_time = time.time()
        deadline = start_time + self.COMMAND_TIMEOUT

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=output_dir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                preexec_fn=preexec_fn,
                creationflags=creationflags,
            )

            if self.task_id:
                pgid = process.pid
                register_task_process_group(self.task_id, pgid)

            output_lines = []
            timed_out = False

            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    timed_out = True
                    break

                rlist, _, _ = select.select([process.stdout], [], [], min(remaining, 0.5))
                if rlist:
                    line = process.stdout.readline()
                    if not line:
                        break
                    output_lines.append(line)
                    if self.output_callback:
                        self.output_callback(line.rstrip("\n"))

            process.stdout.close()
            process.wait(timeout=5)

            if timed_out:
                try:
                    if pgid is not None:
                        if os.name == "nt":
                            process.send_signal(signal.CTRL_BREAK_EVENT)
                        else:
                            os.killpg(pgid, signal.SIGTERM)
                    process.kill()
                except Exception:
                    pass
                elapsed = time.time() - start_time
                return f"Error: Command timed out after {elapsed:.1f}s (limit {self.COMMAND_TIMEOUT}s)."

            elapsed = time.time() - start_time
            output = "".join(output_lines)
            header = (
                f"━━━ Command ━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  $ {command}\n"
                f"  Directory: {output_dir}\n"
                f"  Duration: {elapsed:.1f}s\n"
                f"  Exit code: {process.returncode}\n"
                f"━━━ Output ━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            full = header + output
            if process.returncode != 0:
                return f"Error: Command exited with code {process.returncode}.\n{full.strip()}"
            return f"Success: Command executed successfully.\n{full.strip()}"

        except Exception as e:
            elapsed = time.time() - start_time
            try:
                if pgid is not None:
                    if os.name == "nt":
                        process.send_signal(signal.SIGTERM)
                    else:
                        os.killpg(pgid, signal.SIGTERM)
                if process:
                    process.kill()
            except Exception:
                pass
            return f"Error: Command failed after {elapsed:.1f}s: {e}"
        finally:
            if self.task_id and pgid is not None:
                unregister_task_process_group(self.task_id, pgid)

    DEFAULT_HTTP_PORT = 10010
    MAX_HTTP_PORT = 65535
    MIN_HTTP_PORT = 1

    def start_http_server(self, port: int = None, path: str = ".") -> str:
        """
        Starts a local HTTP server so the user can browse the HTML / static files
        produced by the agent (typically files inside workspace/output/).

        Args:
            port: TCP port to listen on. Defaults to 10010.
            path: Directory (relative to workspace/output) to serve. Defaults to '.'.

        Returns a description of the server with its URL.
        """
        try:
            if port is None:
                port = self.DEFAULT_HTTP_PORT
            port = int(port)
        except (TypeError, ValueError):
            return f"Error: Invalid port '{port}'. Must be an integer between {self.MIN_HTTP_PORT} and {self.MAX_HTTP_PORT}."

        if not (self.MIN_HTTP_PORT <= port <= self.MAX_HTTP_PORT):
            return f"Error: Port {port} is out of range ({self.MIN_HTTP_PORT}-{self.MAX_HTTP_PORT})."

        target_dir, error = self._resolve_output_path(path)
        if error:
            return error
        if not os.path.isdir(target_dir):
            return f"Error: Serve path '{path}' is not a directory."

        server_id = _allocate_server_id(self.task_id or "global")
        host = "0.0.0.0"

        if not _is_port_free(port, host):
            for fallback in range(port, min(port + 20, self.MAX_HTTP_PORT)):
                if _is_port_free(fallback, host):
                    return (
                        f"Error: Port {port} is already in use. "
                        f"Try port {fallback} (it appears to be free) or stop the process bound to {port}."
                    )
            return f"Error: Port {port} is already in use and no nearby port is free."

        log_path = os.path.join(self.workspace_dir, f"http_server_{server_id}.log")
        log_file = open(log_path, "w", encoding="utf-8")

        cmd = [
            sys.executable,
            "-u",
            "-m",
            "http.server",
            str(port),
            "--bind",
            host,
            "--directory",
            target_dir,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=target_dir,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
        except Exception as e:
            log_file.close()
            return f"Error: Failed to start HTTP server: {e}"

        deadline = time.time() + 5.0
        alive = False
        while time.time() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.1)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        alive = True
                        break
            except OSError:
                continue

        if not alive:
            try:
                process.terminate()
            except Exception:
                pass
            log_file.close()
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    tail = f.read()[-400:]
            except Exception:
                tail = ""
            return (
                f"Error: HTTP server failed to start on port {port} within 5 seconds. "
                f"Log tail: {tail or '(empty)'}"
            )

        with _http_server_lock:
            task_bucket = task_http_servers.setdefault(self.task_id or "global", {})
            task_bucket[server_id] = {
                "port": port,
                "process": process,
                "path": path,
                "started_at": time.time(),
            }

        rel_display = os.path.relpath(target_dir, self.workspace_dir)
        return (
            f"Success: HTTP server is running.\n"
            f"  server_id: {server_id}\n"
            f"  port: {port}\n"
            f"  serving: {rel_display}\n"
            f"  url: http://localhost:{port}/\n"
            f"  The user can now open the URL in a browser to test the generated HTML.\n"
            f"  The server will be stopped automatically when this task is deleted."
        )

    def stop_http_server(self, server_id: str) -> str:
        """
        Stops a previously started HTTP server by its id.
        Use list_http_servers to discover active server ids.
        """
        if not server_id:
            return "Error: server_id is required."
        if stop_http_server(server_id, self.task_id):
            return f"Success: HTTP server '{server_id}' stopped."
        return f"Error: No active HTTP server with id '{server_id}' was found."

    def list_http_servers(self) -> str:
        """
        Lists all HTTP servers started by the current task (or by all tasks if global).
        """
        servers = list_http_servers(self.task_id)
        if not servers:
            return "No active HTTP servers."
        lines = []
        for s in servers:
            lines.append(
                f"- server_id={s['server_id']} port={s['port']} path={s['path']} url={s['url']}"
            )
        return "Active HTTP servers:\n" + "\n".join(lines)
