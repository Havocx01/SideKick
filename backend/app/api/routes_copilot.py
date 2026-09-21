"""Copilot routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import registry, settings
from app.config import Settings
from app.copilot.agent import ask
from app.copilot.tools import ToolRegistry
from app.schemas import CopilotAnswer, CopilotRequest

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


@router.get("/tools")
def tools(tool_registry: ToolRegistry = Depends(registry)) -> dict:
    """The tools the copilot may call, with their schemas.

    Exposed so a reviewer can see the whole surface: there is no hidden path from
    the language model to the data.
    """
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
        "language_model": config.llm_model if config.llm_available else None,
        "available": config.llm_available,
        "max_tool_calls": config.llm_max_tool_calls,
        "mode": "language model" if config.llm_available else "recorded evidence only",
        "note": (
            "Answers are drafted by a language model and every figure is checked "
            "against a recorded metric before display."
            if config.llm_available
            else "No API key is configured, so answers are assembled directly from "
            "recorded evidence."
        ),
    }


@router.post("", response_model=CopilotAnswer)
def query(
    request: CopilotRequest,
    tool_registry: ToolRegistry = Depends(registry),
    config: Settings = Depends(settings),
) -> CopilotAnswer:
    return ask(request.question, tool_registry, settings=config)


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
