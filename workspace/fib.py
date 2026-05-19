def fibonacci(n):
    """Return the N-th Fibonacci number.
    
    The Fibonacci sequence starts: 0, 1, 1, 2, 3, 5, 8, ...
    fib(0) = 0
    fib(1) = 1
    fib(n) = fib(n-1) + fib(n-2) for n >= 2
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    
    if n == 0:
        return 0
    if n == 1:
        return 1
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
