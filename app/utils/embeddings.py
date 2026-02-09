from sentence_transformers import SentenceTransformer
from typing import Optional

_encoder: Optional[SentenceTransformer] = None


def get_encoder() -> SentenceTransformer:
    """
    Get the sentence transformer encoder for embeddings.
    
    Uses a cached instance to avoid loading the model on every call.
    """
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder
