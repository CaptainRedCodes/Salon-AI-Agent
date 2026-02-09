from fastapi import APIRouter, HTTPException

from app.models.help_request import HelpRequestCreate, HelpResponseSubmit
from app.services.help_request import HelpRequestService

router = APIRouter(prefix="/api/help-requests", tags=["Help Requests"])


help_service = HelpRequestService()


@router.post("")
async def create_help_request(data: HelpRequestCreate):
    """
    Create a help request.
    
    Called by the AI agent when it cannot answer a question.
    The supervisor will see this in the dashboard.
    """
    result = await help_service.create(data)
    return {"status": "created", "data": result}


@router.get("")
async def list_pending_requests(limit: int = 50):
    """
    Get all pending help requests.
    
    Used by the supervisor dashboard.
    """
    return await help_service.get_pending(limit=limit)


@router.get("/resolved")
async def list_resolved_requests(limit: int = 50):
    """Get resolved help requests."""
    return await help_service.get_resolved(limit=limit)


@router.post("/{request_id}/respond")
async def respond_to_request(request_id: str, response: HelpResponseSubmit):
    """
    Supervisor responds to a help request.
    
    The answer will optionally be added to the knowledge base.
    """
    try:
        result = await help_service.respond(request_id, response)
        return {"status": "resolved", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
