import asyncio
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
import os

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.core.logging_config import get_logger
from app.core.database import FirebaseManager
from app.core.config import help_settings, knowledge_settings
from app.utils.embeddings import get_encoder
from app.models.help_request import HelpResponseSubmit

logger = get_logger(__name__)


class HelpRequestService:
    """Manages help requests and knowledge base."""
    
    def __init__(self):
        self.firebase = FirebaseManager()
        self.db = self.firebase.get_firestore_client()
        self.collection = help_settings.collection_name
        self.kb_collection = knowledge_settings.collection_name
        
        # Initialize Qdrant
        self.qdrant = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
            timeout=60,
        )
        self.encoder = get_encoder()
    
    async def _run(self, func):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)
    
    async def create(self, data) -> dict:
        """
        Create a help request.
        The AI agent calls this when it can't answer a question.
        """
        def _create():
            request_id = str(uuid4())
            now = datetime.now()
            
            doc_data = {
                "id": request_id,
                "question": data.question,
                "customer_name": data.customer_name,
                "customer_phone": data.customer_phone,
                "booking_context": data.booking_context,
                "room_name": getattr(data, 'room_name', None),
                "status": "pending",
                "answer": None,
                "created_at": now,
                "updated_at": now,
            }
            
            self.db.collection(self.collection).document(request_id).set(doc_data)
            
            logger.info(f"✓ Help request created: {request_id}")
            logger.info(f"  Question: {data.question}")
            if data.customer_name:
                logger.info(f"  Customer: {data.customer_name}")
            
            return doc_data
        
        return await self._run(_create)
    
    async def search_knowledge_base(self, query: str, threshold: float = 0.7) -> Optional[dict]:
        """
        Search for similar questions in knowledge base.
        Returns answer if found above threshold.
        """
        try:
            query_vector = self.encoder.encode(query).tolist()
            
            results = self.qdrant.query_points(
                collection_name=self.kb_collection,
                query=query_vector,
                limit=3,
            )
            
            if results.points and results.points[0].score >= threshold:
                payload = results.points[0].payload or {}
                return {
                    "answer": payload.get("answer"),
                    "question": payload.get("question"),
                    "score": results.points[0].score,
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Knowledge base search error: {e}")
            return None
    
    async def get_pending(self, limit: int = 50) -> List[dict]:
        """Get all pending help requests."""
        def _query():
            docs = self.db.collection(self.collection)\
                         .where("status", "==", "pending")\
                         .limit(limit)\
                         .stream()
            return [doc.to_dict() for doc in docs]
        
        return await self._run(_query)
    
    async def get_resolved(self, limit: int = 50) -> List[dict]:
        """Get resolved help requests."""
        def _query():
            docs = self.db.collection(self.collection)\
                         .where("status", "==", "resolved")\
                         .limit(limit)\
                         .stream()
            return [doc.to_dict() for doc in docs]
        
        return await self._run(_query)
    
    async def respond(self, request_id: str, response: HelpResponseSubmit) -> dict:
        """
        Supervisor responds to a help request.
        Optionally adds to knowledge base.
        """
        def _update():
            doc_ref = self.db.collection(self.collection).document(request_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                raise ValueError(f"Help request {request_id} not found")
            
            doc_data = doc.to_dict()
            now = datetime.now()
            created_at = doc_data.get("created_at")
            
            # Calculate response time
            response_time = None
            if created_at:
                if hasattr(created_at, 'timestamp'):
                    response_time = (now - datetime.fromtimestamp(created_at.timestamp())).total_seconds()
            
            update_data = {
                "answer": response.answer,
                "resolution_notes": response.resolution_notes,
                "status": "resolved",
                "resolved_at": now,
                "updated_at": now,
                "response_time_seconds": response_time,
            }
            
            doc_ref.update(update_data)
            
            logger.info(f"Help request resolved: {request_id}")
            
            return {**doc_data, **update_data}
        
        result = await self._run(_update)
        
        # Add to knowledge base if requested
        if response.add_to_knowledge_base:
            await self._add_to_kb(result.get("question", ""), response.answer)
        
        return result
    
    async def _add_to_kb(self, question: str, answer: str):
        """Add Q&A pair to vector knowledge base."""
        try:
            vector = self.encoder.encode(question).tolist()
            
            self.qdrant.upsert(
                collection_name=self.kb_collection,
                points=[
                    PointStruct(
                        id=str(uuid4()),
                        vector=vector,
                        payload={
                            "question": question,
                            "answer": answer,
                            "category": "supervisor_resolved",
                            "source": "supervisor",
                            "added_at": datetime.now().isoformat(),
                        },
                    )
                ],
            )
            
            logger.info(f"✓ Added to knowledge base: {question[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to add to knowledge base: {e}")
