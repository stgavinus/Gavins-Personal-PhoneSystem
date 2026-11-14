"""
Streaming STT via Deepgram WebSocket (nova-3 model).

This module wraps the Deepgram SDK's async live-transcription client and
translates its events into the four turn-detection signals the session state
machine needs:

    on_speech_start  — user started speaking  (→ BARGE_IN when SPEAKING)
    on_partial       — interim transcript (informational, not acted on)
    on_utterance_end — user finished speaking  (→ trigger LLM response)

The session feeds raw slin16 audio by calling send(audio_bytes).
Call finish() when the call ends to close the WebSocket cleanly.

Turn detection is approximated with:
  speech_final=True  transcripts  →  confident end-of-utterance detected by DG
  utterance_end_ms=1000           →  fallback: 1 s silence after speech_final
Both fire on_utterance_end to the state machine.  The state machine deduplicates.
"""
import asyncio
from collections.abc import Callable, Awaitable
from typing import Optional

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

from bridge.log import BoundLogger

# Deepgram model — nova-3 for best accuracy; swap to "nova-2" if quota issues
_MODEL = "nova-3"

# Milliseconds of silence after the last speech_final before firing UtteranceEnd
_UTTERANCE_END_MS = "1000"


class StreamingSTT:
    """
    One STT session per phone call.

    Callbacks are async callables accepting keyword arguments (see below).
    All callbacks are awaited on the event-loop that called connect().
    """

    def __init__(
        self,
        api_key: str,
        log: BoundLogger,
        on_speech_start: Callable[[], Awaitable[None]],
        on_utterance_end: Callable[[str], Awaitable[None]],
        on_partial: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        self._api_key         = api_key
        self._log             = log
        self._on_speech_start = on_speech_start
        self._on_utterance_end = on_utterance_end
        self._on_partial      = on_partial
        self._conn            = None
        self._loop            = None
        self._transcript_buf  = ""   # accumulate speech_final segments

    # ── Public interface ──────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open the WebSocket. Must be called before send()."""
        self._loop = asyncio.get_running_loop()

        opts = DeepgramClientOptions(options={"keepalive": "true"})
        client = DeepgramClient(self._api_key, opts)
        self._conn = client.listen.asyncwebsocket.v("1")

        self._conn.on(LiveTranscriptionEvents.Open,         self._on_open)
        self._conn.on(LiveTranscriptionEvents.Transcript,   self._on_transcript)
        self._conn.on(LiveTranscriptionEvents.SpeechStarted, self._on_speech_started)
        self._conn.on(LiveTranscriptionEvents.UtteranceEnd, self._on_utterance_end_event)
        self._conn.on(LiveTranscriptionEvents.Error,        self._on_error)
        self._conn.on(LiveTranscriptionEvents.Close,        self._on_close)

        options = LiveOptions(
            model           = _MODEL,
            encoding        = "linear16",
            sample_rate     = 8000,
            channels        = 1,
            language        = "en-US",
            smart_format    = True,
            interim_results = True,
            utterance_end_ms = _UTTERANCE_END_MS,
            vad_events      = True,
        )
        started = await self._conn.start(options)
        if not started:
            raise RuntimeError("Deepgram WebSocket failed to start")
        self._log.info("stt_connected", model=_MODEL)

    async def send(self, audio: bytes) -> None:
        """Forward a raw slin16 chunk to Deepgram."""
        if self._conn:
            await self._conn.send(audio)

    async def finish(self) -> None:
        """Flush and close the WebSocket."""
        if self._conn:
            await self._conn.finish()
            self._log.info("stt_closed")

    # ── Deepgram event handlers ───────────────────────────────────────────────

    async def _on_open(self, *_, **__) -> None:
        self._log.debug("stt_open")

    async def _on_speech_started(self, *_, **__) -> None:
        self._log.debug("stt_speech_started")
        await self._on_speech_start()

    async def _on_transcript(self, *_, result=None, **__) -> None:
        if result is None:
            return
        try:
            alt = result.channel.alternatives[0]
            text = alt.transcript.strip()
        except (AttributeError, IndexError):
            return

        if not text:
            return

        is_final       = result.is_final
        speech_final   = result.speech_final

        if not is_final:
            if self._on_partial:
                await self._on_partial(text)
            return

        # Accumulate final segments into the current utterance
        self._transcript_buf += (" " if self._transcript_buf else "") + text

        if speech_final:
            # Deepgram is confident the user has finished speaking
            utterance = self._transcript_buf.strip()
            self._transcript_buf = ""
            self._log.info("stt_speech_final", transcript=utterance)
            await self._on_utterance_end(utterance)

    async def _on_utterance_end_event(self, *_, utterance_end=None, **__) -> None:
        # Fires after utterance_end_ms of silence post speech_final.
        # If speech_final already fired we may have already responded —
        # the state machine guards against double-firing.
        leftover = self._transcript_buf.strip()
        self._transcript_buf = ""
        if leftover:
            self._log.info("stt_utterance_end_fallback", transcript=leftover)
            await self._on_utterance_end(leftover)
        else:
            self._log.debug("stt_utterance_end_empty")

    async def _on_error(self, *_, error=None, **__) -> None:
        self._log.error("stt_error", detail=str(error))

    async def _on_close(self, *_, **__) -> None:
        self._log.debug("stt_ws_closed")
