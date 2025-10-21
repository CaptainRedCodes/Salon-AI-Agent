from datetime import datetime
import asyncio
import uuid
import json
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
import os
from pathlib import Path

FIREBASE_HELP_LOGS = "help_logs"
QDRANT_COLLECTION = "knowledge_base"
REFRESH_INTERVAL = 18000  # seconds 
FAQ_FILE_PATH = os.path.join(os.path.dirname(__file__), "json", "faq.json")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")

class KnowledgeManager:
    def __init__(self):
        self.collection_name = QDRANT_COLLECTION
        self.faq_cache = []
        self.last_updated = None
        self.faq_file_path = FAQ_FILE_PATH

        # Qdrant client
        self.qdrant = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )

        # Lightweight embedding model with local cache
        self.encoder = SentenceTransformer("paraphrase-MiniLM-L3-v2", cache_folder="./models")

        # Initialize Qdrant collection
        self._init_qdrant_collection()

    async def load_faq(self):
        """Load FAQ data from local JSON file and sync to Qdrant."""
        loop = asyncio.get_event_loop()

        def _load_file():
            try:
                with open(self.faq_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    else:
                        print(f"[Warning] FAQ JSON is not a list: {self.faq_file_path}")
                        return []
            except FileNotFoundError:
                print(f"[Error] FAQ file not found: {self.faq_file_path}")
                return []
            except json.JSONDecodeError as e:
                print(f"[Error] Failed to parse JSON {self.faq_file_path}: {e}")
                return []

        # Load FAQs in a thread pool to avoid blocking
        self.faq_cache = await loop.run_in_executor(None, _load_file)
        self.last_updated = datetime.now()

        # Sync to Qdrant (also in executor)
        await loop.run_in_executor(None, self._sync_faqs_to_qdrant)

        print(f"Loaded {len(self.faq_cache)} FAQs from {self.faq_file_path}")

    def _sync_faqs_to_qdrant(self):
        """Sync all cached FAQs to Qdrant vector store."""
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
        
        if points:
            self.qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
            print(f"Synced {len(points)} FAQs to Qdrant")

    def search_faq(self, query: str):
        """Simple keyword search in cached FAQ."""
        question_lower = query.lower()
        for faq in self.faq_cache:
            q_text = faq["question"].lower()
            if any(word in question_lower for word in q_text.split()):
                return faq["answer"]
        return None

    def _init_qdrant_collection(self):
        """Initialize Qdrant collection if not exists."""
        try:
            embedding_size = self.encoder.get_sentence_embedding_dimension()
            if embedding_size is None:
                raise ValueError("Failed to get embedding dimension from encoder")
            self.qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception:
            pass

    def add_to_knowledge_base(self, question: str, answer: str, category: str = "general"):
        """Store new knowledge item into Qdrant."""
        vector = self.encoder.encode(question).tolist()
        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"question": question, "answer": answer, "category": category}
        )
        self.qdrant.upsert(collection_name=QDRANT_COLLECTION, points=[point])
        print(f"Added new KB item: {question[:50]}...")

    def search_knowledge(self, query: str, threshold: float = 0.8, top_k: int = 3):
        """Semantic search in Qdrant knowledge base."""
        hits = self.qdrant.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=self.encoder.encode(query).tolist(),
            limit=top_k,
        )
        if not hits:
            return None
        best = hits[0]
        if best.score < threshold:
            return None
        return best.payload["answer"]