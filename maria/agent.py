# Compatibility module. Real implementation is in maria/agents/maria_agent.py
from maria.agents import (
    MariaAgent,
    parse_agent_response,
    is_llm_response,
)

__all__ = [
    "MariaAgent",
    "parse_agent_response",
    "is_llm_response",
]
