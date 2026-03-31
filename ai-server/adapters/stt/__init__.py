from .base import STTAdapter


def get_stt_adapter() -> STTAdapter:
    from config import settings
    if settings.stt_provider == "deepgram":
        from .deepgram import DeepgramAdapter
        return DeepgramAdapter(api_key=settings.deepgram_api_key)
    else:
        from .whisper import WhisperAdapter
        return WhisperAdapter(model_size=settings.whisper_model)
