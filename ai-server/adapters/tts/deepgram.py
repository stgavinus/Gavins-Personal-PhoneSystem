import httpx
from .base import TTSAdapter


class DeepgramTTSAdapter(TTSAdapter):
    def __init__(self, api_key: str, voice: str = "aura-asteria-en"):
        self.api_key = api_key
        self.voice = voice

    async def synthesize(self, text: str, output_path: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.deepgram.com/v1/speak",
                params={"model": self.voice},
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            )
            if not r.is_success:
                raise RuntimeError(f"Deepgram TTS error: {r.status_code} {r.text[:200]}")
            with open(output_path, "wb") as f:
                f.write(r.content)
        return output_path
