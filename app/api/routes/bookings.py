from fastapi import APIRouter, HTTPException
from typing import Optional

from app.models.booking import BookingCreate, BookingResponse
from app.services.booking import BookingService

router = APIRouter(prefix="/api/bookings", tags=["Bookings"])


booking_service = BookingService()


@router.post("", response_model=BookingResponse)
async def create_booking(data: BookingCreate):
    """
    Create a new booking.
    
    Called by the AI agent after customer confirmation.
    Returns 409 if slot is fully booked.
    """
    return await booking_service.create(data)


@router.get("")
async def list_bookings(date: Optional[str] = None, limit: int = 50):
    """
    List all bookings, optionally filtered by date.
    
    Used by the supervisor dashboard.
    """
    return await booking_service.list_all(date=date, limit=limit)


@router.delete("/{confirmation_number}")
async def cancel_booking(confirmation_number: str, reason: str = ""):
    """
    Cancel a booking by confirmation number.
    """
    success = await booking_service.cancel(confirmation_number, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"status": "cancelled", "confirmation_number": confirmation_number}

@router.get("/availability")
async def check_availability(date: str, time: Optional[str] = None):
    """Check slot availability for a date and optionally a specific time."""
    try:
        result = await booking_service.check_availability(date, time)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


