"""Local embeddings via fastembed — dense (semantic) + sparse (BM25 lexical).

Shared by ingestion (embed child texts) and retrieval (embed the query). Models
are loaded lazily and cached so the (large) model download happens once per
process, on first use.
"""

from __future__ import annotations

from functools import lru_cache

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import models

from app.config import get_settings


@lru_cache
def _dense_model() -> TextEmbedding:
    return TextEmbedding(model_name=get_settings().dense_embed_model)


@lru_cache
def _sparse_model() -> SparseTextEmbedding:
    return SparseTextEmbedding(model_name=get_settings().sparse_embed_model)


def embed_dense(texts: list[str]) -> list[list[float]]:
    return [vec.tolist() for vec in _dense_model().embed(texts)]


def embed_sparse(texts: list[str]) -> list[models.SparseVector]:
    out: list[models.SparseVector] = []
    for sv in _sparse_model().embed(texts):
        out.append(
            models.SparseVector(
                indices=sv.indices.tolist(), values=sv.values.tolist()
            )
        )
    return out


def embed_query(text: str) -> tuple[list[float], models.SparseVector]:
    """Embed a single query string into (dense, sparse) for hybrid search."""
    return embed_dense([text])[0], embed_sparse([text])[0]
