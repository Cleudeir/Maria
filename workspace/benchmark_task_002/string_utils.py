"""
String utilities module. This module provides utility functions for string manipulation.
""" def reverse_string(s: str) -> str: """ Reverse a given string. Args: s (str): The input string to be reversed. Returns: str: The reversed string. Example: >>> reverse_string("hello") 'olleh' >>> reverse_string("") '' """ return s[::-1]
