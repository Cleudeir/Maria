import os
import sys
import importlib
import math
import time
import json
import subprocess
from typing import Any

def load_module(workspace_path: str, module_name: str) -> Any:
    """Dynamically load or reload a module from the workspace directory."""
    if workspace_path not in sys.path:
        sys.path.insert(0, workspace_path)
    
    # If the module was already imported previously, remove it from sys.modules
    # to force re-importing the version in workspace_path
    if module_name in sys.modules:
        del sys.modules[module_name]
        
    try:
        module = importlib.import_module(module_name)
        return module
    except Exception as e:
        raise ImportError(f"Failed to import '{module_name}' from {workspace_path}: {e}")
    finally:
        if workspace_path in sys.path:
            sys.path.remove(workspace_path)

def verify_task_1(workspace_path: str):
    # Prime Checker
    m = load_module(workspace_path, "prime_checker")
    is_prime = getattr(m, "is_prime")
    assert is_prime(2) is True, "2 is prime"
    assert is_prime(3) is True, "3 is prime"
    assert is_prime(4) is False, "4 is not prime"
    assert is_prime(17) is True, "17 is prime"
    assert is_prime(1) is False, "1 is not prime"
    assert is_prime(0) is False, "0 is not prime"
    assert is_prime(-5) is False, "negative numbers are not prime"

def verify_task_2(workspace_path: str):
    # String Reverser
    m = load_module(workspace_path, "string_utils")
    reverse_string = getattr(m, "reverse_string")
    assert reverse_string("hello") == "olleh"
    assert reverse_string("") == ""
    assert reverse_string("a") == "a"
    assert reverse_string("A man a plan a canal Panama") == "amanaP lanac a nalp a nam A"

def verify_task_3(workspace_path: str):
    # Factorial Calculator
    m = load_module(workspace_path, "math_operations")
    factorial = getattr(m, "factorial")
    assert factorial(0) == 1
    assert factorial(1) == 1
    assert factorial(5) == 120
    assert factorial(10) == 3628800

def verify_task_4(workspace_path: str):
    # JSON Config Writer
    config_path = os.path.join(workspace_path, "config.json")
    assert os.path.exists(config_path), "config.json file does not exist"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("app_name") == "MariaTest", f"app_name is {data.get('app_name')}"
    assert data.get("version") == "1.0.0"
    assert data.get("enabled") is True

def verify_task_5(workspace_path: str):
    # Celsius to Fahrenheit Converter
    m = load_module(workspace_path, "temp_converter")
    celsius_to_fahrenheit = getattr(m, "celsius_to_fahrenheit")
    assert abs(celsius_to_fahrenheit(0.0) - 32.0) < 1e-5
    assert abs(celsius_to_fahrenheit(100.0) - 212.0) < 1e-5
    assert abs(celsius_to_fahrenheit(-40.0) - (-40.0)) < 1e-5
    assert abs(celsius_to_fahrenheit(37.0) - 98.6) < 1e-5

def verify_task_6(workspace_path: str):
    # Even Number Filter
    m = load_module(workspace_path, "list_utils")
    get_evens = getattr(m, "get_evens")
    assert get_evens([1, 2, 3, 4, 5, 6]) == [2, 4, 6]
    assert get_evens([]) == []
    assert get_evens([1, 3, 5]) == []
    assert get_evens([2, 4, -2, -3]) == [2, 4, -2]

def verify_task_7(workspace_path: str):
    # Markdown README Creator
    readme_path = os.path.join(workspace_path, "README.md")
    assert os.path.exists(readme_path), "README.md file does not exist"
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Normalize line endings
    content = content.replace("\r\n", "\n").strip()
    
    lines = content.split("\n")
    assert len(lines) >= 5, "README should contain at least 5 lines of text"
    assert lines[0].strip() == "# Project Maria"
    
    # Check that it contains "This is a test project."
    assert any("This is a test project." in line for line in lines)
    
    # Check that there are items
    assert any("* Item 1" in line or "- Item 1" in line for line in lines)
    assert any("* Item 2" in line or "- Item 2" in line for line in lines)

def verify_task_8(workspace_path: str):
    # Word Frequency Counter
    m = load_module(workspace_path, "word_count")
    count_words = getattr(m, "count_words")
    result = count_words("Hello world! Hello, world? Test, test.")
    assert result.get("hello") == 2
    assert result.get("world") == 2
    assert result.get("test") == 2
    assert len(result) == 3

