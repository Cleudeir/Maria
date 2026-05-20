# How to Prevent XML Format Errors in Maria

This document explains why the Maria Agent throws format errors and how to construct agent responses to avoid them.

---

## The Error

When executing steps, the Maria framework parses the assistant's responses and expects a specific XML format. If the parser cannot find or extract a valid tool call, it returns the following error:

```text
ERROR: Format error: You must output <think>...</think> followed by exactly one <tool name='...'>...</tool>.
```

---

## Why It Occurs

The agent loop parses the response using regular expressions in `maria/agents/utils.py`. The parser expects:
1. **A thought block**: An explanation of the rationale behind the action. The parser extracts **all text before the `<tool>` tag** as the thought.
2. **Exactly one XML-style tool call block**: Beginning with `<tool name="...">` and containing all required inner tags (like `<path>`, `<content>`, `<query>`, etc.), closed properly with `</tool>`.

If the parser encounters any of the following, a format error is triggered:
* No `<tool name="...">` block is present in the response.
* The `<tool>` tag is malformed (e.g., missing name attribute, wrong quotes, or missing closing bracket).
* The model output contains raw text/commentary after the `</tool>` block.
* Multiple tool calls are written in a single turn.

---

## How to Prevent the Error (Correct Response Protocol)

To ensure successful parsing, every model turn must follow this exact format structure. Note that the thought process is native, so **do not** manually output `<think>` or `</think>` tags. The system automatically treats all text before the `<tool>` tag as the thought.

```xml
[Provide reasoning here explaining what you are doing, why you are doing it, and what tool you will use next]

<tool name="[tool_name]">
  <[parameter_name_1]>[parameter_value_1]</[parameter_name_1]>
  <[parameter_name_2]>[parameter_value_2]</[parameter_name_2]>
</tool>
```

### Key Formatting Rules:

1. **Write thoughts naturally** at the very beginning of the response. **Do not wrap thoughts in `<think>...</think>` tags** manually, as the reasoning process is native.
2. **Specify exactly one `<tool>` tag** with the correct `name` attribute using single or double quotes (e.g., `<tool name="read_file">`).
3. **Use parameters inside the tool tag** that match the tool's expected schema (e.g., `<path>`, `<content>`, `<query>`, `<command>`, `<summary>`, `<target>`, `<replacement>`).
4. **Ensure all XML tags are properly closed** (e.g., every `<tool>` has a matching `</tool>`).
5. **Do not output any text after the `</tool>` tag.**

---

## Tool Templates

Below are the correct templates for all available tools in the Maria framework:

### 1. list_dir
Used to list the contents of a directory.
```xml
Let's see what files are in the workspace.

<tool name="list_dir">
  <path>.</path>
</tool>
```

### 2. read_file
Used to view the contents of a file.
```xml
Let's read server.py to understand the endpoint logic.

<tool name="read_file">
  <path>server.py</path>
</tool>
```

### 3. write_file
Used to create a new file or completely overwrite an existing one.
```xml
I will create a helper script to test the DB connection.

<tool name="write_file">
  <path>utils/test_db.py</path>
  <content>
import pymysql
print("DB test script")
  </content>
</tool>
```

### 4. edit_file
Used to replace a specific contiguous block of text in an existing file.
```xml
Replacing old_function with new_function in app.py.

<tool name="edit_file">
  <path>app.py</path>
  <target>
def old_function():
    return "old"
  </target>
  <replacement>
def new_function():
    return "new"
  </replacement>
</tool>
```

### 5. find_in_files
Used to search for a query or regex across files.
```xml
Search for usage of get_last_usage in the codebase.

<tool name="find_in_files">
  <path>.</path>
  <query>get_last_usage</query>
</tool>
```

### 6. grep_output
Used to search in output directory logs/results.
```xml
Let's search the output logs for the word "Exception".

<tool name="grep_output">
  <query>Exception</query>
</tool>
```

### 7. run_command
Used to execute commands in the shell.
```xml
Let's run the unit tests to see if our implementation works.

<tool name="run_command">
  <command>pytest tests/test_pipeline.py</command>
</tool>
```

### 8. finish_task
Used when you believe the current step or task is fully complete.
```xml
The TDD cycle is completed successfully and the test passes.

<tool name="finish_task">
  <summary>Implemented the new database utility and verified it with tests.</summary>
</tool>
```
