import os
import re
import shlex


def is_path_safe(base_dir: str, target_path: str) -> bool:
    """
    Checks if target_path is inside base_dir (preventing path traversal attacks).
    """
    # Convert base_dir to absolute path
    abs_base = os.path.abspath(base_dir)

    # If target_path is absolute, check it directly, otherwise join it
    if os.path.isabs(target_path):
        abs_target = os.path.abspath(target_path)
    else:
        abs_target = os.path.abspath(os.path.join(abs_base, target_path))

    # Check if the target is within the base directory
    try:
        return os.path.commonpath([abs_base, abs_target]) == abs_base
    except ValueError:
        return False


def is_command_critical(cmd: str) -> bool:
    """
    Identifies if the command invocation is a critical shell command requiring approval.
    Only the first executable token is checked, with support for common wrappers like sudo/env.
    """
    try:
        parts = shlex.split(cmd, posix=True)
    except ValueError:
        # Fallback to a simple split if the command can't be parsed cleanly.
        parts = re.split(r"\s+", cmd.strip())

    if not parts:
        return False

    wrappers = {"sudo", "env", "nice", "nohup", "command"}
    critical = {
        "git",
        "rm",
        "mv",
        "cp",
        "chmod",
        "chown",
        "chgrp",
        "dd",
        "ln",
        "curl",
        "wget",
        "scp",
        "ssh",
        "docker",
        "kubectl",
        "systemctl",
        "service",
        "npm",
        "yarn",
        "pip",
        "pip3",
        "tar",
        "make",
        "rsync",
    }

    for part in parts:
        if not part:
            continue
        base = os.path.basename(part)
        if base in wrappers:
            continue
        return base in critical

    return False


def prompt_user_approval(cmd: str) -> bool:
    """
    Prompts the user on the console to approve a critical command.
    """
    if os.environ.get("MARIA_SERVER") == "1" or os.environ.get("MARIA_BENCHMARK") == "1":
        print(f"ℹ️ Auto-authorizing critical command: {cmd}")
        return True

    print("\n" + "=" * 60)
    print("⚠️  SECURITY WARNING: The agent requested to run a critical command:")
    print(f"   Command: {cmd}")
    print("=" * 60)

    while True:
        try:
            choice = (
                input("Do you authorize this command? (yes/no or y/n): ")
                .strip()
                .lower()
            )
            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            else:
                print("Please enter 'yes' or 'no'.")
        except (KeyboardInterrupt, EOFError):
            print("\nRejected by default (Interrupted).")
            return False
