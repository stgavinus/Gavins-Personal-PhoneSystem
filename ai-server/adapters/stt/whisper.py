import asyncio
from faster_whisper import WhisperModel
from .base import STTAdapter


class WhisperAdapter(STTAdapter):
    def __init__(self, model_size: str = "tiny"):
        # Runs on CPU in Docker; use "cuda" device if GPU available
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    async def transcribe(self, audio_path: str) -> str:
        loop = asyncio.get_event_loop()
        # Run blocking whisper call in a thread so we don't block the event loop
        segments, _ = await loop.run_in_executor(
            None, lambda: self._model.transcribe(audio_path, language="en")
        )
        return " ".join(s.text.strip() for s in segments).strip()
