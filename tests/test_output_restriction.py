import json
import os
import pytest
import server
from maria.tools import ToolExecutor


def test_tool_executor_write_file_restriction(tmp_path):
    # Setup dummy workspace
    workspace = tmp_path / "task_123"
    workspace.mkdir()

    executor = ToolExecutor(str(workspace))

    # Writing to a root-relative path is now saved under output/
    res = executor.write_file("test.txt", "hello")
    assert "Success" in res
    assert (workspace / "output" / "test.txt").exists()
    assert (workspace / "output" / "test.txt").read_text() == "hello"

    # Writing to output/ should still be allowed
    res2 = executor.write_file("output/test.txt", "hello output")
    assert "Success" in res2
    assert (workspace / "output" / "test.txt").exists()
    assert (workspace / "output" / "test.txt").read_text() == "hello output"

    # Writing to subfolder in output/ should be allowed
    res3 = executor.write_file("output/sub/test.txt", "hello sub")
    assert "Success" in res3
    assert (workspace / "output" / "sub" / "test.txt").exists()
    assert (workspace / "output" / "sub" / "test.txt").read_text() == "hello sub"

    # Writing with parent traversal out of output/ should be blocked
    res4 = executor.write_file("output/../test.txt", "hello bypass")
    assert "Error: Access Denied" in res4
    assert not (workspace / "test.txt").exists()


def test_tool_executor_run_command_uses_output_root(tmp_path):
    workspace = tmp_path / "task_999"
    workspace.mkdir()

    executor = ToolExecutor(str(workspace))
    (workspace / "outside.txt").write_text("outside")

    res = executor.run_command("pwd")
    assert "Success" in res
    assert "/output" in res or "output" in res
    assert (workspace / "output").is_dir()


def test_server_edit_route_restriction(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    task_id = "task_test"
    task_path = tmp_path / task_id
    task_path.mkdir()

    client = server.app.test_client()

    # Editing file outside output/ should be blocked
    response = client.post(
        f"/api/tasks/{task_id}/files/edit",
        json={"path": "test.txt", "content": "hello"},
    )
    assert response.status_code == 403
    assert not (task_path / "test.txt").exists()

    # Editing file inside output/ should be allowed
    response = client.post(
        f"/api/tasks/{task_id}/files/edit",
        json={"path": "output/test.txt", "content": "hello output"},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert (task_path / "output" / "test.txt").exists()
    assert (task_path / "output" / "test.txt").read_text() == "hello output"


def test_new_tools_restrictions(tmp_path):
    # Setup dummy workspace
    workspace = tmp_path / "task_456"
    workspace.mkdir()

    # Create some files inside output and outside output
    output_dir = workspace / "output"
    output_dir.mkdir()

    (output_dir / "test.txt").write_text("hello python world\nline 2 here")
    (workspace / "outside.txt").write_text("hello python outside\nline 2 here")

    executor = ToolExecutor(str(workspace))

    # Test find_in_files inside output/
    res_find = executor.find_in_files("python", "output")
    assert "output/test.txt:1: hello python world" in res_find

    # Test find_in_files outside workspace path (should be blocked)
    res_find_bad = executor.find_in_files("python", "../")
    assert "Error: Access Denied" in res_find_bad

    # Test grep_output (should find files in output/)
    res_grep = executor.grep_output("world")
    assert "output/test.txt:1: hello python world" in res_grep

    # Test edit_file inside output/ (should be allowed)
    res_edit = executor.edit_file(
        "output/test.txt", "hello python world", "hello beautiful python world"
    )
    assert "Success" in res_edit
    assert (
        output_dir / "test.txt"
    ).read_text() == "hello beautiful python world\nline 2 here"

    # Test edit_file outside output/ (should be blocked)
    res_edit_bad = executor.edit_file(
        "outside.txt", "hello python outside", "should not change"
    )
    assert "Error: Access Denied" in res_edit_bad
    assert (
        workspace / "outside.txt"
    ).read_text() == "hello python outside\nline 2 here"


def test_list_dir_shows_output_directory_only(tmp_path):
    workspace = tmp_path / "task_789"
    workspace.mkdir()
    output_dir = workspace / "output"
    output_dir.mkdir()
    (output_dir / "test.txt").write_text("hello output")
    (output_dir / "sub").mkdir()
    (output_dir / "sub" / "nested.txt").write_text("nested")
    (workspace / "outside.txt").write_text("should not be listed")

    executor = ToolExecutor(str(workspace))

    res = executor.list_dir(".")
    assert "[FILE] test.txt" in res
    assert "[DIR] sub" in res
    assert "outside.txt" not in res

    res_sub = executor.list_dir("output/sub")
    assert "[FILE] nested.txt" in res_sub
    assert "outside.txt" not in res_sub

    res_bad = executor.list_dir("../")
    assert "Error: Access Denied" in res_bad
