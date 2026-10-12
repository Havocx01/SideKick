"""Read-only AI investigation. The server owns every displayed claim and reference."""
from app.assistant.agent import investigate


async def enhance_analysis(result, context, settings, *, tools):
    if tools.context != context:
        raise ValueError("Investigation context mismatch.")
    if context.task == "deep":
        from app.assistant.deep import investigate_deep
        return await investigate_deep(tools, settings)
    return await investigate(tools, settings)
