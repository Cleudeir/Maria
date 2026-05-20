# Snake Game Renderer

"""Renderer for Snake Game using Pygame."""

import pygame
from config import WINDOW_WIDTH, WINDOW_HEIGHT, GRID_SIZE, BLACK, WHITE, GREEN, RED, YELLOW
from models import Snake, Food, Direction

class Renderer:
    """Handles rendering for the game."""
    
    def __init__(self):
        """Initialize renderer."""
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
    
    def draw_grid(self):
        """Draw the game grid."""
        for x in range(0, WINDOW_WIDTH, GRID_SIZE):
            for y in range(0, WINDOW_HEIGHT, GRID_SIZE):
                rect = pygame.Rect(x, y, GRID_SIZE, GRID_SIZE)
                pygame.draw.rect(self.screen, BLACK, rect, 1)
    
    def draw_snake(self, snake: Snake):
        """Draw the snake."""
        for i, (x, y) in enumerate(snake.body):
            if i == 0:
                color = GREEN  # Head
            else:
                color = GREEN  # Body
            
            rect = pygame.Rect(x, y, GRID_SIZE, GRID_SIZE)
            pygame.draw.rect(self.screen, color, rect)
    
    def draw_food(self, food):
        """Draw the food."""
        rect = pygame.Rect(food.x, food.y, GRID_SIZE, GRID_SIZE)
        pygame.draw.rect(self.screen, RED, rect)
    
    def draw_score(self, score):
        """Draw the score."""
        font = pygame.font.Font(None, 36)
        text = font.render(f"Score: {score}", True, WHITE)
        self.screen.blit(text, (10, 10))
    
    def draw_pause(self):
        """Draw pause overlay."""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        overlay.set_alpha(128)
        overlay.fill(BLACK)
        self.screen.blit(overlay, (0, 0))
        font = pygame.font.Font(None, 72)
        text = font.render("PAUSED", True, YELLOW)
        text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(text, text_rect)
    
    def draw_game_over(self):
        """Draw game over overlay."""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        overlay.set_alpha(128)
        overlay.fill(BLACK)
        self.screen.blit(overlay, (0, 0))
        font = pygame.font.Font(None, 72)
        text = font.render("GAME OVER", True, RED)
        text_rect = text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(text, text_rect)
    
    def draw(self):
        """Draw all game elements."""
        self.screen.fill(BLACK)
        self.draw_grid()
        self.draw_snake(self.snake)
        self.draw_food(self.food)
        self.draw_score(self.score)
        if self.is_paused:
            self.draw_pause()
        if self.game_over:
            self.draw_game_over()
    
    def show(self):
        """Display the frame."""
        pygame.display.flip()

# Initialize renderer
renderer = Renderer()
