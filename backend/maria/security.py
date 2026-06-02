import os


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
