"""
/api/converse — inbound AI conversation initiated by the user calling in.
"""
import os
import time
import tempfile
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse

from adapters.stt import get_stt_adapter
from adapters.llm import get_llm_adapter
from adapters.tts.piper import PiperAdapter
from agents.conversation_agent import ConversationAgent
from config import settings

router = APIRouter()

_sessions: dict[str, ConversationAgent] = {}

_stt = get_stt_adapter()
_llm = get_llm_adapter()
_tts = PiperAdapter(voice=settings.piper_voice)


@router.post("/greet")
async def greet(call_id: str = Form(...)):
    agent = ConversationAgent(_llm)
    _sessions[call_id] = agent

    greeting_text = await agent.greet()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name

    await _tts.synthesize(greeting_text, out_path)
    return FileResponse(out_path, media_type="audio/wav",
                        headers={"X-Action": "continue"})


@router.post("/process")
async def process(
    call_id: str = Form(...),
    audio: UploadFile = File(...),
):
    agent = _sessions.get(call_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(await audio.read())
        audio_path = f.name

    t0 = time.time()
    try:
        user_text = await _stt.transcribe(audio_path)
    finally:
        os.unlink(audio_path)
    t1 = time.time()
    print(f"[converse][timing] STT: {t1-t0:.2f}s  → {user_text!r}")

    if not user_text.strip():
        user_text = "[silence]"

    response_text, tool_result = await agent.respond(user_text)
    t2 = time.time()
    print(f"[converse][timing] LLM: {t2-t1:.2f}s  → {response_text!r}")

    action = "continue"
    if tool_result:
        action = tool_result.get("action", "continue")
        if action == "end_call":
            _sessions.pop(call_id, None)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name

    await _tts.synthesize(response_text or "I didn't catch that.", out_path)
    t3 = time.time()
    print(f"[converse][timing] TTS: {t3-t2:.2f}s  | total: {t3-t0:.2f}s")

    return FileResponse(out_path, media_type="audio/wav",
                        headers={"X-Action": action})


@router.delete("/session/{call_id}")
async def end_session(call_id: str):
    _sessions.pop(call_id, None)
    return {"status": "ok"}
