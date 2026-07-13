"""Qdrant Cloud — vector store (Index A: static precedent corpus).

Index A holds CHILD chunks with two named vectors:
  dense   semantic embedding (BAAI/bge-small-en-v1.5 by default, dim 384)
  sparse  BM25-style lexical vector

Each point's payload carries the parent expansion + provenance, so retrieval can
return the parent chunk (parent-child pattern) without a second round trip:
  {parent_id, parent_text, mongo_doc_id, source_file}
"""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.config import get_settings


@lru_cache
def get_client() -> QdrantClient:
    """Cached Qdrant client for the configured cloud instance."""
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection() -> None:
    """Create Index A with named dense + sparse vectors if it doesn't exist.

    Idempotent: safe to call at every startup.
    """
    settings = get_settings()
    client = get_client()
    if client.collection_exists(settings.qdrant_collection):
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={
            "dense": models.VectorParams(
                size=settings.dense_embed_dim,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )
