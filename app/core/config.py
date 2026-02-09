import os
import json
from typing import Optional, Dict, Any, List
from functools import lru_cache
from pydantic_settings import BaseSettings


BUSINESS_HOURS: List[str] = [
    "9:00 AM", "10:00 AM", "11:00 AM",
    "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM"
]

MAX_BOOKINGS_PER_SLOT: int = 2


class SalonDataLoader:
    """Centralized loader for salon information from data/info.json."""
    
    _data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def _get_data_path(cls) -> str:
        """Get path to info.json data file."""
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", "info.json")
        if os.path.exists(data_path):
            return data_path
        fallback_path = "app/json/info.json"
        if os.path.exists(fallback_path):
            return fallback_path
        raise FileNotFoundError("Salon info.json not found in data/ or json/ directories")
    
    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> Dict[str, Any]:
        """Load and cache salon data. Thread-safe via lru_cache."""
        with open(cls._get_data_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    
    @classmethod
    def get_name(cls) -> str:
        return cls.load().get("name", "")
    
    @classmethod
    def get_address(cls) -> str:
        return cls.load().get("address", "")
    
    @classmethod
    def get_contact(cls) -> str:
        return cls.load().get("contact", "")
    
    @classmethod
    def get_working_hours(cls) -> Dict[str, str]:
        return cls.load().get("working_hours", {})
    
    @classmethod
    def get_services(cls) -> Dict[str, int]:
        return cls.load().get("services", {})
    
    @classmethod
    def get_faqs(cls) -> List[Dict[str, str]]:
        return cls.load().get("faqs", [])


class Settings(BaseSettings):
    """Global AI + system configuration."""
    
    stt: str = "whisper-large-v3-turbo"
    llm: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    tts: str = "cartesia"
    
    # API Keys
    qdrant_api_key: Optional[str] = None
    qdrant_url: Optional[str] = None
    livekit_url: Optional[str] = None
    livekit_api_key: Optional[str] = None
    livekit_api_secret: Optional[str] = None
    google_api_key: Optional[str] = None
    stt_api_key: Optional[str] = None
    tts_provider: Optional[str] = None
    groq_api_key: Optional[str] = None
    
    # Backend
    backend_url: str = "http://localhost:8000"
    
    model_config = {"env_file": ".env", "extra": "ignore"}


class BookingSettings(BaseSettings):
    """Booking-related configuration."""
    collection_name: str = "appointments"
    
    model_config = {"extra": "ignore"}


class HelpSettings(BaseSettings):
    """Help request configuration."""
    collection_name: str = "help_requests"
    
    model_config = {"extra": "ignore"}


class KnowledgeSettings(BaseSettings):
    """Knowledge base configuration."""
    collection_name: str = "knowledge_base"
    
    model_config = {"extra": "ignore"}


settings = Settings()
booking_settings = BookingSettings()
help_settings = HelpSettings()
knowledge_settings = KnowledgeSettings()

