# Compatibility module. Real implementation is in maria/agents/self_improvement.py
from maria.agents import (
    SelfImprovementAgent,
    parse_self_improvement_response,
    parse_compacted_lessons_response,
)

__all__ = [
    "SelfImprovementAgent",
    "parse_self_improvement_response",
    "parse_compacted_lessons_response",
]