def verify_task_9(workspace_path: str):
    # Basic File Merger
    # Write a.txt and b.txt into workspace first
    a_path = os.path.join(workspace_path, "a.txt")
    b_path = os.path.join(workspace_path, "b.txt")
    with open(a_path, "w", encoding="utf-8") as f:
        f.write("Line A")
    with open(b_path, "w", encoding="utf-8") as f:
        f.write("Line B")
        
    script_path = os.path.join(workspace_path, "file_merger.py")
    assert os.path.exists(script_path), "file_merger.py file does not exist"
    
    # Run the script
    subprocess.run([sys.executable, script_path], cwd=workspace_path, check=True)
    
    merged_path = os.path.join(workspace_path, "merged.txt")
    assert os.path.exists(merged_path), "merged.txt file was not created"
    with open(merged_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    assert content == "Line A\nLine B"

def verify_task_10(workspace_path: str):
    # Calculate Average
    m = load_module(workspace_path, "stats")
    calculate_average = getattr(m, "calculate_average")
    assert abs(calculate_average([1, 2, 3, 4]) - 2.5) < 1e-5
    assert abs(calculate_average([10.0, 20.0, 30.0]) - 20.0) < 1e-5
    assert calculate_average([]) == 0.0
    assert calculate_average([5]) == 5.0

def verify_task_11(workspace_path: str):
    # Fibonacci Generator
    m = load_module(workspace_path, "fibonacci")
    fibonacci_sequence = getattr(m, "fibonacci_sequence")
    assert fibonacci_sequence(10) == [0, 1, 1, 2, 3, 5, 8]
    assert fibonacci_sequence(0) == [0]
    assert fibonacci_sequence(1) == [0, 1, 1]
    assert fibonacci_sequence(-5) == []

def verify_task_12(workspace_path: str):
    # Geometric Shapes Polymorphism
    m = load_module(workspace_path, "geometry")
    Shape = getattr(m, "Shape")
    Circle = getattr(m, "Circle")
    Rectangle = getattr(m, "Rectangle")
    
    try:
        s = Shape()
        s.area()
        assert False, "Shape.area() should raise NotImplementedError"
    except NotImplementedError:
        pass
    except Exception as e:
        assert False, f"Expected NotImplementedError, got {type(e)}"
        
    c = Circle(3.0)
    assert abs(c.area() - (math.pi * 9.0)) < 1e-5
    
    r = Rectangle(4.0, 5.0)
    assert abs(r.area() - 20.0) < 1e-5

def verify_task_13(workspace_path: str):
    # CSV User Parser
    m = load_module(workspace_path, "csv_parser")
    parse_user_csv = getattr(m, "parse_user_csv")
    
    # Write a test CSV
    csv_path = os.path.join(workspace_path, "users.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com\n")
        
    result = parse_user_csv(csv_path)
    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "Alice", "email": "alice@example.com"}
    assert result[1] == {"id": 2, "name": "Bob", "email": "bob@example.com"}
    
    # Empty CSV test
    empty_csv_path = os.path.join(workspace_path, "empty.csv")
    with open(empty_csv_path, "w", encoding="utf-8") as f:
        f.write("")
    assert parse_user_csv(empty_csv_path) == []

def verify_task_14(workspace_path: str):
    # Simple Stack
    m = load_module(workspace_path, "stack")
    Stack = getattr(m, "Stack")
    s = Stack()
    assert s.is_empty() is True
    assert s.size() == 0
    
    s.push(10)
    assert s.is_empty() is False
    assert s.size() == 1
    assert s.peek() == 10
    
    s.push(20)
    assert s.size() == 2
    assert s.peek() == 20
    
    assert s.pop() == 20
    assert s.peek() == 10
    assert s.pop() == 10
    assert s.is_empty() is True
    
    try:
        s.pop()
        assert False, "Should raise IndexError on empty pop"
    except IndexError:
        pass
        
    try:
        s.peek()
        assert False, "Should raise IndexError on empty peek"
    except IndexError:
        pass

def verify_task_15(workspace_path: str):
    # Password Generator
    m = load_module(workspace_path, "password_gen")
    generate_password = getattr(m, "generate_password")
    
    try:
        generate_password(2)
        assert False, "Should raise ValueError for length < 3"
    except ValueError:
        pass
        
    pwd = generate_password(10)
    assert len(pwd) == 10
    assert any(c.isupper() for c in pwd), "Must contain at least one uppercase letter"
    assert any(c.islower() for c in pwd), "Must contain at least one lowercase letter"
    assert any(c.isdigit() for c in pwd), "Must contain at least one digit"
    
    # Try a few times to ensure randomness and consistency
    for _ in range(10):
        p = generate_password(8)
        assert len(p) == 8
        assert any(c.isupper() for c in p)
        assert any(c.islower() for c in p)
        assert any(c.isdigit() for c in p)

