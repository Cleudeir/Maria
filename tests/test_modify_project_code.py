import os
import tempfile
import pytest

from maria.tools import ToolExecutor


@pytest.fixture
def temp_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return str(workspace)


def test_modify_project_code_write_mode(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    result = executor.modify_project_code(
        path="maria/test_example.py",
        content="# Test file content\ndef hello():\n    pass\n",
        mode="write",
    )

    assert "Success" in result
    assert "written successfully" in result


def test_modify_project_code_append_mode(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    first_write = executor.modify_project_code(
        path="maria/test_append.py",
        content="# Initial content\n",
        mode="write",
    )
    assert "Success" in first_write

    result = executor.modify_project_code(
        path="maria/test_append.py",
        content="# Appended content\n",
        mode="append",
    )

    assert "Success" in result
    assert "appended" in result


def test_modify_project_code_edit_mode(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    executor.modify_project_code(
        path="maria/test_edit.py",
        content="def old_function():\n    pass\n",
        mode="write",
    )

    result = executor.modify_project_code(
        path="maria/test_edit.py",
        content="TARGET:def old_function():\n    pass\nREPLACEMENT:def new_function():\n    return True\n",
        mode="edit",
    )

    assert "Success" in result
    assert "edited successfully" in result


def test_modify_project_code_rejects_absolute_path(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    result = executor.modify_project_code(
        path="/etc/passwd",
        content="malicious content",
        mode="write",
    )

    assert "Error" in result
    assert "Absolute paths" in result


def test_modify_project_code_rejects_path_traversal(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    result = executor.modify_project_code(
        path="../../../etc/passwd",
        content="malicious content",
        mode="write",
    )

    assert "Error" in result


def test_modify_project_code_rejects_hidden_files(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    result = executor.modify_project_code(
        path=".env",
        content="SECRET=value",
        mode="write",
    )

    assert "Error" in result
    assert "hidden files" in result


def test_modify_project_code_rejects_disallowed_extension(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    result = executor.modify_project_code(
        path="malware.exe",
        content="binary content",
        mode="write",
    )

    assert "Error" in result
    assert "not allowed" in result


def test_modify_project_code_edit_requires_markers(temp_workspace):
    executor = ToolExecutor(temp_workspace)

    executor.modify_project_code(
        path="maria/test_markers.py",
        content="def foo():\n    pass\n",
        mode="write",
    )

    result = executor.modify_project_code(
        path="maria/test_markers.py",
        content="no markers here",
        mode="edit",
    )

    assert "Error" in result
    assert "TARGET:" in result
