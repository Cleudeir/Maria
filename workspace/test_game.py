import unittest
import os

class TestSnakeGame(unittest.TestCase):
    def test_index_html_exists(self):
        """Test that index.html exists"""
        self.assertTrue(os.path.isfile('index.html'), "index.html should exist")
    
    def test_style_css_exists(self):
        """Test that style.css exists"""
        self.assertTrue(os.path.isfile('style.css'), "style.css should exist")
    
    def test_script_js_exists(self):
        """Test that script.js exists"""
        self.assertTrue(os.path.isfile('script.js'), "script.js should exist")
    
    def test_index_html_contains_canvas(self):
        """Test that index.html contains a canvas element with id 'game-board'"""
        with open('index.html', 'r') as f:
            content = f.read()
        self.assertIn('<canvas id="game-board"', content, "index.html should contain canvas with id 'game-board'")
    
    def test_index_html_loads_script_js(self):
        """Test that index.html loads script.js"""
        with open('index.html', 'r') as f:
            content = f.read()
        self.assertIn('script.js', content, "index.html should load script.js")

if __name__ == '__main__':
    unittest.main()
