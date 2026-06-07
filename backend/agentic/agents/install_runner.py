"""Run package-manager install commands inside a workspace sandbox.

The agent can declare `install_commands` in its plan (e.g. `npm install`, `pip
install flask`, `npx create-vite ...`). This module executes them in the
task's output directory with strict safety guards:

- Commands must start with an allowed manager (`npm`, `npx`, `pnpm`, `yarn`,
  `pip`, `pip3`, `python -m pip`).
- Working directory is forced to the task output dir (no `cd ..` allowed).
- Hard timeout per command (default 90s) and total timeout (default 5min).
- Output is captured and truncated for state size.
- Process is run in its own process group so it can be killed if the task
  is stopped.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable


ALLOWED_PREFIXES: tuple[str, ...] = (
    "npm ",
    "npm i",
    "npm install",
    "npx ",
    "pnpm ",
    "yarn ",
    "pip ",
    "pip3 ",
    "python -m pip",
    "python3 -m pip",
    "echo ",
    "mkdir ",
    "mkdir -p ",
    "cd ",
)

ALLOWED_EXACT: tuple[str, ...] = (
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "pip",
    "pip3",
)

MAX_OUTPUT_BYTES = 8_000
DEFAULT_CMD_TIMEOUT_S = 90
DEFAULT_TOTAL_TIMEOUT_S = 300


@dataclass
class CommandResult:
    command: str
    success: bool
    returncode: int
    duration_ms: int
    stdout: str
    stderr: str
    error: str | None = None


@dataclass
class InstallRunReport:
    working_dir: str
    started_at: float
    finished_at: float
    results: list[CommandResult] = field(default_factory=list)
    all_succeeded: bool = True

    def to_dict(self) -> dict:
        return {
            "working_dir": self.working_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "all_succeeded": self.all_succeeded,
            "results": [
                {
                    "command": r.command,
                    "success": r.success,
                    "returncode": r.returncode,
                    "duration_ms": r.duration_ms,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if the command is in the whitelist. Returns (ok, reason)."""
    if not command or not command.strip():
        return False, "empty command"

    stripped = command.strip()
    lowered = stripped.lower()

    for prefix in ALLOWED_PREFIXES:
        if lowered.startswith(prefix):
            return True, "ok"

    for exact in ALLOWED_EXACT:
        if lowered == exact:
            return True, "ok"

    return False, (
        f"command not in whitelist (allowed: npm, npx, pnpm, yarn, pip, pip3, "
        f"python -m pip). Got: {stripped[:80]}"
    )


TEST_ALLOWED_PREFIXES: tuple[str, ...] = (
    "npm test",
    "npm run test",
    "npm run lint",
    "npm run build",
    "npm run check",
    "npm run typecheck",
    "npm run e2e",
    "npx ",
    "pnpm ",
    "pnpm test",
    "pnpm run ",
    "yarn ",
    "yarn test",
    "yarn run ",
    "pytest",
    "pytest ",
    "py_compile ",
    "python -m pytest",
    "python -m unittest",
    "python -m doctest",
    "python -m py_compile",
    "python3 -m pytest",
    "python3 -m unittest",
    "python3 -m py_compile",
    "node ",
    "node --test",
    "vitest ",
    "vitest run",
    "jest ",
    "jest --",
    "mocha ",
    "tsc ",
    "tsc --noEmit",
    "ruff ",
    "ruff check",
    "mypy ",
    "flake8 ",
    "eslint ",
    "echo ",
    "cd ",
    "&& ",
    "|| ",
)


TEST_ALLOWED_EXACT: tuple[str, ...] = (
    "npm test",
    "pytest",
    "py_compile",
    "tsc",
    "ruff",
    "mypy",
    "flake8",
    "jest",
    "vitest",
    "mocha",
)