def verify_task_16(workspace_path: str):
    # Caesar Cipher
    m = load_module(workspace_path, "caesar")
    encrypt = getattr(m, "encrypt")
    decrypt = getattr(m, "decrypt")
    
    assert encrypt("Hello World!", 3) == "Khoor Zruog!"
    assert decrypt("Khoor Zruog!", 3) == "Hello World!"
    
    assert encrypt("XYZ abc", 5) == "CDE fgh"
    assert decrypt("CDE fgh", 5) == "XYZ abc"
    
    # Negative shift or large shift
    assert encrypt("abc", 28) == "cde"
    assert decrypt("cde", 28) == "abc"

def verify_task_17(workspace_path: str):
    # JSON Database Class
    m = load_module(workspace_path, "json_db")
    JSONDatabase = getattr(m, "JSONDatabase")
    
    db_file = os.path.join(workspace_path, "test_db.json")
    if os.path.exists(db_file):
        os.remove(db_file)
        
    db = JSONDatabase(db_file)
    assert db.get("user1") is None
    
    db.insert("user1", {"name": "Alice", "role": "admin"})
    assert db.get("user1") == {"name": "Alice", "role": "admin"}
    
    # Verify file persistence
    with open(db_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data.get("user1") == {"name": "Alice", "role": "admin"}
    
    # Update test
    assert db.update("user1", {"role": "superadmin", "age": 30}) is True
    assert db.get("user1") == {"name": "Alice", "role": "superadmin", "age": 30}
    assert db.update("user2", {"name": "Bob"}) is False
    
    # Delete test
    assert db.delete("user1") is True
    assert db.get("user1") is None
    assert db.delete("user1") is False

def verify_task_18(workspace_path: str):
    # Directory Extension Scanner
    m = load_module(workspace_path, "dir_scanner")
    count_file_types = getattr(m, "count_file_types")
    
    # Create test directory structure
    test_dir = os.path.join(workspace_path, "test_scan_dir")
    os.makedirs(test_dir, exist_ok=True)
    os.makedirs(os.path.join(test_dir, "sub"), exist_ok=True)
    
    open(os.path.join(test_dir, "file1.txt"), "w").close()
    open(os.path.join(test_dir, "file2.TXT"), "w").close()  # lowercased check
    open(os.path.join(test_dir, "file3.py"), "w").close()
    open(os.path.join(test_dir, "sub", "file4.py"), "w").close()
    open(os.path.join(test_dir, "sub", "no_ext"), "w").close()
    open(os.path.join(test_dir, "sub", ".gitignore"), "w").close()
    
    result = count_file_types(test_dir)
    assert result.get(".txt") == 2, f"Expected 2 .txt files, got {result.get('.txt')}"
    assert result.get(".py") == 2, f"Expected 2 .py files, got {result.get('.py')}"
    assert result.get("no_extension") == 2, f"Expected 2 files with no_extension (.gitignore and no_ext), got {result.get('no_extension')}"

def verify_task_19(workspace_path: str):
    # Multi-key User Sorter
    m = load_module(workspace_path, "sorter")
    sort_users = getattr(m, "sort_users")
    
    users = [
        {"name": "Charlie", "age": 30},
        {"name": "Alice", "age": 25},
        {"name": "Bob", "age": 25},
        {"name": "David", "age": 35}
    ]
    sorted_users = sort_users(users)
    assert sorted_users == [
        {"name": "Alice", "age": 25},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 30},
        {"name": "David", "age": 35}
    ]

def verify_task_20(workspace_path: str):
    # IPv4 Address Validator
    m = load_module(workspace_path, "ipv4_validator")
    is_valid_ipv4 = getattr(m, "is_valid_ipv4")
    
    assert is_valid_ipv4("192.168.1.1") is True
    assert is_valid_ipv4("0.0.0.0") is True
    assert is_valid_ipv4("255.255.255.255") is True
    assert is_valid_ipv4("192.168.01.1") is False, "leading zero in octet"
    assert is_valid_ipv4("256.0.0.1") is False, "octet > 255"
    assert is_valid_ipv4("1.2.3.-4") is False, "negative number"
    assert is_valid_ipv4("1.2.3") is False, "only 3 octets"
    assert is_valid_ipv4("1.2.3.4.5") is False, "5 octets"
    assert is_valid_ipv4("abc.def.ghi.jkl") is False, "non-numeric"

