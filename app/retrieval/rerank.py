"""Cohere Rerank v3.5 — precision layer over hybrid-search candidates.

Hybrid search returns child-level hits; multiple children can map to the same
parent. We dedupe to DISTINCT parents first (parent-child expansion), then let
Cohere score each unique parent against the query and keep the top-n. Returning
distinct parents also preserves contradictions (D3): if precedent A says "Net 30"
and B says "Net 60", both parents survive as separate cited candidates rather
than being collapsed.
"""

from __future__ import annotations

from functools import lru_cache

import cohere
from qdrant_client import models

from app.config import get_settings
from app.models import ParentChunk


@lru_cache
def _client() -> cohere.ClientV2:
    return cohere.ClientV2(api_key=get_settings().cohere_api_key)


def dedupe_parents(points: list[models.ScoredPoint]) -> list[ParentChunk]:
    """First occurrence wins (points arrive in fused-rank order)."""
    seen: set[str] = set()
    parents: list[ParentChunk] = []
    for pt in points:
        payload = pt.payload or {}
        pid = payload.get("parent_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        parents.append(
            ParentChunk(
                parent_id=pid,
                mongo_doc_id=payload.get("mongo_doc_id", ""),
                text=payload.get("parent_text", ""),
                source_file=payload.get("source_file", ""),
            )
        )
    return parents


def rerank(
    query: str, points: list[models.ScoredPoint], top_n: int = 5
) -> list[ParentChunk]:
    """Rerank hybrid-search hits and return the top-n distinct parent chunks."""
    return rerank_parents(query, dedupe_parents(points), top_n)


def rerank_parents(query: str, parents: list[ParentChunk], top_n: int = 5) -> list[ParentChunk]:
    if not parents:
        return []

    settings = get_settings()
    response = _client().rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=[p.text for p in parents],
        top_n=min(top_n, len(parents)),
    )
    # results carry .index into the documents list, sorted by relevance.
    return [parents[r.index] for r in response.results]
