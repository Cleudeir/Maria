# Snake Game Controllers

"""Controllers for Snake Game - Game logic and state management."""

from models import Snake, Food, Direction

class GameController:
    """Main game controller."""
    
    def __init__(self):
        """Initialize game controller."""
        self.snake = Snake()
        self.food = Food(100, 100)
        self.score = 0
        self.game_over = False
        self.is_paused = False
        self.paused_count = 0
    
    def start(self):
        """Start the game."""
        self.game_over = False
        self.is_paused = False
        self.score = 0
        self.snake = Snake()
        self.food = Food(100, 100)
    
    def update(self):
        """Update game state."""
        if not self.is_paused:
            self.snake.move()
            if self.check_collision():
                self.game_over = True
            elif self.food.collides_with(self.snake):
                self.food = Food(
                    self.food.x + (self.snake.direction.value[0] * 20),
                    self.food.y + (self.snake.direction.value[1] * 20)
                )
                self.snake.grow = True
                self.score += 10
    
    def check_collision(self) -> bool:
        """Check for collision with self."""
        return self.snake.check_collision()
    
    def toggle_pause(self):
        """Toggle pause state."""
        self.is_paused = not self.is_paused
        self.paused_count += 1
    
    @property
    def is_game_over(self) -> bool:
        """Check if game is over."""
        return self.game_over
    
    def reset(self):
        """Reset game state."""
        self.start()