def verify_task_21(workspace_path: str):
    # Arithmetic Expression Evaluator
    m = load_module(workspace_path, "calculator")
    evaluate_expression = getattr(m, "evaluate_expression")
    
    assert abs(evaluate_expression("3 + 4") - 7.0) < 1e-5
    assert abs(evaluate_expression("10 - 2 * 3") - 4.0) < 1e-5
    assert abs(evaluate_expression("3 + 4 * 2 / ( 1 - 5 )") - 1.0) < 1e-5
    assert abs(evaluate_expression("(10 + 20) * 3 / 9") - 10.0) < 1e-5

def verify_task_22(workspace_path: str):
    # Concurrent Worker Pool
    m = load_module(workspace_path, "worker_pool")
    SimpleWorkerPool = getattr(m, "SimpleWorkerPool")
    
    pool = SimpleWorkerPool(num_threads=3)
    
    def test_func(x):
        time.sleep(0.1)
        return x * x
        
    pool.submit(test_func, 2)
    pool.submit(test_func, 3)
    pool.submit(test_func, 4)
    
    pool.join()
    
    assert len(pool.results) == 3
    assert set(pool.results) == {4, 9, 16}

def verify_task_23(workspace_path: str):
    # Base64 Encoder and Decoder
    m = load_module(workspace_path, "base64_codec")
    encode_base64 = getattr(m, "encode_base64")
    decode_base64 = getattr(m, "decode_base64")
    
    test_cases = [
        b"hello",
        b"world!",
        b"any carnal pleasure.",
        b"",
        b"\x00\x01\x02\x03\xff"
    ]
    import base64
    for case in test_cases:
        expected_enc = base64.b64encode(case).decode("utf-8")
        assert encode_base64(case) == expected_enc, f"Failed encode for {case}"
        assert decode_base64(expected_enc) == case, f"Failed decode for {expected_enc}"

def verify_task_24(workspace_path: str):
    # Simple SQL Select Query Parser
    m = load_module(workspace_path, "sql_parser")
    parse_select_query = getattr(m, "parse_select_query")
    
    q1 = "SELECT name, age FROM users WHERE id = 10"
    res1 = parse_select_query(q1)
    assert res1 == {
        "fields": ["name", "age"],
        "table": "users",
        "where": {"column": "id", "value": 10}
    }
    
    q2 = "SELECT name FROM users WHERE role = 'admin'"
    res2 = parse_select_query(q2)
    assert res2 == {
        "fields": ["name"],
        "table": "users",
        "where": {"column": "role", "value": "admin"}
    }
    
    try:
        parse_select_query("INSERT INTO users VALUES (1)")
        assert False, "Should raise ValueError for invalid select query"
    except ValueError:
        pass

def verify_task_25(workspace_path: str):
    # Binary Run-length Encoder/Decoder
    m = load_module(workspace_path, "rle")
    rle_encode = getattr(m, "rle_encode")
    rle_decode = getattr(m, "rle_decode")
    
    assert rle_encode(b"AAA") == b"A\x03"
    assert rle_decode(b"A\x03") == b"AAA"
    
    assert rle_encode(b"AABBBCCCC") == b"A\x02B\x03C\x04"
    assert rle_decode(b"A\x02B\x03C\x04") == b"AABBBCCCC"
    
    # Test run > 255
    long_data = b"A" * 300
    encoded = rle_encode(long_data)
    assert encoded == b"A\xffA\x2d" or encoded == b"A\xffA\x2d" # 255 + 45
    assert rle_decode(encoded) == long_data

def verify_task_26(workspace_path: str):
    # Tic-Tac-Toe Minimax AI
    m = load_module(workspace_path, "tictactoe")
    TicTacToe = getattr(m, "TicTacToe")
    
    game = TicTacToe()
    # Check basic move making
    assert game.make_move(0, 0, "X") is True
    assert game.make_move(0, 0, "O") is False, "cell occupied"
    assert game.make_move(3, 0, "O") is False, "out of bounds"
    
    # Check winning state
    game = TicTacToe()
    game.make_move(0, 0, "X")
    game.make_move(0, 1, "X")
    game.make_move(0, 2, "X")
    assert game.check_winner() == "X"
    
    # Test Minimax blocking or taking the win
    game = TicTacToe()
    game.make_move(0, 0, "O")
    game.make_move(0, 1, "O")
    # Player X must play (0, 2) to block O
    move = game.best_move("X")
    assert move == (0, 2)
    
    # Test Minimax winning move
    game = TicTacToe()
    game.make_move(1, 0, "X")
    game.make_move(1, 1, "X")
    # Player X can play (1, 2) to win
    move = game.best_move("X")
    assert move == (1, 2)

