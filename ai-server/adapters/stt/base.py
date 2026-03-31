from abc import ABC, abstractmethod


class STTAdapter(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> str:
        """Transcribe audio file at audio_path, return text."""
