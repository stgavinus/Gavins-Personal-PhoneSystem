"""
CallSession — per-call orchestration and state machine.

One instance is created per inbound AudioSocket connection and lives for the
duration of the call.  It owns three concurrent asyncio tasks:

    _rx_task    Read AudioSocket frames from Asterisk.
                  • AUDIO frames → audio_queue (fed to STT)
                  • HANGUP frame → signal clean shutdown
    _stt_task   Drain audio_queue, forward to Deepgram WebSocket.
    _speak_task (cancellable) — fires when STT signals EndOfTurn:
                  • Build prompt from session history + Mem0 memories
                  • Stream Gemini tokens, accumulate to sentence boundary
                  • Stream TTS chunks back through AudioSocket

State machine
─────────────
    IDLE          call just connected, no audio yet
    LISTENING     user may be speaking; audio forwarded to STT
    PROCESSING    user finished; LLM + TTS running
    SPEAKING      TTS audio is being sent to Asterisk
    BARGE_IN      StartOfTurn arrived during SPEAKING; _speak_task cancelled

Transitions
───────────
    IDLE        → LISTENING         on first audio frame (answer + STT open)
    LISTENING   → PROCESSING        on STT utterance_end
    PROCESSING  → SPEAKING          when first TTS audio byte is ready
    SPEAKING    → LISTENING         when TTS stream finishes
    SPEAKING    → BARGE_IN          on STT speech_start
    BARGE_IN    → LISTENING         immediately after cancelling _speak_task

Double-fire guard: if a second utterance_end arrives while PROCESSING/SPEAKING
(can happen if speech_final and UtteranceEnd both fire), it is silently dropped.
"""
import asyncio
import os
import re
import sys
import time
from enum import Enum, auto

import httpx

from bridge import protocol as proto
from bridge.log import BoundLogger
from bridge.stt import StreamingSTT
from bridge.tts import StreamingTTS

# ── Sentence boundary regex ───────────────────────────────────────────────────
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# ── Environment / config ──────────────────────────────────────────────────────
_DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
_TTS_VOICE        = os.environ.get("TTS_DEEPGRAM_VOICE", "aura-asteria-en")
_BRAIN_URL        = os.environ.get("BRAIN_URL", "http://localhost:8000")

# How long to wait for the greeting TTS before falling back to silence (seconds)
_GREET_TIMEOUT = 10.0
# Max tool-call iterations per turn
_MAX_TOOL_ITERS = 5
# Session timeout: close call after this many seconds of total silence
_IDLE_TIMEOUT = 20.0


class State(Enum):
    IDLE       = auto()
    LISTENING  = auto()
    PROCESSING = auto()
    SPEAKING   = auto()
    BARGE_IN   = auto()


