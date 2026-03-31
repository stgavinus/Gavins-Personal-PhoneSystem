from deepgram import DeepgramClient, PrerecordedOptions
from .base import STTAdapter


class DeepgramAdapter(STTAdapter):
    def __init__(self, api_key: str):
        self._client = DeepgramClient(api_key)

    async def transcribe(self, audio_path: str) -> str:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        options = PrerecordedOptions(model="nova-2", language="en")
        response = self._client.listen.prerecorded.v("1").transcribe_file(
            {"buffer": audio_data, "mimetype": "audio/wav"},
            options,
        )
        return response.results.channels[0].alternatives[0].transcript.strip()
