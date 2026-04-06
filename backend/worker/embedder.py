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
        # A jina-embeddings-v2 modeling_bert.py update introduced an
        # attn_implementation gate that fails to load from config, causing it
        # to skip PyTorch SDPA and run a raw O(n²) matmul on the full 8192-token
        # window. Cap at chunk_max_tokens so the model never sees inputs longer
        # than what the chunker produces.
        _model.max_seq_length = settings.chunk_max_tokens
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
