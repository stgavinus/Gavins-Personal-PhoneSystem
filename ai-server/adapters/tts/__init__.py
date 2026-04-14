from .base import TTSAdapter


def get_tts_adapter() -> TTSAdapter:
    from config import settings
    if settings.tts_provider == "deepgram":
        from .deepgram import DeepgramTTSAdapter
        return DeepgramTTSAdapter(api_key=settings.deepgram_api_key, voice=settings.tts_deepgram_voice)
    else:
        from .piper import PiperAdapter
        return PiperAdapter(voice=settings.piper_voice)
