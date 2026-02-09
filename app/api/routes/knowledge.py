from fastapi import APIRouter
from typing import Optional

from app.services.booking import BookingService
from app.services.knowledge import KnowledgeService

router = APIRouter(prefix="/api", tags=["Availability & Knowledge"])

# Services
booking_service = BookingService()
knowledge_service = KnowledgeService()


@router.get("/availability")
async def check_availability(date: str, time: Optional[str] = None):
    """
    Check slot availability for a date.
    
    Called by the AI agent before suggesting times to customer.
    """
    return await booking_service.check_availability(date, time)


@router.get("/knowledge-base/search")
async def search_knowledge_base(query: str, threshold: float = 0.7):
    """
    Search knowledge base for similar questions.
    
    Called by the AI agent before escalating to supervisor.
    """
    result = knowledge_service.search(query, threshold=threshold)
    
    if result:
        return {
            "found": True,
            "answer": result["answer"],
            "question": result.get("question"),
            "score": result.get("score"),
        }
    
    return {"found": False}
