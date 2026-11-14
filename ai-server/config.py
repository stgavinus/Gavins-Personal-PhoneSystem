from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # VM / Asterisk
    vm_tailscale_ip: str = ""
    vm_ssh_user: str = ""
    vm_ssh_key: str = ""
    wakeup_extension: str = "101"

    # AI server
    ai_server_host: str = "0.0.0.0"
    ai_server_port: int = 8000
    ai_server_api_key: str = "changeme"

    # LLM
    llm_provider: str = "ollama"
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # STT
    stt_provider: str = "whisper"
    whisper_model: str = "tiny"
    deepgram_api_key: str = ""

    # TTS
    tts_provider: str = "deepgram"
    piper_voice: str = "en_US-lessac-medium"
    tts_deepgram_voice: str = "aura-asteria-en"

    # Asterisk AMI
    ami_host: str = "asterisk"
    ami_port: int = 5038
    ami_user: str = "aiserver"
    ami_secret: str = ""

    # Wake-up
    wakeup_retry_interval: int = 180
    wakeup_max_retries: int = 20

    # Brain
    brain_gemini_model: str = "gemini-3.1-flash-lite-preview"

    # Web UI
    web_username: str = "admin"
    web_password: str = "changeme"

    class Config:
        env_file = ".env"


settings = Settings()
