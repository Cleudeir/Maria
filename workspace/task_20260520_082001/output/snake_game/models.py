# Snake Game Models

"""Models for Snake Game."""

from enum import Enum
from typing import List, Tuple

class Direction(Enum):
    """Direction enum for snake movement."""
    UP = (-20, 0)
    DOWN = (20, 0)
    LEFT = (0, -20)
    RIGHT = (0, 20)
    
    def get_delta(self):
        """Get coordinate delta for movement."""
        return self.value

class Snake:
    """Snake model."""
    
    def __init__(self):
        """Initialize snake with starting position."""
        self.body: List[Tuple[int, int]] = [(180, 200), (180, 220), (180, 240)]
        self.direction = Direction.UP
    
    def move(self):
        """Move the snake in current direction."""
        delta = self.direction.get_delta()
        new_head = (self.body[0][0] + delta[0], self.body[0][1] + delta[1])
        self.body.insert(0, new_head)
        self.body.pop()
    
    def set_direction(self, direction: Direction):
        """Set snake direction."""
        self.direction = direction
    
    def check_collision(self) -> bool:
        """Check if snake collides with itself."""
        head = self.body[0]
        for i in range(1, len(self.body)):
            if head == self.body[i]:
                return True
        return False

class Food:
    """Food model."""
    
    def __init__(self, x: int, y: int):
        """Initialize food with position."""
        self.x = x
        self.y = y
    
    def move(self, dx: int, dy: int) -> 'Food':
        """Move food and return new position."""
        new_food = Food(self.x + dx, self.y + dy)
        return new_food
    
    def collides_with(self, snake: Snake) -> bool:
        """Check if food collides with snake."""
        head = snake.body[0]
        return (self.x == head[0] and self.y == head[1])
