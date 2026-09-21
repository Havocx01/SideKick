"""The copilot: tool registry, numeric verification, bounded agent loop."""

from app.copilot.agent import SYSTEM_PROMPT, ask
from app.copilot.fallback import answer_without_llm
from app.copilot.tools import Tool, ToolError, ToolRegistry
from app.copilot.verify import unverified, verify_answer

__all__ = [
    "SYSTEM_PROMPT",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "answer_without_llm",
    "ask",
    "unverified",
    "verify_answer",
]
