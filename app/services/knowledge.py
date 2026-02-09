from typing import Any, Dict
import uuid
import os
from itertools import islice

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.core.logging_config import get_logger
from app.core.config import knowledge_settings, SalonDataLoader
from app.utils.embeddings import get_encoder

logger = get_logger(__name__)

QDRANT_COLLECTION = knowledge_settings.collection_name
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")

# Control syncing from env
SYNC_KB = os.getenv("SYNC_KB", "false").lower() == "true"


def batch(iterable, size=50):
    """Yield batches of fixed size"""
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk


class KnowledgeService:
    """Manages the vector knowledge base for FAQ and learned answers."""
    
    def __init__(self):
        self.collection_name = QDRANT_COLLECTION

        # Load salon FAQs from centralized loader
        self.faq = SalonDataLoader.get_faqs()

        self.qdrant = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=60,
        )

        self.encoder = get_encoder()

    def initialize(self):
        """Initialize Qdrant collection and optionally sync FAQs."""
        self._init_collection()

        if SYNC_KB:
            self._sync_faqs()
        else:
            logger.info("Skipping FAQ sync (SYNC_KB=false)")

    def _init_collection(self):
        """Create collection if it doesn't exist."""
        try:
            self.qdrant.get_collection(self.collection_name)
            logger.info("Collection already exists")
        except Exception:
            embedding_size = self.encoder.get_sentence_embedding_dimension()
            if not embedding_size:
                raise ValueError("Could not determine embedding dimension")

            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=embedding_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created collection '{self.collection_name}'")

    def _sync_faqs(self):
        """Sync FAQs to Qdrant (BATCHED)."""

        if not isinstance(self.faq, list):
            logger.error(f"FAQ is not a list! Type: {type(self.faq)}")
            return

        points = []

        for idx, faq in enumerate(self.faq):
            if not isinstance(faq, dict):
                logger.warning(f"Invalid FAQ at index {idx}")
                continue

            question = faq.get("question")
            answer = faq.get("answer")

            if not question or not answer:
                logger.warning(f"Missing data in FAQ {idx}")
                continue

            vector = self.encoder.encode(question).tolist()

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "question": question,
                        "answer": answer,
                        "category": "faq",
                        "source": "local",
                    },
                )
            )

        if not points:
            logger.warning("No valid FAQs to sync")
            return

        # Batch upserts to avoid timeouts
        for i, chunk in enumerate(batch(points, size=50), start=1):
            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=chunk,
            )
            logger.info(f"Upserted batch {i} ({len(chunk)} points)")

        logger.info(f"FAQ sync complete ({len(points)} total)")

    def search(self, query: str, threshold: float = 0.7, top_k: int = 3):
        """Search knowledge base for similar questions."""
        query_vector = self.encoder.encode(query).tolist()

        results = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
        )

        if results.points and results.points[0].score >= threshold:
            payload = cast(Dict[str, Any], results.points[0].payload or {})
            return {
                "answer": payload.get("answer"),
                "question": payload.get("question"),
                "score": results.points[0].score,
            }

        return None

    def add_knowledge(self, question: str, answer: str, category: str = "general"):
        """Add a new Q&A pair to the knowledge base."""
        vector = self.encoder.encode(question).tolist()

        self.qdrant.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "question": question,
                        "answer": answer,
                        "category": category,
                        "source": "user_added",
                    },
                )
            ],
        )

        logger.info(f"Added knowledge: {question[:40]}...")

    def close(self):
        """Close the Qdrant client connection."""
        self.qdrant.close()
