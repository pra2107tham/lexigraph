"""Generate a draft outline for a job via the LLM.

The user reviews/overrides this outline (Plan Mode) before drafting begins.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.drafting.llm import _model, _system, _user
from app.models import Outline, OutlineSection


class _OutlineDraft(BaseModel):
    """LLM-facing shape: titles + instructions, ids assigned by us afterwards."""

    class _Section(BaseModel):
        title: str
        instructions: str

    sections: list[_Section]


_OUTLINE_SYSTEM = (
    "You are a legal drafting co-counsel. Produce a concise outline (5-10 sections) "
    "for the requested document. Each section needs a clear title and one or two "
    "sentences of drafting instructions describing what it must cover. Do not draft "
    "the content itself."
)


def generate_outline(job_id: str, prompt: str) -> Outline:
    response = _model().call(
        [_system(_OUTLINE_SYSTEM), _user(prompt)],
        format=_OutlineDraft,
    )
    draft = response.parse()
    sections = [
        OutlineSection(title=s.title, instructions=s.instructions)
        for s in draft.sections
    ]
    return Outline(job_id=job_id, sections=sections, approved=False)
