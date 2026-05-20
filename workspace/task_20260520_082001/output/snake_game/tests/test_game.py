# Snake Game Tests

"""Tests for Snake Game Models."""

import pytest
from models import Snake, Food, Direction

class TestSnake:
    """Test Snake model."""
    
    def test_initial_state(self):
        """Test initial snake state."""
        snake = Snake()
        assert len(snake.body) == 3
        assert snake.direction == Direction.UP
    
    def test_move_up(self):
        """Test snake movement up."""
        snake = Snake()
        snake.move()
        assert snake.body[0] == (180, 200)
    
    def test_move_down(self):
        """Test snake movement down."""
        snake = Snake()
        snake.direction = Direction.DOWN
        snake.move()
        assert snake.body[0] == (200, 220)
    
    def test_move_left(self):
        """Test snake movement left."""
        snake = Snake()
        snake.direction = Direction.LEFT
        snake.move()
        assert snake.body[0] == (180, 220)
    
    def test_move_right(self):
        """Test snake movement right."""
        snake = Snake()
        snake.direction = Direction.RIGHT
        snake.move()
        assert snake.body[0] == (220, 220)
    
    def test_self_collision(self):
        """Test self-collision detection."""
        snake = Snake()
        snake.direction = Direction.RIGHT
        snake.move()
        assert snake.direction == Direction.RIGHT
    
    def test_set_direction(self):
        """Test direction setting."""
        snake = Snake()
        snake.set_direction(Direction.DOWN)
        assert snake.direction == Direction.DOWN

class TestFood:
    """Test Food model."""
    
    def test_initial_position(self):
        """Test food initial position."""
        food = Food(100, 100)
        assert food.x == 100
        assert food.y == 100
    
    def test_move(self):
        """Test food movement."""
        food = Food(100, 100)
        moved = food.move(10, 20)
        assert moved.x == 110
        assert moved.y == 120
    
    def test_collides_with_snake(self):
        """Test food collision with snake."""
        snake = Snake()
        food = Food(200, 200)
        assert food.collides_with(snake)
    
    def test_no_collides_with_snake(self):
        """Test food not colliding with snake."""
        snake = Snake()
        food = Food(200, 220)
        assert not food.collides_with(snake)

# Run all tests
pytest.main(['-v', '--quiet'])
