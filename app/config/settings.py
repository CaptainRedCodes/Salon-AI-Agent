from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global AI + system configuration"""

    stt: str = "assemblyai/universal-streaming:en"
    llm: str = "google/gemini-2.0-flash"
    tts: str = "cartesia"

    class Config:
        env_file = ".env"


class BookingSettings(BaseSettings):
    """Booking collection and related config"""
    collection_name: str = "appointments"


class HelpSettings(BaseSettings):
    """Help requests collection and related config"""
    collection_name: str = "help_requests"

class KnowledgeSettings(BaseSettings):
    """ KnowledgeBase settings and related config"""
    logs_collection = "help_logs"
    qdrant_collection = "knowledge_base"
    refresh_interval = 1800


settings = Settings()
booking_settings = BookingSettings()
help_settings = HelpSettings()
knowledge_settings = KnowledgeSettings()