# Compatibility module. Real implementation is in maria/agents/
from agentic.agents import (
    MariaAgent,
    parse_agent_response,
    parse_agent_responses,
)

__all__ = [
    "MariaAgent",
    "parse_agent_response",
    "parse_agent_responses",
]
