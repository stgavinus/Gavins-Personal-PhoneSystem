"""
Deepgram TTS — streaming PCM output.

Requests raw linear16 PCM at 8 kHz (matching Asterisk's slin16 format)
so the bytes can be written directly into AudioSocket audio frames without
any transcoding.

synthesize_stream() returns an async generator of raw PCM bytes chunks.
Each chunk may be any size; the caller (session.py) is responsible for
slicing into FRAME_BYTES pieces before writing to AudioSocket.

If Deepgram TTS does not support 8 kHz for the chosen voice the response
content-type will indicate an error or the audio will be silent.  The
resampling fallback (audioop) is available but not enabled by default —
enable it via RESAMPLE_FROM_HZ if needed.
"""
import audioop
from collections.abc import AsyncIterator

import httpx

from bridge.log import BoundLogger

_TTS_URL       = "https://api.deepgram.com/v1/speak"
_DEFAULT_VOICE = "aura-asteria-en"
_TARGET_HZ     = 8_000
# Set to the sample rate Deepgram actually returns if it refuses 8 kHz.
# 0 means "request 8 kHz directly and trust the response".
RESAMPLE_FROM_HZ: int = 0


class StreamingTTS:
    def __init__(self, api_key: str, log: BoundLogger, voice: str = _DEFAULT_VOICE) -> None:
        self._api_key = api_key
        self._log     = log
        self._voice   = voice

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """
        Yield raw slin16 PCM chunks for *text*.

        Each yielded bytes object is variable-length raw PCM.
        The caller must split into FRAME_BYTES (320-byte) chunks.
        """
        params = {
            "model":       self._voice,
            "encoding":    "linear16",
            "sample_rate": _TARGET_HZ if not RESAMPLE_FROM_HZ else RESAMPLE_FROM_HZ,
            "container":   "none",   # no WAV header — raw PCM only
        }
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type":  "application/json",
        }

        self._log.debug("tts_request", chars=len(text), voice=self._voice)

        resample_state = None  # audioop.ratecv state — only used when RESAMPLE_FROM_HZ != 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                _TTS_URL,
                params  = params,
                headers = headers,
                json    = {"text": text},
            ) as response:
                if not response.is_success:
                    body = await response.aread()
                    raise RuntimeError(
                        f"Deepgram TTS error {response.status_code}: "
                        f"{body[:200].decode(errors='replace')}"
                    )

                async for chunk in response.aiter_bytes(chunk_size=640):
                    if not chunk:
                        continue
                    if RESAMPLE_FROM_HZ and RESAMPLE_FROM_HZ != _TARGET_HZ:
                        chunk, resample_state = audioop.ratecv(
                            chunk, 2, 1, RESAMPLE_FROM_HZ, _TARGET_HZ, resample_state
                        )
                    yield chunk

        self._log.debug("tts_done", chars=len(text))
