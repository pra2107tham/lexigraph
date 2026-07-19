"""Composed retrieval: hybrid search -> rerank -> top-n parent chunks.

This is the single entry point the drafting loop (and the `retrieve` tool) calls.
"""

from __future__ import annotations

from typing import Callable

from app.models import ParentChunk
from app.retrieval.rerank import dedupe_parents, rerank_parents
from app.retrieval.search import hybrid_search


def _snippet(text: str) -> str:
    return text[:90]


def retrieve(
    query: str,
    top_n: int = 5,
    candidates: int = 50,
    session_id: str | None = None,
    emit: Callable[..., None] | None = None,
) -> list[ParentChunk]:
    """Hybrid search -> dedupe -> rerank. `emit(type, **data)` (§7) surfaces the
    intermediate stages to the live stream when provided."""
    points = hybrid_search(query, k=candidates, session_id=session_id)
    parents = dedupe_parents(points)
    ranked = rerank_parents(query, parents, top_n=top_n)
    if emit:
        emit("candidates", n_candidates=len(points),
             sample=[{"parent_id": p.payload["parent_id"], "snippet": _snippet(p.payload.get("parent_text", ""))}
                     for p in points[:5] if p.payload])
        emit("deduped", n_before=len(points), n_after=len(parents),
             parent_ids=[p.parent_id for p in parents])
        emit("reranked", ranked=[{"parent_id": p.parent_id, "snippet": _snippet(p.text), "rank": i + 1}
                                 for i, p in enumerate(ranked)])
    return ranked
