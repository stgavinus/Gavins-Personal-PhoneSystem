from .base import LLMAdapter


def get_llm_adapter() -> LLMAdapter:
    from config import settings
    if settings.llm_provider == "gemini":
        from .gemini import GeminiAdapter
        return GeminiAdapter(api_key=settings.gemini_api_key, model=settings.gemini_model)
    elif settings.llm_provider == "groq":
        from .groq import GroqAdapter
        return GroqAdapter(api_key=settings.groq_api_key, model=settings.groq_model)
    else:
        from .ollama import OllamaAdapter
        return OllamaAdapter(url=settings.ollama_url, model=settings.ollama_model)
