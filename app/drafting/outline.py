"""Generate a draft outline for a job via the LLM.

The user reviews/overrides this outline (Plan Mode) before drafting begins.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.drafting.llm import _model, _system, _user
from app.models import Outline, OutlineSection
from app.retrieval.retriever import retrieve
from app.stores import mongo


class _OutlineDraft(BaseModel):
    """LLM-facing shape: titles + instructions, ids assigned by us afterwards."""

    class _Section(BaseModel):
        title: str
        instructions: str
        source_files: list[str] = Field(default_factory=list)

    sections: list[_Section]


_OUTLINE_SYSTEM = (
    "You are a legal drafting co-counsel. Produce a concise outline (3-10 sections) "
    "for the requested document. Each section needs a clear title and one or two "
    "sentences of drafting instructions describing what it must cover. Do not draft "
    "the content itself. When AVAILABLE DOCUMENTS are listed, only propose sections "
    "the corpus can actually support, and set each section's source_files to the "
    "exact document names that inform it (empty list if none do)."
)


def _corpus_context(prompt: str, session_id: str | None) -> str:
    """B1: what the corpus contains (doc abstracts) + what's relevant (retrieval),
    so the outline skeleton is grounded instead of blind."""
    docs = list(mongo.documents().find(
        {"session_id": session_id}, {"source_file": 1, "abstract": 1}))
    if not docs:
        return ""
    listing = "\n".join(f"- {d['source_file']}: {d.get('abstract') or '(no abstract)'}" for d in docs)
    try:
        passages = retrieve(prompt, top_n=8, session_id=session_id)
        snippets = "\n".join(f"- [{p.source_file}] {p.text[:200]}" for p in passages)
    except Exception:  # noqa: BLE001 — outline still works without retrieval
        snippets = "(retrieval unavailable)"
    return f"AVAILABLE DOCUMENTS:\n{listing}\n\nRELEVANT PASSAGES:\n{snippets}\n\n"


def generate_outline(job_id: str, prompt: str, session_id: str | None = None) -> Outline:
    response = _model().call(
        [_system(_OUTLINE_SYSTEM), _user(_corpus_context(prompt, session_id) + prompt)],
        format=_OutlineDraft,
    )
    draft = response.parse()
    sections = [
        OutlineSection(title=s.title, instructions=s.instructions, source_files=s.source_files)
        for s in draft.sections
    ]
    return Outline(job_id=job_id, sections=sections, approved=False)
