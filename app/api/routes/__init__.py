# API Routes
from app.api.routes.bookings import router as bookings_router
from app.api.routes.help_requests import router as help_requests_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.knowledge import router as knowledge_router

__all__ = [
    "bookings_router",
    "help_requests_router",
    "dashboard_router",
    "knowledge_router",
]
