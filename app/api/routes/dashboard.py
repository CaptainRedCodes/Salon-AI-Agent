from fastapi import APIRouter

from app.services.booking import BookingService
from app.services.help_request import HelpRequestService

router = APIRouter(tags=["Dashboard"])

booking_service = BookingService()
help_service = HelpRequestService()


@router.get("/")
async def dashboard():
    """Main supervisor dashboard data."""
    pending = await help_service.get_pending(limit=5)
    bookings = await booking_service.list_all(limit=10)
    
    return {
        "pending_requests": pending,
        "pending_count": len(pending),
        "recent_bookings": bookings,
        "booking_count": len(bookings),
    }


@router.get("/help-requests")
async def help_requests():
    """Help requests data."""
    pending = await help_service.get_pending()
    resolved = await help_service.get_resolved(limit=20)
    
    return {
        "pending_requests": pending,
        "resolved_requests": resolved,
    }


@router.get("/bookings")
async def bookings():
    """Bookings data."""
    bookings = await booking_service.list_all(limit=50)
    
    return {
        "bookings": bookings,
    }