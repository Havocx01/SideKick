"""Copilot routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import registry, settings
from app.config import Settings
from app.copilot.fallback import answer_without_llm
from app.copilot.tools import ToolRegistry
from app.schemas import CopilotAnswer, CopilotRequest

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


@router.get("/tools")
def tools(tool_registry: ToolRegistry = Depends(registry)) -> dict:
    """The tools the copilot may call, with their schemas."""
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "mutating": tool.mutating,
            }
            for tool in (tool_registry.get(name) for name in tool_registry.names())
        ],
        "note": (
            "The copilot reaches data only through these tools. Raw sensor readings "
            "are never sent to the language model, and no tool returns a prediction."
        ),
    }


@router.get("/status")
def status(config: Settings = Depends(settings)) -> dict:
    return {
        "language_model": None,
        "available": False,
        "max_tool_calls": config.llm_max_tool_calls,
        "mode": "recorded evidence only",
        "note": "Answers are assembled from recorded evidence. This prototype makes no external model calls.",
    }


@router.post("", response_model=CopilotAnswer)
def query(request: CopilotRequest, tool_registry: ToolRegistry = Depends(registry)) -> CopilotAnswer:
    return answer_without_llm(request.question, tool_registry, reason="no API key is configured")


@router.get("/suggestions")
def suggestions() -> dict:
    """Starter questions that exercise the tools the demo depends on."""
    return {
        "suggestions": [
            "Which model should we deploy, and why?",
            "How did each candidate hold up under sensor faults?",
            "Which sensor fault hurt the models most?",
            "Show the clean detection rates with their confidence intervals.",
            "Is there anything wrong with the data?",
            "Did the fault-augmented retraining actually help?",
            "How does the age baseline compare?",
        ]
    }
