from abc import ABC, abstractmethod


class TTSAdapter(ABC):
    @abstractmethod
    async def synthesize(self, text: str, output_path: str) -> str:
        """Convert text to speech, write WAV to output_path, return output_path."""
