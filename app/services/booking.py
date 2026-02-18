import asyncio
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import HTTPException

from app.core.logging_config import get_logger
from app.core.database import FirebaseManager
from app.core.config import booking_settings,MAX_BOOKINGS_PER_SLOT,BUSINESS_HOURS
from app.models.booking import BookingResponse

logger = get_logger(__name__)


class BookingService:
    """Manages all booking operations in Firebase."""
    
    def __init__(self):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection = booking_settings.collection_name
    
    async def _run(self, func):
        """
        Run a blocking (synchronous) function in a separate thread
        so that the FastAPI async event loop does not get blocked.

        Why this is needed:
        -------------------
        FastAPI runs on an async event loop. The event loop must stay
        free to handle multiple requests concurrently.

        However, some operations (like Firestore queries, database calls,
        file I/O, etc.) are synchronous and blocking. If we execute them
        directly inside an async function, they will pause the entire
        event loop until they finish. This reduces performance and
        prevents other requests from being handled.

        What this function does:
        ------------------------
        1. Gets the currently running asyncio event loop.
        2. Submits the blocking function (`func`) to a thread pool executor.
        3. The blocking function runs in a separate thread.
        4. Meanwhile, the event loop remains free to handle other requests.
        5. Once the thread completes, we await and return the result.

        In simple terms:
        ----------------
        Instead of blocking the async server, we offload the heavy work
        to a background worker thread and wait for the result safely.

        This keeps the API fast and scalable.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)

    
    async def create(self, data) -> BookingResponse:
        """
        Create a new booking with conflict prevention.
        Raises 409 if slot is full.
        """
        def _create():
            # Check slot availability first
            bookings_ref = self.db.collection(self.collection)
            existing = bookings_ref.where("appointment_date", "==", data.appointment_date)\
                                   .where("appointment_time", "==", data.appointment_time)\
                                   .where("cancelled", "==", False)\
                                   .stream()
            
            count = sum(1 for _ in existing)
            
            if count >= MAX_BOOKINGS_PER_SLOT:
                raise HTTPException(
                    status_code=409,
                    detail=f"Sorry, {data.appointment_time} on {data.appointment_date} is fully booked. Please choose another time."
                )
            
            # Create booking
            confirmation_number = f"SA{uuid4().hex[:6].upper()}"
            now = datetime.now()
            
            booking_data = {
                "confirmation_number": confirmation_number,
                "customer_name": data.customer_name,
                "phone_number": data.phone_number,
                "service": data.service,
                "appointment_date": data.appointment_date,
                "appointment_time": data.appointment_time,
                "price": data.price,
                "status": "confirmed",
                "created_at": now,
                "cancelled": False,
            }
            
            doc_ref = self.db.collection(self.collection).add(booking_data)
            doc_id = doc_ref[1].id
            
            logger.info(f"Booking created: {confirmation_number} for {data.customer_name}")
            
            return BookingResponse(
                id=doc_id,
                **booking_data
            )
        
        return await self._run(_create)
    
    async def list_all(self, date: Optional[str] = None, limit: int = 50) -> List[dict]:
        """Get bookings, optionally filtered by date."""
        def _query():
            ref = self.db.collection(self.collection)
            if date:
                ref = ref.where("appointment_date", "==", date)
            docs = ref.limit(limit).stream()
            return [{"id": doc.id, **doc.to_dict()} for doc in docs]
        
        return await self._run(_query)
    
    async def check_availability(self, date: str, time: Optional[str] = None):
        """Check which slots are available on a date."""
        def _check():
            bookings_ref = self.db.collection(self.collection)
            existing = bookings_ref.where("appointment_date", "==", date)\
                                   .where("cancelled", "==", False)\
                                   .stream()
            
            # Count bookings per slot
            slot_counts = {slot: 0 for slot in BUSINESS_HOURS}
            for doc in existing:
                data = doc.to_dict()
                slot = data.get("appointment_time")
                if slot in slot_counts:
                    slot_counts[slot] += 1
            
            available_slots = [
                slot for slot, count in slot_counts.items()
                if count < MAX_BOOKINGS_PER_SLOT
            ]
            
            if time:
                # Check specific time
                current_count = slot_counts.get(time, 0)
                return {
                    "date": date,
                    "time": time,
                    "available": current_count < MAX_BOOKINGS_PER_SLOT,
                    "current_bookings": current_count,
                    "max_per_slot": MAX_BOOKINGS_PER_SLOT,
                    "available_slots": available_slots if current_count >= MAX_BOOKINGS_PER_SLOT else None,
                }
            
            return {
                "date": date,
                "available_slots": available_slots,
                "booked_slots": [s for s in BUSINESS_HOURS if s not in available_slots],
                "all_slots": BUSINESS_HOURS,
            }
        
        return await self._run(_check)
    
    async def cancel(self, confirmation_number: str, reason: str) -> bool:
        """Cancel a booking by confirmation number."""
        def _cancel():
            ref = self.db.collection(self.collection)
            docs = ref.where("confirmation_number", "==", confirmation_number).limit(1).stream()
            
            for doc in docs:
                doc.reference.update({
                    "cancelled": True,
                    "status": "cancelled",
                    "cancellation_reason": reason,
                    "cancelled_at": datetime.now(),
                })
                logger.info(f"✓ Booking cancelled: {confirmation_number}")
                return True
            
            return False
        
        return await self._run(_cancel)
