import asyncio
from asyncio.log import logger
from datetime import datetime
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from app.knowledge_base import KnowledgeManager
from app.db import FirebaseManager
from app.model import HelpRequestCreate,HelpRequestStatus,HelpRequestView,SupervisorResponse
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



    
class HelpRequestManager:
    """Manages help requests with webhook notifications."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection_name = "help_requests"
        self.knowledge_base = KnowledgeManager()
        self.webhook_url = webhook_url or os.getenv("WEBHOOK_URL")
        self.ai_callback_url = os.getenv("AI_CALLBACK_URL")
        self._loop = asyncio.get_event_loop()
  
    async def _run_in_executor(self, func, *args):
        """Run synchronous Firebase operations in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)
    
    async def create_help_request(
        self,
        reason: str,
        room_name: Optional[str] = None,
        customer_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new help request and notify supervisor."""
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
                "answer": None,
                "response_time_seconds": None
            }
            
            # Run Firebase operations in executor
            def create_doc():
                doc_ref = self.db.collection(self.collection_name).document()
                doc_ref.set(help_request)
                return doc_ref.id
            
            request_id = await self._run_in_executor(create_doc)
            logger.info(f"Help request created: {request_id} - {reason}")
            
            # Notify supervisor asynchronously
            await self._notify_supervisor(request_id, help_request)
            
            return request_id
            
        except Exception as e:
            logger.error(f"Failed to create help request: {e}")
            raise
    
    async def _notify_supervisor(self, request_id: str, help_request: Dict[str, Any]):
        """Send webhook notification to supervisor."""
        if not self.webhook_url:
            logger.warning("Supervisor webhook URL not configured")
            return
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "event": "help_request_created",
                    "request_id": request_id,
                    "reason": help_request["reason"],
                    "room_name": help_request.get("room_name"),
                    "customer_context": help_request.get("customer_context"),
                    "created_at": help_request["created_at"].isoformat(),
                    "dashboard_url": f"{os.getenv('DASHBOARD_URL', '')}/help-requests/{request_id}"
                }
                
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    logger.info(f"Supervisor notified for request {request_id}")
                else:
                    logger.warning(f"Supervisor notification failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Failed to notify supervisor: {e}")
    
    async def resolve_help_request(
        self,
        request_id: str,
        answer: str,
        resolution_notes: Optional[str] = None,
        add_to_kb: bool = True,
        kb_category: str = "general"
    ) -> Dict[str, Any]:
        """Resolve a help request with supervisor's answer."""
        try:
            # Run Firebase operations in executor
            def get_and_update():
                doc_ref = self.db.collection(self.collection_name).document(request_id)
                doc = doc_ref.get()
                
                if not doc.exists:
                    raise ValueError(f"Help request {request_id} not found")
                
                help_request = doc.to_dict()
                if not help_request:
                    raise ValueError(f"Help request {request_id} data is corrupted")
                    
                created_at = help_request["created_at"]
                response_time = (datetime.now() - created_at).total_seconds()
                
                # Update help request
                update_data = {
                    "status": HelpRequestStatus.RESOLVED.value,
                    "answer": answer,
                    "resolution_notes": resolution_notes,
                    "updated_at": datetime.now(),
                    "response_time_seconds": response_time,
                    "resolved_by": "supervisor",
                    "resolved_at": datetime.now()
                }
                
                doc_ref.update(update_data)
                return help_request, response_time
            
            help_request, response_time = await self._run_in_executor(get_and_update)
            logger.info(f"Help request {request_id} resolved")
            
            # Add to knowledge base in executor
            if add_to_kb:
                await self._run_in_executor(
                    self.knowledge_base.add_to_knowledge_base,
                    help_request["reason"],
                    answer,
                    kb_category
                )
            
            # Notify AI agent asynchronously
            await self._notify_ai_agent(request_id, help_request, answer)
            
            return {
                "request_id": request_id,
                "status": "resolved",
                "response_time_seconds": response_time
            }
            
        except Exception as e:
            logger.error(f"Failed to resolve help request: {e}")
            raise
    
    async def _notify_ai_agent(
        self,
        request_id: str,
        help_request: Dict[str, Any],
        answer: str
    ):
        """Notify AI agent to respond to customer."""
        if not self.ai_callback_url:
            logger.warning("AI callback URL not configured")
            return
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "event": "help_request_resolved",
                    "request_id": request_id,
                    "room_name": help_request.get("room_name"),
                    "original_question": help_request["reason"],
                    "answer": answer,
                    "customer_context": help_request.get("customer_context")
                }
                
                response = await client.post(
                    self.ai_callback_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    logger.info(f"AI agent notified for request {request_id}")
                else:
                    logger.warning(f"AI agent notification failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Failed to notify AI agent: {e}")
    
    async def get_pending_requests(self) -> List[HelpRequestView]:
        """Get all pending help requests."""
        try:
            def fetch_pending():
                query = self.db.collection(self.collection_name).where(
                    "status", "==", HelpRequestStatus.PENDING.value
                ).order_by("created_at", direction="DESCENDING")
                
                docs = query.stream()
                requests = []
                
                for doc in docs:
                    data = doc.to_dict()
                    requests.append(HelpRequestView(
                        id=doc.id,
                        **data
                    ))
                
                return requests
            
            return await self._run_in_executor(fetch_pending)
            
        except Exception as e:
            logger.error(f"Failed to get pending requests: {e}")
            raise
    
    async def get_all_requests(
        self,
        status: Optional[HelpRequestStatus] = None,
        limit: int = 100
    ) -> List[HelpRequestView]:
        """Get all help requests with optional status filter."""
        try:
            def fetch_all():
                query = self.db.collection(self.collection_name)
                
                if status:
                    query = query.where("status", "==", status.value)
                
                query = query.order_by("created_at", direction="DESCENDING").limit(limit)
                
                docs = query.stream()
                requests = []
                
                for doc in docs:
                    data = doc.to_dict()
                    requests.append(HelpRequestView(
                        id=doc.id,
                        **data
                    ))
                
                return requests
            
            return await self._run_in_executor(fetch_all)
            
        except Exception as e:
            logger.error(f"Failed to get requests: {e}")
            raise