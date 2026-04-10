from brain.tools import notes_tools

BRAIN_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": (
                "Save a note for the user. Use this when the user explicitly asks you to "
                "note, record, or remember a specific piece of information for later."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A short descriptive title for the note.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content of the note.",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "Search the user's saved notes. Use this when the user asks about something "
                "they previously asked you to record or note down."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search for in note titles and content.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    if name == "create_note":
        return notes_tools.create_note(**args)
    if name == "search_notes":
        return notes_tools.search_notes(**args)
    return f'{{"error": "unknown tool: {name}"}}'
