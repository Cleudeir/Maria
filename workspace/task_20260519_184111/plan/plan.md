**Role:** You are a Senior Frontend Developer and Test Engineer specializing in Test-Driven Development (TDD) and responsive web applications.

**Objective:** Create a fully functional, beautifully designed, and responsive Snake game using HTML, CSS, and Vanilla JavaScript. You must follow a strict TDD workflow using a Python test script to validate the implementation.

**Technical Stack:**
- **Testing:** Python 3 (Standard Library only: `os`, `sys`, `re`).
- **Frontend:** HTML5, CSS3, Vanilla JavaScript (ES6+).
- **Environment:** Local workspace.

**Design & Functional Requirements:**
1.  **Visuals:** Use a modern dark theme (background `#1a1a1a`, snake green `#4caf50`, food red `#f44336`). Ensure the UI is clean and centered.
2.  **Responsiveness:** The game canvas must resize dynamically to fit the window width/height while maintaining aspect ratio.
3.  **Game Logic:**
    - Grid-based movement (20x20 cells).
    - Smooth animation using `requestAnimationFrame` (target ~60 FPS).
    - Input buffering to prevent multiple moves per frame.
    - Collision detection: Game over if snake hits walls or its own body.
    - Score tracking: Display current score on the UI; reset score on game over.
    - Food generation: Random position not overlapping with the snake.

**TDD Workflow & Testing Strategy:**
You must execute the following steps sequentially. Do not skip steps.

1.  **Create Test Script (`test_game.py`):**
    - Write a Python script that performs the following checks:
        - Verify the existence of `index.html`, `style.css`, and `script.js` in the current directory.
        - Read `index.html` and verify it contains a `<canvas>` element with the specific ID `game-board`.
        - Read `script.js` and verify it contains code referencing the `game-board` element (e.g., `document.getElementById('game-board')`).
    - The script should print detailed error messages if any check fails and exit with a non-zero status code.

2.  **Initial Verification (Fail State):**
    - Run `python test_game.py`.
    - Confirm the script fails because the game files do not exist yet.
    - Log the failure details to ensure the test is working correctly.

3.  **Implementation:**
    - Create `index.html` with the required canvas structure and basic meta tags.
    - Create `style.css` with the dark theme and responsive layout rules.
    - Create `script.js` with the complete Snake game logic (game loop, input handling, collision detection, rendering).
    - Ensure `script.js` is loaded within the HTML structure.

4.  **Final Verification (Pass State):**
    - Run `python test_game.py` again.
    - Confirm the script passes all checks (files exist, canvas ID present, script loaded).
    - Ensure the game is playable and meets all functional requirements.

5.  **Completion:**
    - Once the test passes and the game is functional, output the command `finish_task`.

**Constraints & Edge Cases:**
- **Input:** Handle Arrow Keys (Up, Down, Left, Right). Prevent 180-degree turns (e.g., cannot go Left if currently moving Right).
- **Performance:** Ensure the game loop does not cause lag on lower refresh rate monitors.
- **Security:** No external dependencies; all code must be self-contained in the provided files.
- **Error Handling:** If the user presses a key while the game is paused, the game should not resume until the next frame.

**Output Format:**
- Provide the content for `test_game.py`, `index.html`, `style.css`, and `script.js`.
- Include the execution logs for the test script (simulated or actual output).
- End with the exact string `finish_task`.