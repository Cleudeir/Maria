# Step 16

Approved & Executed: read_file {'path': 'plan/plan.md'}

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

[truncated]
