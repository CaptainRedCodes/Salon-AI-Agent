from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.booking import BookingContext

class SalonUserData(BaseModel):
    """User session data with booking context tracking"""
    current_booking: BookingContext = Field(default_factory=BookingContext)
    conversation_state: str = "greeting"  # greeting, inquiry, booking, confirming, completed
    previous_queries: List[Dict[str, str]] = Field(default_factory=list)
    availability_checks: List[Dict[str, str]] = Field(default_factory=list)

    waiting_for_confirmation: bool = False
    last_tool_called: Optional[str] = None
    last_tool_result: Optional[Any] = None

    validation_errors: List[str] = Field(default_factory=list)
    retry_count: int = 0

    def reset_booking(self):
        """Reset the current booking context"""
        self.current_booking = BookingContext()
        self.waiting_for_confirmation = False
        self.validation_errors = []
        self.retry_count = 0

    def add_query(self, query: str):
        """Track customer queries"""
        self.previous_queries.append({
            "query": query,
            "timestamp": datetime.now().isoformat()
        })
        if len(self.previous_queries) > 10:
            self.previous_queries.pop(0)

class AvailabilityCheckPayload(BaseModel):
    date: str = Field(..., description="Date to check, e.g., 'January 15, 2025'")
    time: Optional[str] = Field(None, description="Optional time to check, e.g., '2:00 PM'")