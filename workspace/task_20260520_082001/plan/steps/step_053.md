# Step 53

Approved & Executed: write_file {'path': 'output/snake_game/game_config.py', 'content': '# Snake Game Configuration\n\n"""Configuration constants for Snake Game."""\n\nfrom typing import Tuple\n\n# Window dimensions\nWINDOW_WIDTH = 600\nWINDOW_HEIGHT = 400\n\n# Grid settings\nGRID_SIZE = 20  # Pixel size of each grid cell\nGRID_COUNT_X = WINDOW_WIDTH // GRID_SIZE\nGRID_COUNT_Y = WINDOW_HEIGHT // GRID_SIZE\n\n# Colors (RGB)\nBLACK = (0, 0, 0)\nWHITE = (255, 255, 255)\nGREEN = (0, 255, 0)\nRED = (255, 0, 0)\nYELLOW = (255, 255, 0)\n\n# Game settings\nFPS = 60\nINITIAL_SNAKE_BODY_LENGTH = 3\nFOOD_SCORE = 10\n\n# Initialize colors\ncolors = {\n    \'background\': BLACK,\n    \'grid\': WHITE,\n    \'snake_head\': GREEN,\n    \'snake_body\': GREEN,\n    \'food\': RED,\n    \'text\': WHITE\n}\n'}

Success: File 'output/snake_game/game_config.py' written successfully.
