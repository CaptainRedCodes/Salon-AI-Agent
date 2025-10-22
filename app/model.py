from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class HelpRequestStatus(Enum):
    """Status states for help requests."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    
class HelpRequestCreate(BaseModel):
    reason: str
    room_name: Optional[str] = None
    customer_context: Optional[Dict[str, Any]] = None

class SupervisorResponse(BaseModel):
    request_id: str
    answer: str
    resolution_notes: Optional[str] = None
    add_to_knowledge_base: bool = Field(default=True, description="Whether to add this to KB")

class HelpRequestView(BaseModel):
    id: str
    reason: str
    status: str
    room_name: Optional[str]
    customer_context: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    resolution_notes: Optional[str] = None
    answer: Optional[str] = None
    response_time_seconds: Optional[float] = None




@dataclass
class BookingContext:
    """Context for current booking in progress"""
    customer_name: Optional[str] = None
    phone_number: Optional[str] = None
    service: Optional[str] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    price: Optional[float] = None
    confirmed: bool = False
    
    def is_complete(self) -> bool:
        """Check if all required fields are present"""
        return all([
            self.customer_name,
            self.phone_number,
            self.service,
            self.appointment_date,
            self.appointment_time
        ])
    
    def get_summary(self) -> str:
        """Get a summary of the current booking"""
        if not self.is_complete():
            return "Incomplete booking information"
        
        return (
            f"Customer: {self.customer_name}\n"
            f"Phone: {self.phone_number}\n"
            f"Service: {self.service}\n"
            f"Date: {self.appointment_date}\n"
            f"Time: {self.appointment_time}\n"
            f"Price: ₹{self.price}"
        )

@dataclass
class SalonUserData:
    """User session data with context tracking"""
   
    current_booking: BookingContext = field(default_factory=BookingContext)
    conversation_state: str = "greeting"  # greeting, inquiry, booking, confirming, completed
    previous_queries: List[Dict[str, str]] = field(default_factory=list)
    availability_checks: List[Dict[str, str]] = field(default_factory=list)
    
    waiting_for_confirmation: bool = False
    last_tool_called: Optional[str] = None
    last_tool_result: Optional[Any] = None
    
    validation_errors: List[str] = field(default_factory=list)
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