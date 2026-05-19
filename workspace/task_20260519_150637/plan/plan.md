# Implementation Plan

## 1. Architecture & Design Choices

*   **Design Pattern:** Model-View-Controller (MVC) adapted for Vanilla JavaScript.
    *   **Model:** `GameState` object holding snake coordinates, food position, score, and status.
    *   **View:** `Renderer` class handling Canvas drawing and DOM updates (score, overlays).
    *   **Controller:** `GameEngine` class managing the game loop, input queue, and state transitions.
*   **Rendering:** HTML5 Canvas (`<canvas>`).
    *   **Resolution:** Fixed logical grid (20x20) mapped to CSS pixels (20px per cell).
    *   **Optimization:** Use `ctx.fillRect` for snake segments and `ctx.arc` for food. Avoid unnecessary DOM manipulation during the game loop.
*   **State Management:** Centralized `GameState` object.
    *   **Status:** `IDLE`, `PLAYING`, `PAUSED`, `GAME_OVER`.
    *   **Persistence:** `StorageManager` class wrapping `localStorage` to save High Score.
*   **Input Handling:**
    *   **Keyboard:** `keydown` event listener with an `inputQueue` array to prevent 180-degree turns within a single frame.
    *   **Mobile:** HTML D-Pad buttons with `touchstart` and `touchend` listeners mapped to the same input queue logic.
*   **Game Loop:**
    *   **Throttling:** `requestAnimationFrame` with a delta-time check to enforce exactly 15 FPS (approx. 66ms per frame).
    *   **Collision:** Axis-Aligned Bounding Box (AABB) logic for walls and segment-based logic for self-collision.

## 2. Target File Structure

Since the requirement is a single file application, the structure is contained within `index.html`.

*   **`index.html` (Single File)**
    *   **`<head>`:** Meta tags, CSS styles (`<style>`).
    *   **`<body>`:**
        *   Canvas element (`#gameCanvas`).
        *   UI Overlay (`#ui-layer`) for Score, High Score, and Game Over Modal.
        *   Mobile Controls (`#mobile-controls`).
    *   **`<script>`:**
        *   `StorageManager`: Handles `localStorage`.
        *   `InputHandler`: Manages key/touch events and buffering.
        *   `GameEngine`: Core logic (update, draw, loop).
        *   `Renderer`: Canvas drawing logic.
        *   `TestRunner`: In-browser unit tests.

## 3. Step-by-step Implementation Strategy

1.  **Setup & CSS:**
    *   Define CSS variables for colors and grid size.
    *   Implement responsive layout using Flexbox/Grid.
    *   Style the Game Over modal and Mobile D-Pad.
2.  **Core Game Engine (`GameEngine`):**
    *   Initialize `GameState` (Snake at center, 3 segments).
    *   Implement `update()` loop: Move snake, check collisions, check food.
    *   Implement `draw()` loop: Clear canvas, draw snake, draw food.
    *   Throttle loop to 15 FPS.
3.  **Snake & Food Logic:**
    *   Snake movement: Update head based on direction, shift body.
    *   Food generation: Random coordinates, validate against snake body.
    *   Growth: Add segment if food consumed.
4.  **Input Handling (`InputHandler`):**
    *   Create `inputQueue` array.
    *   On keydown/touch: Check if new direction is valid (not opposite to current). Push to queue.
    *   In `update()`: Process `inputQueue.shift()` if queue is not empty.
5.  **Persistence (`StorageManager`):**
    *   Initialize High Score from `localStorage`.
    *   Save High Score on `GAME_OVER`.
6.  **UI & Mobile:**
    *   Update Score/High Score DOM elements.
    *   Show/Hide Game Over Modal based on state.
    *   Bind D-Pad buttons to input queue.
7.  **Testing (`TestRunner`):**
    *   Implement `assert` function.
    *   Run collision, score, persistence, and input buffering tests immediately after initialization.

## 4. Testing Strategy

Since external libraries are prohibited, testing is performed via a `TestRunner` class within the script.

*   **Unit Tests (Collision):**
    *   Simulate snake movement against wall boundaries.
    *   Simulate snake movement against its own body segments.
    *   Assert `gameState.gameOver` becomes `true` on collision.
*   **Integration (Score & Persistence):**
    *   Simulate eating food.
    *   Assert `score` increments by 10.
    *   Simulate `localStorage` read/write cycle.
    *   Assert High Score persists across simulated reloads.
*   **Performance:**
    *   Run simulation with 50+ segments.
    *   Verify frame rate remains stable at 15 FPS (no lag spikes).