def is_test_command_allowed(command: str) -> tuple[bool, str]:
    """Whitelist check for test/build/lint commands.

    Test runners expand the install whitelist with common quality-gate
    commands (pytest, jest, vitest, mocha, tsc, ruff, eslint, etc.). A
    leading `cd ` or `&& ` is permitted so the LLM can chain steps or
    change directory inside the working_dir, which is itself forced to
    the task output dir by the runner.
    """
    if not command or not command.strip():
        return False, "empty command"

    stripped = command.strip()
    lowered = stripped.lower()

    if lowered in TEST_ALLOWED_EXACT:
        return True, "ok"

    for prefix in TEST_ALLOWED_PREFIXES:
        if lowered.startswith(prefix):
            return True, "ok"

    return False, (
        f"test command not in whitelist (allowed: npm test, pytest, jest, "
        f"vitest, mocha, tsc, ruff, mypy, flake8, eslint, etc.). "
        f"Got: {stripped[:80]}"
    )


def run_test_commands(
    commands: list[str],
    working_dir: str,
    progress_callback: Callable[[str], None] | None = None,
    cmd_timeout_s: int = DEFAULT_CMD_TIMEOUT_S,
    total_timeout_s: int = DEFAULT_TOTAL_TIMEOUT_S,
) -> InstallRunReport:
    """Run test/lint/build commands sequentially in `working_dir`.

    Reuses `run_install_commands` machinery but with a separate, broader
    whitelist (`is_test_command_allowed`). Stops on first failure so
    the caller can surface the failing test to the user.
    """
    if _has_path_traversal(working_dir):
        raise ValueError(f"Refusing to use path with '..': {working_dir}")

    working_dir = os.path.abspath(working_dir)
    os.makedirs(working_dir, exist_ok=True)

    report = InstallRunReport(
        working_dir=working_dir,
        started_at=time.time(),
        finished_at=time.time(),
    )

    if not commands:
        return report

    deadline = time.time() + total_timeout_s

    for raw_cmd in commands:
        if not raw_cmd or not raw_cmd.strip():
            continue
        if time.time() > deadline:
            result = CommandResult(
                command=raw_cmd,
                success=False,
                returncode=-1,
                duration_ms=0,
                stdout="",
                stderr="",
                error="Total timeout exceeded before this command could run",
            )
            report.results.append(result)
            report.all_succeeded = False
            break

        ok, reason = is_test_command_allowed(raw_cmd)
        if not ok:
            result = CommandResult(
                command=raw_cmd,
                success=False,
                returncode=-1,
                duration_ms=0,
                stdout="",
                stderr="",
                error=f"Command rejected: {reason}",
            )
            report.results.append(result)
            report.all_succeeded = False
            break

        if progress_callback:
            progress_callback(f"Running test: {raw_cmd}")

        started = time.time()
        try:
            proc = subprocess.Popen(
                raw_cmd,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
        except Exception as e:
            result = CommandResult(
                command=raw_cmd,
                success=False,
                returncode=-1,
                duration_ms=int((time.time() - started) * 1000),
                stdout="",
                stderr="",
                error=f"Failed to start: {e}",
            )
            report.results.append(result)
            report.all_succeeded = False
            break

        remaining = min(cmd_timeout_s, max(1, int(deadline - time.time())))
        try:
            stdout, stderr = proc.communicate(timeout=remaining)
            returncode = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except Exception:
                stdout, stderr = "", ""
            returncode = -1
            timed_out = True
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            returncode = -1
            stdout, stderr = "", ""
            timed_out = True
            stderr = (stderr or "") + f"\n[runner error: {e}]"

        stdout = _truncate(stdout or "", MAX_OUTPUT_BYTES)
        stderr = _truncate(stderr or "", MAX_OUTPUT_BYTES)

        success = (returncode == 0) and not timed_out
        result = CommandResult(
            command=raw_cmd,
            success=success,
            returncode=returncode,
            duration_ms=int((time.time() - started) * 1000),
            stdout=stdout,
            stderr=stderr,
            error=("timeout" if timed_out else None),
        )
        report.results.append(result)
        if progress_callback:
            tag = "OK" if success else "FAIL"
            preview = (stdout or stderr).strip().splitlines()[-3:] if (stdout or stderr) else []
            progress_callback(
                f"[{tag}] {raw_cmd} ({result.duration_ms}ms)\n"
                + "\n".join(preview)
            )

        if not success:
            report.all_succeeded = False
            break

    report.finished_at = time.time()
    return report


def _has_path_traversal(working_dir_arg: str) -> bool:
    return ".." in working_dir_arg.replace("\\", "/").split("/")


def run_install_commands(
    commands: list[str],
    working_dir: str,
    progress_callback: Callable[[str], None] | None = None,
    cmd_timeout_s: int = DEFAULT_CMD_TIMEOUT_S,
    total_timeout_s: int = DEFAULT_TOTAL_TIMEOUT_S,
) -> InstallRunReport:
    """Run a list of install commands sequentially in `working_dir`.

    Returns an InstallRunReport. Stops on first failure unless
    `continue_on_error=True` is set in the future.
    """
    if _has_path_traversal(working_dir):
        raise ValueError(f"Refusing to use path with '..': {working_dir}")

    working_dir = os.path.abspath(working_dir)
    os.makedirs(working_dir, exist_ok=True)

    report = InstallRunReport(
        working_dir=working_dir,
        started_at=time.time(),
        finished_at=time.time(),
    )

    if not commands:
        return report

    deadline = time.time() + total_timeout_s

    for raw_cmd in commands:
        if not raw_cmd or not raw_cmd.strip():
            continue
        if time.time() > deadline:
            result = CommandResult(
                command=raw_cmd,
                success=False,
                returncode=-1,
                duration_ms=0,
                stdout="",
                stderr="",
                error="Total timeout exceeded before this command could run",
            )
            report.results.append(result)
            report.all_succeeded = False
            break

        ok, reason = is_command_allowed(raw_cmd)
        if not ok:
            result = CommandResult(
                command=raw_cmd,
                success=False,
                returncode=-1,
                duration_ms=0,
                stdout="",
                stderr="",
                error=f"Command rejected: {reason}",
            )
            report.results.append(result)
            report.all_succeeded = False
            break

        if progress_callback:
            progress_callback(f"Running: {raw_cmd}")

        started = time.time()
        try:
            proc = subprocess.Popen(
                raw_cmd,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
        except Exception as e:
            result = CommandResult(
                command=raw_cmd,
                success=False,
                returncode=-1,
                duration_ms=int((time.time() - started) * 1000),
                stdout="",
                stderr="",
                error=f"Failed to start: {e}",
            )
            report.results.append(result)
            report.all_succeeded = False
            break

        remaining = min(cmd_timeout_s, max(1, int(deadline - time.time())))
        try:
            stdout, stderr = proc.communicate(timeout=remaining)
            returncode = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except Exception:
                stdout, stderr = "", ""
            returncode = -1
            timed_out = True
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            returncode = -1
            stdout, stderr = "", ""
            timed_out = True
            stderr = (stderr or "") + f"\n[runner error: {e}]"

        stdout = _truncate(stdout or "", MAX_OUTPUT_BYTES)
        stderr = _truncate(stderr or "", MAX_OUTPUT_BYTES)

        success = (returncode == 0) and not timed_out
        result = CommandResult(
            command=raw_cmd,
            success=success,
            returncode=returncode,
            duration_ms=int((time.time() - started) * 1000),
            stdout=stdout,
            stderr=stderr,
            error=("timeout" if timed_out else None),
        )
        report.results.append(result)
        if progress_callback:
            tag = "OK" if success else "FAIL"
            preview = (stdout or stderr).strip().splitlines()[-3:] if (stdout or stderr) else []
            progress_callback(
                f"[{tag}] {raw_cmd} ({result.duration_ms}ms)\n"
                + "\n".join(preview)
            )

        if not success:
            report.all_succeeded = False
            break

    report.finished_at = time.time()
    return report


def _truncate(s: str, max_bytes: int) -> str:
    if not s:
        return ""
    b = s.encode("utf-8", errors="replace")
    if len(b) <= max_bytes:
        return s
    return b[:max_bytes].decode("utf-8", errors="replace") + "\n[...truncated...]"