class CallSession:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        log: BoundLogger,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._log    = log

        self._state: State = State.IDLE
        self._hangup_event = asyncio.Event()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)

        self._stt: StreamingSTT | None = None
        self._speak_task: asyncio.Task | None = None

        self._tts = StreamingTTS(_DEEPGRAM_API_KEY, log, _TTS_VOICE)

        self._session_id: str = ""
        self._last_activity: float = time.monotonic()

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run until the call hangs up or times out."""
        try:
            # First frame must be the UUID
            ftype, payload = await asyncio.wait_for(
                proto.read_frame(self._reader), timeout=5.0
            )
            if ftype != proto.UUID:
                self._log.error("session_no_uuid", ftype=ftype)
                return
            self._session_id = payload.decode("utf-8", errors="replace").strip("\x00")
            self._log = self._log.bind(session_id=self._session_id)
            self._log.info("session_start")

            # Launch concurrent tasks
            rx_task  = asyncio.create_task(self._rx_loop(),  name="rx")
            stt_task = asyncio.create_task(self._stt_loop(), name="stt")
            idle_task = asyncio.create_task(self._idle_watchdog(), name="idle")

            done, pending = await asyncio.wait(
                [rx_task, stt_task, idle_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # One task finished (hangup, error, or idle timeout) — cancel rest
            for t in pending:
                t.cancel()
            # Propagate any exception (not CancelledError)
            for t in done:
                exc = t.exception()
                if exc and not isinstance(exc, asyncio.CancelledError):
                    self._log.error("session_task_error", detail=str(exc))

        except Exception:
            self._log.exception("session_fatal")
        finally:
            await self._cleanup()
            self._log.info("session_end", session_id=self._session_id)

    # ── RX loop: read AudioSocket frames from Asterisk ────────────────────────

    async def _rx_loop(self) -> None:
        frame_count = 0
        while True:
            try:
                ftype, payload = await proto.read_frame(self._reader)
            except asyncio.IncompleteReadError:
                self._log.info("rx_eof", frames_received=frame_count)
                return

            frame_count += 1
            if frame_count <= 5 or frame_count % 100 == 0:
                self._log.debug("rx_frame", ftype=hex(ftype), payload_len=len(payload), count=frame_count)

            if ftype == proto.HANGUP:
                self._log.info("rx_hangup", frames_received=frame_count)
                return

            elif ftype == proto.AUDIO:
                self._last_activity = time.monotonic()

                if self._state == State.IDLE:
                    # First audio: open STT, send greeting
                    await self._transition_to_listening()
                    asyncio.create_task(self._greet(), name="greet")

                if self._state in (State.LISTENING, State.BARGE_IN):
                    try:
                        self._audio_queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block

            elif ftype == proto.ERROR:
                self._log.error("rx_asterisk_error",
                                detail=payload.decode(errors="replace"))

    # ── STT loop: drain audio_queue → Deepgram ────────────────────────────────

    async def _stt_loop(self) -> None:
        # Wait until STT is initialised (by _transition_to_listening)
        while self._stt is None:
            await asyncio.sleep(0.02)
        while True:
            try:
                audio = await asyncio.wait_for(self._audio_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if self._hangup_event.is_set():
                    return
                continue
            await self._stt.send(audio)

    # ── Idle watchdog ─────────────────────────────────────────────────────────

    async def _idle_watchdog(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            if time.monotonic() - self._last_activity > _IDLE_TIMEOUT:
                self._log.info("session_idle_timeout")
                return

    # ── State transitions ─────────────────────────────────────────────────────

    async def _transition_to_listening(self) -> None:
        self._state = State.LISTENING
        self._stt = StreamingSTT(
            api_key         = _DEEPGRAM_API_KEY,
            log             = self._log,
            on_speech_start = self._on_speech_start,
            on_utterance_end = self._on_utterance_end,
        )
        await self._stt.connect()
        self._log.info("state", state="LISTENING")

    async def _on_speech_start(self) -> None:
        self._last_activity = time.monotonic()
        if self._state == State.SPEAKING and self._speak_task:
            self._log.info("barge_in")
            self._state = State.BARGE_IN
            self._speak_task.cancel()
        elif self._state in (State.LISTENING, State.BARGE_IN):
            pass  # normal start-of-speech

    async def _on_utterance_end(self, transcript: str) -> None:
        self._last_activity = time.monotonic()
        if self._state not in (State.LISTENING, State.BARGE_IN):
            # double-fire guard
            self._log.debug("utterance_end_dropped", state=self._state.name)
            return

        self._state = State.PROCESSING
        self._log.info("state", state="PROCESSING", transcript=transcript)

        self._speak_task = asyncio.create_task(
            self._respond(transcript), name="speak"
        )

    # ── Greeting ──────────────────────────────────────────────────────────────

    async def _greet(self) -> None:
        greeting = await self._brain_call("[call_connected]")
        await self._play_text(greeting or "Hello! How can I help you today?")
        if self._state == State.SPEAKING:
            self._state = State.LISTENING
            self._log.info("state", state="LISTENING")

    # ── Respond to a user utterance ───────────────────────────────────────────

    async def _respond(self, transcript: str) -> None:
        t0 = time.monotonic()
        try:
            response_text = await self._brain_call(transcript)
            llm_ms = int((time.monotonic() - t0) * 1000)

            t1 = time.monotonic()
            await self._play_text(response_text or "Sorry, I didn't catch that.")
            tts_ms = int((time.monotonic() - t1) * 1000)

            self._log.info("turn_complete",
                           transcript=transcript,
                           response=response_text,
                           llm_ms=llm_ms,
                           tts_ms=tts_ms,
                           total_ms=int((time.monotonic() - t0) * 1000))
        except asyncio.CancelledError:
            self._log.info("respond_cancelled")
            raise
        except Exception:
            self._log.exception("respond_error")
            await self._play_text("I'm sorry, something went wrong. Please try again.")
        finally:
            if self._state in (State.SPEAKING, State.PROCESSING):
                self._state = State.LISTENING
                self._log.info("state", state="LISTENING")

    # ── Brain call: delegate to ai-server POST /chat ──────────────────────────

    async def _brain_call(self, text: str) -> str:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{_BRAIN_URL}/chat",
                json={"text": text, "session_id": self._session_id, "channel": "phone"},
            )
            r.raise_for_status()
            return r.json().get("response", "")

    # ── TTS → AudioSocket ─────────────────────────────────────────────────────

    async def _play_text(self, text: str) -> None:
        """Stream TTS audio for *text* back to Asterisk via AudioSocket."""
        if not text.strip():
            return

        self._state = State.SPEAKING
        self._log.info("state", state="SPEAKING", text_len=len(text))

        try:
            buf = bytearray()
            async for pcm_chunk in self._tts.synthesize_stream(text):
                buf.extend(pcm_chunk)
                # Drain any full 320-byte frames immediately
                while len(buf) >= proto.FRAME_BYTES:
                    frame_data = bytes(buf[:proto.FRAME_BYTES])
                    del buf[:proto.FRAME_BYTES]
                    self._writer.write(proto.build_frame(proto.AUDIO, frame_data))
                    await self._writer.drain()
            # Flush remainder
            if buf:
                padded = bytes(buf) + b"\x00" * (proto.FRAME_BYTES - len(buf))
                self._writer.write(proto.build_frame(proto.AUDIO, padded))
                await self._writer.drain()
        except asyncio.CancelledError:
            self._log.info("tts_cancelled")
            raise

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def _cleanup(self) -> None:
        if self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()
        if self._stt:
            try:
                await asyncio.wait_for(self._stt.finish(), timeout=3.0)
            except Exception:
                pass
        try:
            self._writer.close()
            await asyncio.wait_for(self._writer.wait_closed(), timeout=3.0)
        except Exception:
            pass
