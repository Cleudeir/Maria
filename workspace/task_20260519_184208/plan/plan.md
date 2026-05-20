Act as a Senior Full-Stack Developer. Your objective is to build a fully functional, responsive Snake game using HTML5, CSS3, and Vanilla JavaScript within the workspace. You must adhere to a strict Test-Driven Development (TDD) methodology.

**1. Project Structure & Files**
Create the following files in the workspace root directory:
- `test_game.py` (Python test script)
- `index.html` (Main entry point)
- `style.css` (Styling)
- `script.js` (Game Logic)

**2. Design & Technical Specifications**
- **HTML:** Must include a `<canvas>` element with the exact ID `game-board`.
- **CSS:** Implement a modern, dark-themed UI. Ensure the canvas is responsive (100% width/height) and centered on the viewport.
- **JavaScript:**
    - Use `requestAnimationFrame` for the game loop to ensure smooth animations (target 60 FPS).
    - Implement grid-based movement logic (e.g., 20x20 grid).
    - Handle keyboard input (Arrow keys or WASD).
    - Ensure input buffering to prevent multiple turns per frame.
    - Implement collision detection for walls and self-collision.
    - Implement food generation (random empty grid cells).
    - Display score tracking on the UI.
    - Implement a "Game Over" state with a restart mechanism.

**3. TDD Workflow Execution**
You must execute the following steps in order:

- **Step 1: Write Tests.**
  Create `test_game.py` using Python's `unittest` framework. The script must perform the following assertions:
  1. Verify the existence of `index.html`, `style.css`, and `script.js`.
  2. Parse `index.html` to ensure the `<canvas id="game-board">` tag exists.
  3. Verify `script.js` is referenced in the `<head>` or `<body>` of `index.html`.

- **Step 2: Initial Verification.**
  Run `python test_game.py`. Confirm the test suite fails (as expected in TDD).

- **Step 3: Implementation.**
  Implement the game logic in `script.js` and styling in `style.css` to satisfy the requirements. Ensure the game runs correctly when opened in a browser.

- **Step 4: Final Verification.**
  Run `python test_game.py` again. Confirm the test suite passes.

- **Step 5: Completion.**
  Call `finish_task` to conclude the task.

**4. Edge Cases & Constraints**
- **Input Handling:** Prevent the snake from reversing direction into itself (e.g., moving Up while currently moving Down).
- **Game Loop:** Ensure the game loop handles the "Game Over" state correctly (stops updating, shows message).
- **Responsiveness:** Ensure the canvas resizes correctly if the browser window is resized.
- **Error Handling:** Ensure the script does not crash if the canvas context fails to initialize.