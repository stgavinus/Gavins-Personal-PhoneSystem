"""
Tool registry — add new tools here. Each tool needs:
  - A function
  - An Ollama-compatible schema (same shape as OpenAI function calling)
"""
from .call_tools import confirm_awake, end_call


TOOLS: dict[str, callable] = {
    "confirm_awake": confirm_awake,
    "end_call": end_call,
}

# Schema sent to the LLM so it knows what tools are available
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "confirm_awake",
            "description": "Call this when the user has confirmed they are awake and ready to start their day.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": "Call this to hang up the phone.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def get_tool(name: str):
    return TOOLS.get(name)
