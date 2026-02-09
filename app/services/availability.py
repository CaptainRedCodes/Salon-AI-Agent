from typing import Dict, List, Optional

from app.core.logging_config import get_logger
from app.models.availability import AvailabilityResult
from app.core.database import FirebaseManager
from app.core.config import booking_settings, BUSINESS_HOURS, MAX_BOOKINGS_PER_SLOT

logger = get_logger(__name__)


class AvailabilityService:
    """Handles availability checking logic with type safety."""
    
    def __init__(self):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection = booking_settings.collection_name
    
    def _get_slot_counts(self, date: str) -> Dict[str, int]:
        """Get booking counts for each slot on a given date."""
        try:
            bookings_ref = self.db.collection(self.collection)\
                .where("appointment_date", "==", date)
            bookings = bookings_ref.stream()
            slot_counts: Dict[str, int] = {slot: 0 for slot in BUSINESS_HOURS}
            
            for doc in bookings:
                data = doc.to_dict()
                slot_time = data.get("appointment_time")
                if slot_time and slot_time in slot_counts:
                    slot_counts[slot_time] += 1
            
            return slot_counts
            
        except Exception as e:
            logger.error(f"Error fetching slot counts: {e}")
            return {slot: 0 for slot in BUSINESS_HOURS}
    
    def _get_available_slots(self, slot_counts: Dict[str, int]) -> List[str]:
        """Get list of available slots based on counts."""
        return [
            slot for slot, count in slot_counts.items() 
            if count < MAX_BOOKINGS_PER_SLOT
        ]
    
    def _format_available_slots(self, slots: List[str]) -> str:
        """Format available slots for display."""
        if not slots:
            return "No slots available"
        return "\n".join(f"• {slot}" for slot in slots)
    
    def check_availability(self, date: str, time: Optional[str] = None) -> AvailabilityResult:
        """
        Check slot availability for a given date and optionally time.
        
        Args:
            date: Date in format "YYYY-MM-DD"
            time: Optional specific time slot (e.g., "10:00 AM")
        
        Returns:
            AvailabilityResult with status and message
        """
        try:
            slot_counts = self._get_slot_counts(date)
            available_slots = self._get_available_slots(slot_counts)
            
            if time:
                return self._check_specific_time(
                    date, time, slot_counts, available_slots
                )
            
            return self._check_all_slots(date, available_slots)
            
        except Exception as e:
            logger.error(f"Availability check failed: {e}")
            return AvailabilityResult(
                status="error",
                message="I'm having trouble checking availability. Let me get help from my supervisor.",
                available_slots=[],
                checked_date=date,
                checked_time=time
            )
    
    def _check_specific_time(
        self,
        date: str,
        time: str,
        slot_counts: Dict[str, int],
        available_slots: List[str]
    ) -> AvailabilityResult:
        """Check availability for a specific time slot."""
        
        if time not in BUSINESS_HOURS:
            return AvailabilityResult(
                status="invalid_time",
                message=(
                    f"{time} is outside our business hours.\n"
                    f"Available times: {', '.join(BUSINESS_HOURS)}"
                ),
                available_slots=BUSINESS_HOURS,
                checked_date=date,
                checked_time=time
            )
        
        current_bookings = slot_counts.get(time, 0)
        
        if current_bookings < MAX_BOOKINGS_PER_SLOT:
            return AvailabilityResult(
                status="available",
                message=f"{time} on {date} is available!",
                available_slots=[time],
                checked_date=date,
                checked_time=time
            )
        
        # Offer alternatives
        if available_slots:
            alternatives = self._format_available_slots(available_slots)
            return AvailabilityResult(
                status="booked",
                message=(
                    f"{time} is fully booked.\n\n"
                    f"Available slots on {date}:\n{alternatives}"
                ),
                available_slots=available_slots,
                checked_date=date,
                checked_time=time
            )
        
        return AvailabilityResult(
            status="all_booked",
            message=f"All slots on {date} are fully booked.",
            available_slots=[],
            checked_date=date,
            checked_time=time
        )
    
    def _check_all_slots(self, date: str, available_slots: List[str]) -> AvailabilityResult:
        """Check availability for all slots on a date."""
        
        if available_slots:
            slots_formatted = self._format_available_slots(available_slots)
            return AvailabilityResult(
                status="available",
                message=f"Available times on {date}:\n{slots_formatted}",
                available_slots=available_slots,
                checked_date=date
            )
        
        return AvailabilityResult(
            status="all_booked",
            message=(
                f"Unfortunately, we're fully booked on {date}.\n"
                f"Would you like to check another date?"
            ),
            available_slots=[],
            checked_date=date
        )