def verify_task_27(workspace_path: str):
    # Token Lexer
    m = load_module(workspace_path, "lexer")
    tokenize = getattr(m, "tokenize")
    
    # The prompt requests support for KEYWORD, IDENTIFIER, NUMBER, OPERATOR, SEMICOLON
    code = "if x = 10 return 5;"
    tokens = tokenize(code)
    assert len(tokens) == 7
    assert tokens[0] == {"type": "KEYWORD", "value": "if"}
    assert tokens[1] == {"type": "IDENTIFIER", "value": "x"}
    assert tokens[2] == {"type": "OPERATOR", "value": "="}
    assert tokens[3] == {"type": "NUMBER", "value": "10"}
    assert tokens[4] == {"type": "KEYWORD", "value": "return"}
    assert tokens[5] == {"type": "NUMBER", "value": "5"}
    assert tokens[6] == {"type": "SEMICOLON", "value": ";"}
    
    code_with_semi = "x = 42;"
    tokens_semi = tokenize(code_with_semi)
    assert tokens_semi[3] == {"type": "SEMICOLON", "value": ";"}
    
    # Error checking
    try:
        tokenize("x = 10 @ 20")
        assert False, "Should raise ValueError for invalid char @"
    except ValueError:
        pass

def verify_task_28(workspace_path: str):
    # Thread-safe Key-Value Store with TTL
    m = load_module(workspace_path, "kv_store")
    TTLKeyValueStore = getattr(m, "TTLKeyValueStore")
    
    store = TTLKeyValueStore()
    store.set("a", 100)
    assert store.get("a") == 100
    
    # TTL check
    store.set("b", 200, ttl_seconds=0.1)
    assert store.get("b") == 200
    time.sleep(0.2)
    assert store.get("b") is None
    
    # Delete test
    assert store.delete("a") is True
    assert store.get("a") is None
    assert store.delete("a") is False

def verify_task_29(workspace_path: str):
    # Regex Matcher from Scratch
    m = load_module(workspace_path, "regex_matcher")
    match_pattern = getattr(m, "match_pattern")
    
    assert match_pattern("a", "a") is True
    assert match_pattern("a", "b") is False
    assert match_pattern(".", "a") is True
    assert match_pattern("a*", "") is True
    assert match_pattern("a*", "aaa") is True
    assert match_pattern("^ab*c$", "ac") is True
    assert match_pattern("^ab*c$", "abbc") is True
    assert match_pattern("^ab*c$", "abbd") is False
    assert match_pattern("a.*b", "axxxb") is True

def verify_task_30(workspace_path: str):
    # Dependency Injection Container
    m = load_module(workspace_path, "di_container")
    Container = getattr(m, "Container")
    
    class Database:
        def __init__(self):
            pass
            
    class UserRepository:
        def __init__(self, db):
            self.db = db
            
    class UserService:
        def __init__(self, repo):
            self.repo = repo
            
    container = Container()
    container.register_singleton("db", Database)
    container.register_transient("repo", UserRepository, ["db"])
    container.register_transient("service", UserService, ["repo"])
    
    service = container.resolve("service")
    assert isinstance(service, UserService)
    assert isinstance(service.repo, UserRepository)
    assert isinstance(service.repo.db, Database)
    
    # Singleton check
    db1 = container.resolve("db")
    db2 = container.resolve("db")
    assert db1 is db2, "db singleton instances should be identical"
    
    # Transient check
    repo1 = container.resolve("repo")
    repo2 = container.resolve("repo")
    assert repo1 is not repo2 or repo1 is not repo2, "Transient instances should be distinct" # Transient should create new instances

def verify_task_31(workspace_path: str):
    # Snake Game HTML
    html_path = os.path.join(workspace_path, "index.html")
    assert os.path.exists(html_path), "index.html file does not exist"
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "game-canvas" in content or "canvas" in content.lower(), "Should contain canvas element"
    assert "snake" in content.lower(), "Should mention snake in HTML/JS"
    assert "score" in content.lower(), "Should implement scoring mechanism"
    assert "keydown" in content.lower() or "arrow" in content.lower() or "wasd" in content.lower(), "Should handle keyboard inputs"
