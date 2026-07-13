"""Composed retrieval: hybrid search -> rerank -> top-n parent chunks.

This is the single entry point the drafting loop (and the `retrieve` tool) calls.
"""

from __future__ import annotations

from app.models import ParentChunk
from app.retrieval.rerank import rerank
from app.retrieval.search import hybrid_search


def retrieve(query: str, top_n: int = 5, candidates: int = 50) -> list[ParentChunk]:
    points = hybrid_search(query, k=candidates)
    return rerank(query, points, top_n=top_n)
