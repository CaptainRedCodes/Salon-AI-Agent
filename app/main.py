from fastapi import FastAPI, HTTPException
from app.models.help_request import SupervisorResponse
from app.help_request import HelpRequestCreate, HelpRequestManager

app = FastAPI()

help_manager = HelpRequestManager()

@app.webhooks.post("recieve_help_request")
async def receive_help_request(request: HelpRequestCreate):
    """
    Webhook endpoint for receiving help requests from AI agent.
    This is called when the AI agent's request_help tool is triggered.
    """
    try:
        request_id = await help_manager.create_help_request(
            payload=request
        )
        
        return {
            "status": "success",
            "request_id": request_id,
            "message": "Help request created and supervisor notified"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/help-requests/{request_id}/resolve")
async def resolve_help_request(request_id: str, payload: SupervisorResponse):
    """
    Supervisor submits answer to resolve a help request.
    This triggers notification to the AI agent to respond to customer.
    
    Flow:
    1. Supervisor calls this endpoint with answer
    2. Updates help request in Firebase with status=RESOLVED
    3. Adds Q&A to knowledge base (optional)
    4. Sends webhook to AI agent with the answer
    5. AI agent receives answer and sends it to customer
    """
    try:
        result = await help_manager.resolve_help_request(request_id, payload)
        return {
            "status": "success",
            "message": "Help request resolved and AI agent notified",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/api/help-request-resolved")
async def ai_agent_callback(payload: dict):
    """
    Callback endpoint that receives notifications when help requests are resolved.
    This is called BY the help_manager when a supervisor resolves a request.
    """
    try:
        request_id = payload.get("request_id")
        room_name = payload.get("room_name")
        question = payload.get("original_question")
        answer = payload.get("answer")
        
        # TODO: Implement logic to send answer to customer
        
        # Placeholder implementation
        print(f"[AI AGENT] Sending answer to room {room_name}")
        print(f"[AI AGENT] Question: {question}")
        print(f"[AI AGENT] Answer: {answer}")
        
        
        return {
            "status": "success",
            "message": f"Answer delivered to room {room_name}"
        }
        
    except Exception as e:
        # Log the error but return success to avoid webhook retries
        print(f"Error in AI agent callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/help-requests/pending")
async def get_pending_requests():
    """
    Get all pending help requests for supervisor dashboard.
    """
    try:
        requests = await help_manager.get_pending_requests()
        return {
            "status": "success",
            "count": len(requests),
            "requests": requests
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/help-requests/{request_id}")
async def get_help_request(request_id: str):
    """
    Get a specific help request by ID.
    """
    try:
        request = await help_manager.get_request_by_id(request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Help request not found")
        
        return {
            "status": "success",
            "request": request
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))