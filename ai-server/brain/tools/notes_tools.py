import json
from brain import memory


def create_note(title: str, content: str) -> str:
    memory.create_note(title, content)
    return json.dumps({"saved": True})


def search_notes(query: str) -> str:
    results = memory.search_notes(query)
    return json.dumps({"results": results})
