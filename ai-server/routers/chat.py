"""
POST /chat — brain's public HTTP API.
Accepts text, returns text. Channel-agnostic.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from brain.agent import get_brain
from brain import memory, mem0_client

router = APIRouter()


class ChatRequest(BaseModel):
    text: str
    session_id: str
    channel: str = "phone"


class ChatResponse(BaseModel):
    response: str
    action: str


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    response_text, action = await get_brain().chat(
        req.text,
        session_id=req.session_id,
        channel=req.channel,
    )
    return ChatResponse(response=response_text, action=action)


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Delete session message history from SQLite."""
    import sqlite3
    from brain.memory import DB_PATH
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    return {"status": "ok"}


@router.get("/memory")
async def list_memory(user_id: str = "default"):
    """Debug: list all Mem0 memories for a user."""
    if mem0_client._mem0 is None:
        return {"memories": [], "note": "Mem0 not initialised"}
    try:
        results = mem0_client._mem0.get_all(user_id=user_id)
        items = results.get("results", results) if isinstance(results, dict) else results
        return {"memories": [r.get("memory", str(r)) for r in items]}
    except Exception as e:
        return {"error": str(e)}
