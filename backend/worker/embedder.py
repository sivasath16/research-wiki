"""
Code-aware embedding using jinaai/jina-embeddings-v2-base-code.
768-dim vectors — significantly better code retrieval than general sentence models.
Singleton pattern so the model loads once per worker process.
"""
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer
from core.config import settings

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # trust_remote_code required by jina-embeddings-v2
        _model = SentenceTransformer(
            settings.embedding_model,
            trust_remote_code=True,
        )
    return _model


def embed_texts(texts: List[str], batch_size: int = 64) -> List[List[float]]:
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def embed_query(query: str) -> List[float]:
    model = get_model()
    embedding = model.encode(query, normalize_embeddings=True)
    return embedding.tolist()
