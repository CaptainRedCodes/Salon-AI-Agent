# Configure logging
import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List

from db import FirebaseManager


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
        self.collection_name = "appointments"
    
    async def create_booking(
        self,
        customer_name: str,
        service: str,
        appointment_date: str,
        appointment_time: str,
        price: float,
        phone_number: str = ""
    ) -> Dict[str, Any]:
        """Create a new appointment booking."""
        try:
            timestamp = datetime.now(timezone.utc)
            loop = asyncio.get_event_loop()
            
            def _create():
                # Generate confirmation number using timestamp-based approach
                # This is more reliable than counting documents
                timestamp_part = int(timestamp.timestamp() * 1000) % 100000
                confirmation_number = f"SA{timestamp_part}"
                
                booking = {
                    "confirmation_number": confirmation_number,
                    "customer_name": customer_name,
                    "service": service,
                    "appointment_date": appointment_date,
                    "appointment_time": appointment_time,
                    "phone_number": phone_number,
                    "price": price,
                    "status": "confirmed",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "cancelled": False,
                    "cancellation_reason": None
                }
                
                doc_ref = self.db.collection(self.collection_name).document()
                doc_ref.set(booking)
                
                booking["id"] = doc_ref.id
                logger.info(f"Booking created: {confirmation_number} for {customer_name}")
            
                return booking
            
            booking = await loop.run_in_executor(None, _create)
            logger.info(f"Booking created: {booking['confirmation_number']} for {booking['customer_name']}")
            return booking
            
        except Exception as e:
            logger.error(f"Failed to create booking: {e}")
            raise
    
    async def get_bookings_by_date(self, date: str) -> List[Dict[str, Any]]:
        """Get all bookings for a specific date."""
        loop = asyncio.get_event_loop()
        
        def _query():
            docs = self.db.collection(self.collection_name).where(
                "appointment_date", "==", date
            ).stream()
            return [doc.to_dict() for doc in docs]

        return await loop.run_in_executor(None, _query)