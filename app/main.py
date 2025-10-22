from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, logger
from pydantic import BaseModel

from app.helper import HelpRequestCreate, HelpRequestManager, HelpRequestStatus, HelpRequestView, SupervisorResponse

app = FastAPI()

# Initialize manager
help_manager = HelpRequestManager()

@app.webhooks.post("recieve_help_request")
async def receive_help_request(request: HelpRequestCreate):
    """
    Webhook endpoint for receiving help requests from AI agent.
    This is called when the AI agent's request_help tool is triggered.
    """
    try:
        request_id = await help_manager.create_help_request(
            reason=request.reason,
            room_name=request.room_name,
            customer_context=request.customer_context
        )
        
        return {
            "status": "success",
            "request_id": request_id,
            "message": "Help request created and supervisor notified"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/help-requests/pending")
# async def get_pending_requests():
#     """Get all pending help requests for supervisor dashboard."""
#     try:
#         requests = await help_manager.get_pending_requests()
#         return {
#             "status": "success",
#             "count": len(requests),
#             "requests": requests
#         }
#     except Exception as e:
#         logger.error(f"Error fetching pending requests: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/help-requests")
# async def get_all_requests(
#     status: Optional[HelpRequestStatus] = None,
#     limit: int = 100
# ):
#     """Get all help requests with optional status filter."""
#     try:
#         requests = await help_manager.get_all_requests(status=status, limit=limit)
#         return {
#             "status": "success",
#             "count": len(requests),
#             "requests": requests
#         }
#     except Exception as e:
#         logger.error(f"Error fetching requests: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.get("/api/help-requests/{request_id}")
# async def get_help_request(request_id: str):
#     """Get a specific help request by ID."""
#     try:
#         doc = help_manager.db.collection(help_manager.collection_name).document(request_id).get()
        
#         if not doc.exists:
#             raise HTTPException(status_code=404, detail="Help request not found")
        
#         data = doc.to_dict()
#         return {
#             "status": "success",
#             "request": HelpRequestView(id=doc.id, **data)
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error fetching request: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/api/help-requests/{request_id}/resolve")
# async def resolve_help_request(
#     request_id: str,
#     response: SupervisorResponse,
#     background_tasks: BackgroundTasks
# ):
#     """
#     Supervisor submits answer to resolve a help request.
#     This triggers notification to the AI agent to respond to customer.
#     """
#     try:
#         result = await help_manager.resolve_help_request(
#             request_id=request_id,
#             answer=response.answer,
#             resolution_notes=response.resolution_notes,
#             add_to_kb=response.add_to_knowledge_base,
#             kb_category=response.kb_category or "general"
#         )
        
#         return {
#             "status": "success",
#             "message": "Help request resolved and AI agent notified",
#             "data": result
#         }
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     except Exception as e:
#         logger.error(f"Error resolving request: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/webhook/ai-callback")
# async def ai_agent_callback(request: Request):
#     """
#     Callback endpoint for AI agent to receive resolved help requests.
#     The AI agent should implement this endpoint to handle responses.
#     """
#     try:
#         payload = await request.json()
        
#         logger.info(f"AI callback received: {payload.get('event')}")
#         logger.info(f"Request ID: {payload.get('request_id')}")
#         logger.info(f"Room: {payload.get('room_name')}")
#         logger.info(f"Answer: {payload.get('answer')}")
        
#         # Here you would trigger the AI agent to respond to the customer
#         # This could be through LiveKit, WebSocket, or your agent framework
        
#         # Example: Send message to customer through LiveKit room
#         room_name = payload.get("room_name")
#         answer = payload.get("answer")
        
#         if room_name and answer:
#             # Trigger AI to speak the answer in the room
#             # await ai_agent.speak_in_room(room_name, answer)
#             pass
        
#         return {
#             "status": "success",
#             "message": "AI agent will respond to customer"
#         }
        
#     except Exception as e:
#         logger.error(f"Error in AI callback: {e}")
#         raise HTTPException(status_code=500, detail=str(e))
