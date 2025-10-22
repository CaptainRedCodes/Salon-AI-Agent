import asyncio
from datetime import datetime, timezone
import logging
from typing import List

from app.config.settings import booking_settings
from app.db import FirebaseManager
from app.models.booking import BookingCreate, BookingView


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BookingManager:
    """Manages appointment bookings in Firebase."""
    
    def __init__(self):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection_name = booking_settings.collection_name
    
    async def create_booking(self, booking_data: BookingCreate) -> BookingView:
        """Create a new appointment booking."""
        try:
            timestamp = datetime.now(timezone.utc)
            loop = asyncio.get_event_loop()
            
            def _create():
                timestamp_part = int(timestamp.timestamp() * 1000) % 100000
                confirmation_number = f"SA{timestamp_part}"
                
                booking_dict = booking_data.model_dump()
                booking_dict.update({
                    "confirmation_number": confirmation_number,
                    "status": "confirmed",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "cancelled": False,
                    "cancellation_reason": None
                })
                
                doc_ref = self.db.collection(self.collection_name).document()
                doc_ref.set(booking_dict)
                booking_dict["id"] = doc_ref.id

                logger.info(f"Booking created: {confirmation_number} for {booking_data.customer_name}")
                return booking_dict
            
            booking = await loop.run_in_executor(None, _create)
            logger.info(f"Booking created: {booking['confirmation_number']} for {booking['customer_name']}")
            return BookingView(**booking)
            
        except Exception as e:
            logger.error(f"Failed to create booking: {e}")
            raise
    
    async def get_bookings_by_date(self, date: str) -> List[BookingView]:
        """Get all bookings for a specific date."""
        loop = asyncio.get_event_loop()
        
        def _query():
            docs = self.db.collection(self.collection_name).where(
                "appointment_date", "==", date
            ).stream()
            return [BookingView(**doc.to_dict()) for doc in docs]

        return await loop.run_in_executor(None, _query)