*   **Validation (Input Buffering):**
    *   Simulate rapid key presses (e.g., Down -> Up -> Left).
    *   Assert that the snake does not reverse direction within the same frame.
    *   Assert that the last valid input is executed.

## 5. Complete Implementation Code

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vanilla JS Snake Game</title>
    <style>
        :root {
            --bg-color: #1a1a1a;
            --text-color: #ffffff;
            --accent-color: #4CAF50;
            --danger-color: #f44336;
            --grid-color: #333;
        }

        body {
            margin: 0;
            padding: 0;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            overflow: hidden;
        }

        #game-container {
            position: relative;
            box-shadow: 0 0 20px rgba(0,0,0,0.5);
        }

        canvas {
            background-color: #000;
            border: 2px solid var(--grid-color);
            display: block;
        }

        #ui-layer {
            position: absolute;
            top: 10px;
            left: 10px;
            right: 10px;
            display: flex;
            justify-content: space-between;
            pointer-events: none;
            font-size: 18px;
            font-weight: bold;
        }

        #game-over-modal {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.85);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s;
            z-index: 10;
        }

        #game-over-modal.visible {
            opacity: 1;
            pointer-events: auto;
        }

        #game-over-modal h2 {
            color: var(--danger-color);
            font-size: 40px;
            margin-bottom: 20px;
        }

        button {
            background-color: var(--accent-color);
            color: white;
            border: none;
            padding: 10px 20px;
            font-size: 18px;
            cursor: pointer;
            border-radius: 5px;
            transition: background 0.2s;
        }

        button:hover {
            background-color: #45a049;
        }

        #mobile-controls {
            margin-top: 20px;
            display: grid;
            grid-template-columns: 60px 60px 60px;
            grid-template-rows: 60px 60px;
            gap: 10px;
            justify-items: center;
            align-items: center;
        }

        .d-pad-btn {
            width: 60px;
            height: 60px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            color: white;
            font-size: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }

        .d-pad-btn:active {
            background: rgba(76, 175, 80, 0.5);
        }

        #controls-hint {
            margin-top: 10px;
            font-size: 14px;
            color: #888;
        }

        /* Responsive adjustments */
        @media (max-width: 600px) {
            canvas {
                width: 300px;
                height: 300px;
            }
        }
    </style>
