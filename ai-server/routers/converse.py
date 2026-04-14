"""
/api/converse — inbound AI conversation initiated by the user calling in.
Thin bridge: STT → brain → TTS.
"""
import os
import time
import tempfile
from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse

from adapters.stt import get_stt_adapter
from adapters.tts import get_tts_adapter
from brain.agent import get_brain

router = APIRouter()

_stt = get_stt_adapter()
_tts = get_tts_adapter()


@router.post("/greet")
async def greet(call_id: str = Form(...)):
    greeting_text, _ = await get_brain().chat(
        "[call_connected]",
        session_id=call_id,
        channel="phone",
    )
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
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(await audio.read())
        audio_path = f.name

    t0 = time.time()
    try:
        user_text = await _stt.transcribe(audio_path)
    finally:
        os.unlink(audio_path)
    t1 = time.time()
    print(f"[brain][timing] STT: {t1-t0:.2f}s  → {user_text!r}")

    if not user_text.strip():
        user_text = "[silence]"

    response_text, action = await get_brain().chat(
        user_text,
        session_id=call_id,
        channel="phone",
    )
    t2 = time.time()
    print(f"[brain][timing] LLM: {t2-t1:.2f}s  → {response_text!r}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name

    await _tts.synthesize(response_text or "I didn't catch that.", out_path)
    t3 = time.time()
    print(f"[brain][timing] TTS: {t3-t2:.2f}s  | total: {t3-t0:.2f}s")

    return FileResponse(out_path, media_type="audio/wav",
                        headers={"X-Action": action})


@router.delete("/session/{call_id}")
async def end_session(call_id: str):
    from brain.memory import DB_PATH
    import sqlite3
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM messages WHERE session_id = ?", (call_id,))
    return {"status": "ok"}
