# Snake Game Controller Tests

"""Tests for Snake Game Controllers."""

import pytest
from controllers import GameController
from models import Snake, Food, Direction

class TestGameController:
    """Test GameController."""
    
    def test_initialization(self):
        """Test game controller initialization."""
        game = GameController()
        assert game.snake.body == [(180, 200), (180, 220), (180, 240)]
        assert game.food.x == 100
        assert game.food.y == 100
        assert game.score == 0
        assert game.game_over == False
        assert game.is_paused == False
    
    def test_start(self):
        """Test game start."""
        game = GameController()
        game.start()
        assert game.score == 0
        assert game.game_over == False
        assert game.is_paused == False
    
    def test_update_with_food_collision(self):
        """Test food eating logic."""
        game = GameController()
        game.update()
        assert game.snake.body == [(180, 200), (180, 220), (180, 240)]
        assert game.score == 0
    
    def test_update_with_collision(self):
        """Test collision with self."""
        game = GameController()
        game.update()
        game.update()
        assert game.game_over == True
    
    def test_toggle_pause(self):
        """Test pause toggle."""
        game = GameController()
        game.toggle_pause()
        assert game.is_paused == True
        assert game.paused_count == 1
        
        game.toggle_pause()
        assert game.is_paused == False
        assert game.paused_count == 2
    
    def test_reset(self):
        """Test game reset."""
        game = GameController()
        game.game_over = True
        game.reset()
        assert game.game_over == False
        assert game.score == 0
        assert game.is_paused == False
    
    def test_direction_check(self):
        """Test direction setting."""
        game = GameController()
        game.snake.direction = Direction.DOWN
        assert game.snake.direction == Direction.DOWN
    
    def test_self_collision_check(self):
        """Test self-collision detection."""
        game = GameController()
        game.snake.direction = Direction.UP
        game.snake.move()
        game.snake.move()
        game.snake.move()
        game.snake.move()
        assert game.check_collision() == True

# Run all tests
pytest.main(['-v', '--quiet'])
