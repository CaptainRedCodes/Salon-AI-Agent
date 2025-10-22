import asyncio
import uuid
from qdrant_client import models
from qdrant_client.async_qdrant_client import AsyncQdrantClient
from sentence_transformers import SentenceTransformer
import os

from app.config.settings import knowledge_settings
from app.information import SALON_FAQ

FIREBASE_HELP_LOGS = knowledge_settings.logs_collection
QDRANT_COLLECTION = knowledge_settings.qdrant_collection
REFRESH_INTERVAL =  knowledge_settings.refresh_interval
FAQ = SALON_FAQ
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")

class KnowledgeManager:
    def __init__(self):
        self.collection_name = QDRANT_COLLECTION
        self.faq_cache = []
        self.last_updated = None
        self.faq = FAQ

        # Async Qdrant client
        self.qdrant = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )

        # Lightweight embedding model
        self.encoder = SentenceTransformer("paraphrase-MiniLM-L3-v2", cache_folder="./sentence_models")

    async def initialize(self):
        """Initialize Qdrant collection - call this after creating the instance."""
        self.faq_cache = self.faq.copy()
        await self._init_qdrant_collection()
        await self._sync_faqs_to_qdrant()

    async def _run_in_executor(self, func, *args):
        """Run CPU-intensive operations in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    async def _sync_faqs_to_qdrant(self):
        """Sync all cached FAQs to Qdrant vector store."""
        def _prepare_points():
            points = []
            for faq in self.faq_cache:
                vector = self.encoder.encode(faq["question"]).tolist()
                point = models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "question": faq["question"],
                        "answer": faq["answer"],
                        "category": "faq",
                        "source": "local_file"
                    }
                )
                points.append(point)
            return points
        
        # Prepare points in executor (CPU-intensive encoding)
        points = await self._run_in_executor(_prepare_points)
        
        if points:
            await self.qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
            print(f"Synced {len(points)} FAQs to Qdrant")

    async def search_faq(self, query: str):
        """Simple keyword search in cached FAQ."""
        def _search():
            question_lower = query.lower()
            for faq in self.faq_cache:
                q_text = faq["question"].lower()
                if any(word in question_lower for word in q_text.split()):
                    return faq["answer"]
            return None
        
        return await self._run_in_executor(_search)

    async def _init_qdrant_collection(self):
        """Initialize Qdrant collection if not exists."""
        try:
            # Get embedding dimension in executor (CPU-bound)
            embedding_size = await self._run_in_executor(
                self.encoder.get_sentence_embedding_dimension
            )
            
            if embedding_size is None:
                raise ValueError("Failed to get embedding dimension from encoder")
            
            await self.qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as e:
            pass

    async def add_to_knowledge_base(self, question: str, answer: str, category: str = "general"):
        """Store new knowledge item into Qdrant."""
        def _prepare_point():
            vector = self.encoder.encode(question).tolist()
            return models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"question": question, "answer": answer, "category": category}
            )
        
        # Encode in executor (CPU-intensive)
        point = await self._run_in_executor(_prepare_point)
        
        # Upsert to Qdrant (async)
        await self.qdrant.upsert(collection_name=QDRANT_COLLECTION, points=[point])
        print(f"Added new KB item: {question[:50]}...")

    async def search_knowledge(self, query: str, threshold: float = 0.8, top_k: int = 3):
        """Semantic search in Qdrant knowledge base."""
        # Encode query in executor (CPU-intensive)
        query_vector = await self._run_in_executor(
            lambda: self.encoder.encode(query).tolist()
        )
        
        # Search in Qdrant (async)
        hits = await self.qdrant.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vector,
            limit=top_k,
        )
        
        if not hits:
            return None
        
        best = hits[0]
        if best is None or best.score < threshold:
            return None
        
        return best.payload.get("answer") if best.payload else None

    async def close(self):
        """Close the async Qdrant client."""
        await self.qdrant.close()