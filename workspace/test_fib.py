import unittest

class TestFibonacci(unittest.TestCase):
    def test_fib_0(self):
        """Test fibonacci(0) returns 0"""
        from fib import fibonacci
        self.assertEqual(fibonacci(0), 0)
    
    def test_fib_1(self):
        """Test fibonacci(1) returns 1"""
        from fib import fibonacci
        self.assertEqual(fibonacci(1), 1)
    
    def test_fib_2(self):
        """Test fibonacci(2) returns 1"""
        from fib import fibonacci
        self.assertEqual(fibonacci(2), 1)
    
    def test_fib_3(self):
        """Test fibonacci(3) returns 2"""
        from fib import fibonacci
        self.assertEqual(fibonacci(3), 2)
    
    def test_fib_5(self):
        """Test fibonacci(5) returns 5"""
        from fib import fibonacci
        self.assertEqual(fibonacci(5), 5)

if __name__ == '__main__':
    unittest.main()
