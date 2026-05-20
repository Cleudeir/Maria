# Snake Game Configuration

"""Configuration constants for Snake Game."""

from typing import Tuple

# Window dimensions
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 400

# Grid settings
GRID_SIZE = 20  # Pixel size of each grid cell
GRID_COUNT_X = WINDOW_WIDTH // GRID_SIZE
GRID_COUNT_Y = WINDOW_HEIGHT // GRID_SIZE

# Colors (RGB)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)

# Game settings
FPS = 60
INITIAL_SNAKE_BODY_LENGTH = 3
FOOD_SCORE = 10

# Initialize colors
colors = {
    'background': BLACK,
    'grid': WHITE,
    'snake_head': GREEN,
    'snake_body': GREEN,
    'food': RED,
    'text': WHITE
}
