from dataclasses import dataclass
from typing import List, Optional
from pydantic import BaseModel


@dataclass
class AvailabilityResult:
    """Type-safe result for availability checks."""
    status: str 
    message: str
    available_slots: List[str]
    checked_time: Optional[str] = None
    checked_date: Optional[str] = None


class AvailabilityResponse(BaseModel):
    """Response for availability check API."""
    date: str
    time: Optional[str] = None
    available: bool = True
    available_slots: Optional[List[str]] = None
    current_bookings: int = 0
    max_per_slot: int = 2
