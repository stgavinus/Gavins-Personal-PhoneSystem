"""
/api/process — called by the AGI script on the VM during a live call.

Flow:
  1. AGI records caller audio → sends WAV here
  2. We run STT → LLM → TTS
  3. Return audio bytes + optional action signal
"""
import os
import time
import tempfile
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse

from adapters.stt import get_stt_adapter
from adapters.llm import get_llm_adapter
from adapters.tts.piper import PiperAdapter
from agents.wakeup_agent import WakeupAgent
from config import settings

router = APIRouter()

# One agent per call session, keyed by call_id
_sessions: dict[str, WakeupAgent] = {}

_stt = get_stt_adapter()
_llm = get_llm_adapter()
_tts = PiperAdapter(voice=settings.piper_voice)


@router.post("/greet")
async def greet(call_id: str = Form(...)):
    """Start a new session and return the opening greeting audio."""
    agent = WakeupAgent(_llm)
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
    """Process caller audio, return response audio + action header."""
    agent = _sessions.get(call_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save uploaded audio to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(await audio.read())
        audio_path = f.name

    t0 = time.time()
    try:
        user_text = await _stt.transcribe(audio_path)
    finally:
        os.unlink(audio_path)
    t1 = time.time()
    print(f"[timing] STT: {t1-t0:.2f}s  → {user_text!r}")

    if not user_text.strip():
        user_text = "[silence]"

    response_text, tool_result = await agent.respond(user_text)
    t2 = time.time()
    print(f"[timing] LLM: {t2-t1:.2f}s  → {response_text!r}")

    # Determine action for AGI script
    action = "continue"
    if tool_result:
        action = tool_result.get("action", "continue")
        if action == "confirm_awake":
            _sessions.pop(call_id, None)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name

    await _tts.synthesize(response_text or "Okay, have a great day!", out_path)
    t3 = time.time()
    print(f"[timing] TTS: {t3-t2:.2f}s  | total: {t3-t0:.2f}s")

    return FileResponse(out_path, media_type="audio/wav",
                        headers={"X-Action": action})


@router.delete("/session/{call_id}")
async def end_session(call_id: str):
    _sessions.pop(call_id, None)
    return {"status": "ok"}
