import asyncio
from asyncio.log import logger
from datetime import datetime
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from app.config.settings import help_settings
from app.knowledge_base import KnowledgeManager
from app.db import FirebaseManager
from app.models.help_request import HelpRequestCreate, HelpRequestCreatedEvent, HelpRequestResolvedEvent,HelpRequestStatus,HelpRequestView, SupervisorResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HelpRequestManager:
    """Manages help requests with webhook notifications."""
    
    def __init__(self):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection_name = help_settings.collection_name
        self.knowledge_base = KnowledgeManager()
        self.webhook_url = os.getenv("WEBHOOK_URL")
        self.ai_callback_url = os.getenv("AI_CALLBACK_URL")
        self._loop = asyncio.get_event_loop()
  
    async def _run_in_executor(self, func, *args):
        """Run synchronous Firebase operations in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)
    
    async def create_help_request(self, payload: HelpRequestCreate) -> str:
        """Create a new help request and notify supervisor."""
        request_id = str(uuid4())
        timestamp = datetime.now()

        doc_data = {
            "question": payload.question,
            "answer": None,
            "status": HelpRequestStatus.PENDING.value,
            "room_name": payload.room_name,
            "created_at": timestamp,
            "updated_at": timestamp,
            "resolution_notes": None,
            "response_time_seconds": None,
            "resolved_by": None,
            "resolved_at": None
        }

        def write_doc():
            doc_ref = self.db.collection(self.collection_name).document(request_id)
            doc_ref.set(doc_data)
            return request_id

        await self._run_in_executor(write_doc)
        logger.info(f"Help request created: {request_id} - {payload.question}")

        # Notify supervisor
        await self._notify_supervisor(request_id, doc_data)

        return request_id

    async def _notify_supervisor(self, request_id: str, help_request: Dict):
        """Send webhook notification to supervisor."""
        if not self.webhook_url:
            logger.warning("Supervisor webhook not configured")
            return

        payload = HelpRequestCreatedEvent(
            request_id=request_id,
            question=help_request["question"],
            room_name=help_request.get("room_name"),
            created_at=help_request["created_at"].isoformat()
        )

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self.webhook_url, json=payload.dict())
                if resp.status_code == 200:
                    logger.info(f"Supervisor notified for request {request_id}")
                else:
                    logger.warning(f"Supervisor webhook failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Error notifying supervisor: {e}")

    async def resolve_help_request(
        self,
        request_id: str,
        supervisor_response: SupervisorResponse
    ) -> HelpRequestResolvedEvent:
        """Resolve a help request and optionally add it to the knowledge base."""

        def update_doc():
            doc_ref = self.db.collection(self.collection_name).document(request_id)
            doc = doc_ref.get()

            if not doc.exists:
                raise ValueError(f"Help request {request_id} not found")
            
            data = doc.to_dict()

            if not data:
                raise ValueError(f"Help request {request_id} data is empty")
            
            response_time = (datetime.now() - data["created_at"]).total_seconds()

            update_data = {
                "status": HelpRequestStatus.RESOLVED.value,
                "answer": supervisor_response.answer,
                "resolution_notes": supervisor_response.resolution_notes,
                "updated_at": datetime.now(),
                "response_time_seconds": response_time,
                "resolved_by": "supervisor",
                "resolved_at": datetime.now()
            }
            doc_ref.update(update_data)
            return data, response_time

        help_request, _ = await self._run_in_executor(update_doc)
        logger.info(f"Help request {request_id} resolved")

        # Add to knowledge base
        if supervisor_response.add_to_knowledge_base:
            await self.knowledge_base.add_to_knowledge_base(
                help_request["question"],
                supervisor_response.answer,
                supervisor_response.kb_category
            )

        # Notify AI agent
        event = HelpRequestResolvedEvent(
            request_id=request_id,
            room_name=help_request.get("room_name"),
            original_question=help_request["question"],
            answer=supervisor_response.answer
        )
        await self._notify_ai_agent(event)

        return event

    async def _notify_ai_agent(self, event: HelpRequestResolvedEvent):
        """Send resolved help request to AI agent."""
        if not self.ai_callback_url:
            logger.warning("AI callback not configured")
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self.ai_callback_url, json=event.dict())
                logger.info(f"AI agent notified for request {event.request_id}")
        except Exception as e:
            logger.error(f"Failed to notify AI agent: {e}")

    async def get_pending_requests(self) -> List[HelpRequestView]:
        """Fetch all pending requests."""

        def fetch_pending():
            query = self.db.collection(self.collection_name).where(
                "status", "==", HelpRequestStatus.PENDING.value
            ).order_by("created_at", direction="DESCENDING")
            return [
                HelpRequestView(id=doc.id, **doc.to_dict())
                for doc in query.stream()
            ]

        return await self._run_in_executor(fetch_pending)

    async def get_request_by_id(self, request_id: str) -> Optional[HelpRequestView]:
        """Fetch a specific request by ID."""

        def fetch_doc():
            doc_ref = self.db.collection(self.collection_name).document(request_id)
            doc = doc_ref.get()
            if not doc.exists:
                return None
            data: Dict[str, Any] = doc.to_dict() or {
                "question": "",
                "answer": None,
                "status": HelpRequestStatus.PENDING.value,
                "room_name": "",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "resolution_notes": None,
                "response_time_seconds": None,
                "resolved_by": None,
                "resolved_at": None
            }
            return HelpRequestView(id=doc.id, **data)

        return await self._run_in_executor(fetch_doc)