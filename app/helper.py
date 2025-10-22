
import asyncio
from asyncio.log import logger
from datetime import datetime
from enum import Enum
import logging
from typing import Any, Dict, Optional
from app.knowledge_base import KnowledgeManager
from app.db import FirebaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HelpRequestStatus(Enum):
    """Status states for help requests."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"

    
class HelpRequestManager:
    """Manages help requests in Firebase."""
    
    def __init__(self):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection_name = "help_requests"
        self.knowledge_base = KnowledgeManager()
  
    async def create_help_request(
        self,
        reason: str,
        room_name: Optional[str] = None,
        customer_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new help request in Firebase.
        
        Args:
            reason: Why help is needed
            room_name: LiveKit room identifier
            customer_context: Additional context about the customer/conversation
            
        Returns:
            Help request ID
        """
        try:
            timestamp = datetime.now()
            
            help_request = {
                "reason": reason,
                "status": HelpRequestStatus.PENDING.value,
                "room_name": room_name,
                "customer_context": customer_context or {},
                "created_at": timestamp,
                "updated_at": timestamp,
                "resolution_notes": None,
                "response_time_seconds": None
            }
            
            doc_ref = self.db.collection(self.collection_name).document()
            doc_ref.set(help_request)
            
            request_id = doc_ref.id
            logger.info(f"Help request created: {request_id} - {reason}")
            
            # Notify supervisor asynchronously
            
            return request_id
            
        except Exception as e:
            logger.error(f"Failed to create help request: {e}")
            raise
        
        
    #WILL UPDATE TO WEBHOOK LATER
    # async def _notify_supervisor(
    #     self,
    #     request_id: str,
    #     reason: str,
    #     room_name: Optional[str]
    # )