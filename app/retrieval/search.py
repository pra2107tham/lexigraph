"""Hybrid retrieval over Index A: dense + sparse fused server-side via RRF.

Uses Qdrant's native Reciprocal Rank Fusion (query_points with prefetch +
FusionQuery) — no client-side fusion. Each returned point carries the parent
expansion in its payload, so callers get parent context directly.
"""

from __future__ import annotations

from qdrant_client import models

from app.config import get_settings
from app.retrieval.embeddings import embed_query
from app.stores.qdrant import get_client


def hybrid_search(query: str, k: int = 50, per_branch: int = 50) -> list[models.ScoredPoint]:
    """Return the top-k child points for a query, fusing dense + sparse with RRF.

    per_branch caps how many candidates each of the dense/sparse legs contributes
    before fusion; k caps the fused result.
    """
    settings = get_settings()
    dense_vec, sparse_vec = embed_query(query)

    result = get_client().query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            models.Prefetch(query=dense_vec, using="dense", limit=per_branch),
            models.Prefetch(query=sparse_vec, using="sparse", limit=per_branch),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
        with_payload=True,
    )
    return result.points