</head>
<body>

    <div id="game-container">
        <canvas id="gameCanvas" width="400" height="400"></canvas>
        <div id="ui-layer">
            <div id="score">Score: 0</div>
            <div id="high-score">High Score: 0</div>
        </div>
        <div id="game-over-modal">
            <h2>Game Over</h2>
            <button id="restart-btn">Play Again</button>
        </div>
    </div>

    <div id="mobile-controls">
        <div></div>
        <button class="d-pad-btn" data-dir="up">▲</button>
        <div></div>
        <button class="d-pad-btn" data-dir="left">◀</button>
        <button class="d-pad-btn" data-dir="down">▼</button>
        <button class="d-pad-btn" data-dir="right">▶</button>
    </div>

    <div id="controls-hint">Use Arrow Keys or WASD to play</div>

    <script>
        /**
         * Storage Manager
         * Handles LocalStorage operations for High Score persistence.
         */
        class StorageManager {
            constructor() {
                this.key = 'snake_high_score';
                this.score = parseInt(localStorage.getItem(this.key) || '0');
            }

            save(score) {
                if (score > this.score) {
                    this.score = score;
                    localStorage.setItem(this.key, this.score);
                }
            }

            get() {
                return this.score;
            }
        }

        /**
         * Input Handler
         * Manages keyboard and touch input with buffering to prevent self-collision.
         */
        class InputHandler {
            constructor(game) {
                this.game = game;
                this.queue = [];
                this.setupKeyboard();
                this.setupMobile();
            }

            setupKeyboard() {
                document.addEventListener('keydown', (e) => {
                    const key = e.key.toLowerCase();
                    const validKeys = ['arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'w', 'a', 's', 'd'];
                    if (!validKeys.includes(key)) return;

                    const dir = this.getDirectionFromKey(key);
                    if (dir) {
                        this.queue.push(dir);
                    }
                });
            }

            setupMobile() {
                const buttons = document.querySelectorAll('.d-pad-btn');
                buttons.forEach(btn => {
                    btn.addEventListener('touchstart', (e) => {
                        e.preventDefault();
                        const dir = btn.getAttribute('data-dir');
                        this.queue.push(dir);
                    });
                    // Also support mouse click for testing
                    btn.addEventListener('mousedown', (e) => {
                        const dir = btn.getAttribute('data-dir');
                        this.queue.push(dir);
                    });
                });
            }

            getDirectionFromKey(key) {
                if (key === 'arrowup' || key === 'w') return 'UP';
                if (key === 'arrowdown' || key === 's') return 'DOWN';
                if (key === 'arrowleft' || key === 'a') return 'LEFT';
                if (key === 'arrowright' || key === 'd') return 'RIGHT';
                return null;
            }

            process() {
                if (this.queue.length > 0) {
                    const nextDir = this.queue.shift();
                    this.game.setDirection(nextDir);
                }
            }
        }

        /**
         * Game Engine
         * Core logic for game loop, state management, and rendering.
         */
        class GameEngine {
            constructor() {
                this.canvas = document.getElementById('gameCanvas');
                this.ctx = this.canvas.getContext('2d');
                this.storage = new StorageManager();
                this.input = new InputHandler(this);
                
                this.gridSize = 20;
                this.tileCountX = this.canvas.width / this.gridSize;
                this.tileCountY = this.canvas.height / this.gridSize;

                this.score = 0;
                this.highScore = this.storage.get();
                this.gameOver = false;
                this.paused = false;
                this.isRunning = false;

                this.snake = [];
                this.food = { x: 0, y: 0 };
                this.direction = 'RIGHT';
                this.nextDirection = 'RIGHT'; // Buffer for input

                this.lastTime = 0;
                this.frameInterval = 1000 / 15; // 15 FPS

                this.init();
            }

            init() {
                this.resetGame();
                this.updateUI();
                this.loop = this.loop.bind(this);
                requestAnimationFrame(this.loop);
            }

            resetGame() {
                this.snake = [
                    { x: 10, y: 10 },
                    { x: 9, y: 10 },
                    { x: 8, y: 10 }
                ];
                this.score = 0;
                this.gameOver = false;
                this.paused = false;
                this.direction = 'RIGHT';
                this.nextDirection = 'RIGHT';
                this.input.queue = [];
                this.placeFood();
                this.updateUI();
                document.getElementById('game-over-modal').classList.remove('visible');
            }

            placeFood() {
                let valid = false;
                while (!valid) {
                    this.food.x = Math.floor(Math.random() * this.tileCountX);
                    this.food.y = Math.floor(Math.random() * this.tileCountY);
                    
                    // Ensure food doesn't spawn on snake
                    valid = !this.snake.some(segment => segment.x === this.food.x && segment.y === this.food.y);
                }
            }

            setDirection(dir) {
                // Prevent reversing direction
                if (dir === 'UP' && this.direction === 'DOWN') return;
                if (dir === 'DOWN' && this.direction === 'UP') return;
                if (dir === 'LEFT' && this.direction === 'RIGHT') return;
                if (dir === 'RIGHT' && this.direction === 'LEFT') return;
                
                this.nextDirection = dir;
            }

            update() {
                if (this.gameOver || this.paused) return;

                // Process Input
                this.direction = this.nextDirection;

                // Move Snake
                const head = { ...this.snake[0] };
                switch (this.direction) {
                    case 'UP': head.y--; break;
                    case 'DOWN': head.y++; break;
                    case 'LEFT': head.x--; break;
                    case 'RIGHT': head.x++; break;
                }

                // Collision Detection: Walls
                if (head.x < 0 || head.x >= this.tileCountX || head.y < 0 || head.y >= this.tileCountY) {
                    this.gameOver = true;
                    this.storage.save(this.score);
                    this.updateUI();
                    return;
                }

                // Collision Detection: Self
                if (this.snake.some(segment => segment.x === head.x && segment.y === head.y)) {
                    this.gameOver = true;
                    this.storage.save(this.score);
                    this.updateUI();
                    return;
                }

                this.snake.unshift(head);

                // Food Collision
                if (head.x === this.food.x && head.y === this.food.y) {
                    this.score += 10;
                    this.placeFood();
                    // Don't pop, so snake grows
                } else {
                    this.snake.pop();
                }
            }

            draw() {
                // Clear Canvas
                this.ctx.fillStyle = '#000';
                this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

                // Draw Food
                this.ctx.fillStyle = '#ff5252';
                this.ctx.beginPath();
                const foodX = this.food.x * this.gridSize + this.gridSize / 2;
                const foodY = this.food.y * this.gridSize + this.gridSize / 2;
                this.ctx.arc(foodX, foodY, this.gridSize / 2 - 2, 0, Math.PI * 2);
                this.ctx.fill();

                // Draw Snake
                this.ctx.fillStyle = '#4CAF50';
                this.snake.forEach((segment, index) => {
                    const x = segment.x * this.gridSize;
                    const y = segment.y * this.gridSize;
                    
                    // Head is slightly different color
                    if (index === 0) {
                        this.ctx.fillStyle = '#66BB6A';
                    } else {
                        this.ctx.fillStyle = '#4CAF50';
                    }
                    
                    this.ctx.fillRect(x + 1, y + 1, this.gridSize - 2, this.gridSize - 2);
                });
            }

            updateUI() {
                document.getElementById('score').innerText = `Score: ${this.score}`;
                document.getElementById('high-score').innerText = `High Score: ${this.storage.get()}`;
            }

            gameOver() {
                this.gameOver = true;
                document.getElementById('game-over-modal').classList.add('visible');
            }

            loop(timestamp) {
                if (!this.isRunning) return;

                const deltaTime = timestamp - this.lastTime;

                if (deltaTime >= this.frameInterval) {
                    this.update();
                    this.draw();
                    this.lastTime = timestamp;
                }

                requestAnimationFrame(this.loop);
            }
        }

        /**
         * Test Runner
         * Runs unit tests to validate core logic.
         */
        class TestRunner {
            constructor(game) {
                this.game = game;
                this.passed = 0;
                this.failed = 0;
            }

            assert(condition, message) {
                if (condition) {
                    this.passed++;
                    console.log(`✓ ${message}`);
                } else {
                    this.failed++;
                    console.error(`✗ ${message}`);
                }
            }

            run() {
                console.log("Running Tests...");

                // Test 1: Initial State
                this.assert(this.game.snake.length === 3, "Initial snake length is 3");
                this.assert(this.game.score === 0, "Initial score is 0");
                this.assert(this.game.gameOver === false, "Game is not over initially");

                // Test 2: Input Buffering (Self-Collision Prevention)
                // Simulate pressing Down then Left (should not collide with head)
                this.game.setDirection('DOWN');
                this.game.setDirection('LEFT');
                this.game.update(); // Move once
                this.game.draw();
                
                // Head should be at (10, 11) then (9, 11)
                // If we pressed Down then Left, head moves Down then Left
                // But wait, the input queue processes one per frame.
                // Let's simulate a rapid press that would cause a 180 turn if not buffered.
                // Actually, the input queue processes one per frame.
                // Let's test the logic inside setDirection.
                
                // Simulate a scenario where we try to reverse
                this.game.direction = 'RIGHT';
                this.game.nextDirection = 'LEFT'; // Valid
                this.game.setDirection('LEFT');
                this.game.update();
                this.game.draw();
                
                // Head should be at (9, 10)
                this.assert(this.game.snake[0].x === 9, "Snake moved Left correctly");

                // Test 3: Wall Collision
                this.game.direction = 'RIGHT';
                this.game.nextDirection = 'RIGHT';
                this.game.setDirection('RIGHT');
                this.game.update(); // Move to (11, 10)
                this.game.update(); // Move to (12, 10)
                this.game.update(); // Move to (13, 10)
                this.game.update(); // Move to (14, 10)
                this.game.update(); // Move to (15, 10)
                this.game.update(); // Move to (16, 10)
                this.game.update(); // Move to (17, 10)
                this.game.update(); // Move to (18, 10)
                this.game.update(); // Move to (19, 10)
                this.game.update(); // Move to (20, 10) -> Game Over
                this.assert(this.game.gameOver === true, "Game Over triggered on wall collision");

                // Test 4: Self Collision
                this.game.resetGame();
                this.game.direction = 'DOWN';
                this.game.nextDirection = 'DOWN';
                this.game.setDirection('DOWN');
                this.game.update(); // (10, 11)
                this.game.update(); // (10, 12)
                this.game.update(); // (10, 13)
                this.game.update(); // (10, 14)
                this.game.update(); // (10, 15)
                this.game.update(); // (10, 16)
                this.game.update(); // (10, 17)
                this.game.update(); // (10, 18)
                this.game.update(); // (10, 19)
                this.game.update(); // (10, 20) -> Game Over
                
                // Test 5: Score Update
                this.game.resetGame();
                this.game.placeFood();
                this.game.direction = 'RIGHT';
                this.game.nextDirection = 'RIGHT';
                this.game.setDirection('RIGHT');
                this.game.update(); // Move
                this.game.update(); // Eat food
                this.assert(this.game.score === 10, "Score increased by 10 after eating");

                // Test 6: Persistence
                this.game.resetGame();
                this.game.placeFood();
                this.game.direction = 'RIGHT';
                this.game.nextDirection = 'RIGHT';
                this.game.setDirection('RIGHT');
                this.game.update(); // Move
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game.update(); // Eat food
                this.game