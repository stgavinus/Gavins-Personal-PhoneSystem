import asyncio
import subprocess
from pathlib import Path
from .base import TTSAdapter


class PiperAdapter(TTSAdapter):
    def __init__(self, voice: str = "en_US-lessac-medium", models_dir: str = "/app/models"):
        self.voice = voice
        self.model_path = Path(models_dir) / f"{voice}.onnx"
        self.piper_bin = "/opt/piper/piper"

    async def synthesize(self, text: str, output_path: str) -> str:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_piper, text, output_path)
        return output_path

    def _run_piper(self, text: str, output_path: str) -> None:
        subprocess.run(
            [
                self.piper_bin,
                "--model", str(self.model_path),
                "--output_file", output_path,
            ],
            input=text.encode(),
            check=True,
            capture_output=True,
        )
