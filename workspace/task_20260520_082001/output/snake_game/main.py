# Snake Game - Main Entry Point

"""Entry point for Snake Game."""

import pygame
import sys
from models import Snake, Food, Direction
from controllers import GameController

# Initialize Pygame
pygame.init()

# Create game window
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 400
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Snake Game")

# Game Clock
clock = pygame.time.Clock()
clock.tick(60)  # 60 FPS

# Main Game Loop
running = True
while running:
    # Handle events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_SPACE:
                game.toggle_pause()
    
    # Get current direction
    if not game.is_paused:
        direction = snake.direction
        
        # Handle keyboard input
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            if direction != Direction.DOWN:
                game.snake.set_direction(Direction.UP)
        elif keys[pygame.K_DOWN]:
            if direction != Direction.UP:
                game.snake.set_direction(Direction.DOWN)
        elif keys[pygame.K_LEFT]:
            if direction != Direction.RIGHT:
                game.snake.set_direction(Direction.LEFT)
        elif keys[pygame.K_RIGHT]:
            if direction != Direction.LEFT:
                game.snake.set_direction(Direction.RIGHT)
    
    # Update game state
    game.update()
    
    # Draw everything
    game.draw()
    
    # Display score
    pygame.display.flip()
    
    # Check if game over
    if game.is_game_over:
        game.reset()

# Quit Pygame
pygame.quit()
sys.exit()
