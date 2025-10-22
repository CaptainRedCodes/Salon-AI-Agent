from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class HelpRequestStatus(Enum):
    """Status states for help requests."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class HelpRequestCreate(BaseModel):
    question: str = Field(..., description="The customer's question that needs supervisor help")
    room_name: Optional[str] = Field(None, description="Chat room/session identifier")
    
class SupervisorResponse(BaseModel):
    answer: str = Field(..., description="The supervisor's answer to the question")
    resolution_notes: Optional[str] = Field(None, description="Internal notes about the resolution")
    add_to_knowledge_base: bool = Field(True, description="Whether to add this Q&A to knowledge base")
    kb_category: str = Field("general", description="Knowledge base category")

class HelpRequestView(BaseModel):
    id: str = Field(..., description="UUID of the help request")
    question: str = Field(..., description="The customer's question")
    answer: Optional[str] = Field(None, description="The supervisor's answer (null if pending)")
    status: str = Field(..., description="Current status of the request")
    room_name: Optional[str] = Field(None, description="Chat room/session identifier")
    created_at: datetime = Field(..., description="When the request was created")
    updated_at: datetime = Field(..., description="When the request was last updated")
    resolution_notes: Optional[str] = Field(None, description="Internal resolution notes")
    response_time_seconds: Optional[float] = Field(None, description="Time taken to resolve (null if pending)")
    resolved_by: Optional[str] = Field(None, description="Who resolved the request")
    resolved_at: Optional[datetime] = Field(None, description="When it was resolved")
    
    class Config:
        arbitrary_types_allowed = True
        
class HelpRequestResolvedEvent(BaseModel):
    event: str = Field(default="help_request_resolved", description="Event type")
    request_id: str = Field(..., description="UUID of the resolved request")
    room_name: Optional[str] = Field(None, description="Chat room to send answer to")
    original_question: str = Field(..., description="The original customer question")
    answer: str = Field(..., description="The supervisor's answer")

class HelpRequestCreatedEvent(BaseModel):
    event: str = Field(default="help_request_created", description="Event type")
    request_id: str = Field(..., description="UUID of the new request")
    question: str = Field(..., description="The customer's question")
    room_name: Optional[str] = Field(None, description="Chat room identifier")
    created_at: str = Field(..., description="ISO format timestamp")