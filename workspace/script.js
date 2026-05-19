class SnakeGame {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.gridSize = 20;
        this.tileCountX = this.canvas.width / this.gridSize;
        this.tileCountY = this.canvas.height / this.gridSize;
        
        this.snake = [{x: 10, y: 10}, {x: 9, y: 10}, {x: 8, y: 10}];
        this.food = this.spawnFood();
        this.direction = 'UP';
        this.nextDirection = 'UP';
        this.score = 0;
        this.gameOver = false;
        this.gameLoop = null;
        
        this.bindEvents();
        this.startGame();
    }
    
    spawnFood() {
        let x, y;
        do {
            x = Math.floor(Math.random() * this.tileCountX);
            y = Math.floor(Math.random() * this.tileCountY);
        } while (this.snake.some(segment => segment.x === x && segment.y === y));
        return {x, y};
    }
    
    bindEvents() {
        document.addEventListener('keydown', (e) => {
            switch(e.key) {
                case 'ArrowUp':
                    if (this.direction !== 'DOWN') this.nextDirection = 'UP';
                    break;
                case 'ArrowDown':
                    if (this.direction !== 'UP') this.nextDirection = 'DOWN';
                    break;
                case 'ArrowLeft':
                    if (this.direction !== 'RIGHT') this.nextDirection = 'LEFT';
                    break;
                case 'ArrowRight':
                    if (this.direction !== 'LEFT') this.nextDirection = 'RIGHT';
                    break;
                case ' ':
                    this.resetGame();
                    break;
            }
        });
    }
    
    startGame() {
        this.draw();
        this.gameLoop = setInterval(() => this.update(), 100);
    }
    
    resetGame() {
        this.snake = [{x: 10, y: 10}, {x: 9, y: 10}, {x: 8, y: 10}];
        this.food = this.spawnFood();
        this.direction = 'UP';
        this.nextDirection = 'UP';
        this.score = 0;
        this.gameOver = false;
        this.updateScore();
        this.draw();
        this.gameLoop = setInterval(() => this.update(), 100);
    }
    
    update() {
        if (this.gameOver) return;
        
        this.direction = this.nextDirection;
        const head = { ...this.snake[0] };
        
        switch(this.direction) {
            case 'UP': head.y--; break;
            case 'DOWN': head.y++; break;
            case 'LEFT': head.x--; break;
            case 'RIGHT': head.x++; break;
        }
        
        // Check wall collision
        if (head.x < 0 || head.x >= this.tileCountX || 
            head.y < 0 || head.y >= this.tileCountY) {
            this.gameOver = true;
            this.showGameOver();
            return;
        }
        
        // Check self collision
        if (this.snake.some(segment => segment.x === head.x && segment.y === head.y)) {
            this.gameOver = true;
            this.showGameOver();
            return;
        }
        
        this.snake.unshift(head);
        
        // Check food collision
        if (head.x === this.food.x && head.y === this.food.y) {
            this.score += 10;
            this.updateScore();
            this.food = this.spawnFood();
        } else {
            this.snake.pop();
        }
        
        this.draw();
    }
    
    draw() {
        // Clear canvas
        this.ctx.fillStyle = '#0d0d1a';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        // Draw food
        this.ctx.fillStyle = '#ff4444';
        this.ctx.beginPath();
        this.ctx.arc(
            this.food.x * this.gridSize + this.gridSize / 2,
            this.food.y * this.gridSize + this.gridSize / 2,
            this.gridSize / 2 - 2,
            0,
            Math.PI * 2
        );
        this.ctx.fill();
        
        // Draw snake
        this.snake.forEach((segment, index) => {
            this.ctx.fillStyle = index === 0 ? '#00ff87' : '#00b8ff';
            this.ctx.fillRect(
                segment.x * this.gridSize + 1,
                segment.y * this.gridSize + 1,
                this.gridSize - 2,
                this.gridSize - 2
            );
        });
    }
    
    updateScore() {
        document.getElementById('score').textContent = this.score;
    }
    
    showGameOver() {
        const overlay = document.createElement('div');
        overlay.className = 'game-over';
        overlay.innerHTML = `
            <h2>Game Over!</h2>
            <p>Final Score: ${this.score}</p>
            <button class="restart-btn" onclick="game.resetGame()">Play Again</button>
        `;
        this.canvas.appendChild(overlay);
    }
}

// Initialize game when DOM is ready
let game;
document.addEventListener('DOMContentLoaded', () => {
    game = new SnakeGame('game-board');
});
