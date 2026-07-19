"""Shared Pydantic contracts used across ingestion, retrieval, and drafting."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


class ParentChunk(BaseModel):
    """A layout-aware CompositeElement from Unstructured (~1000-1500 tokens).

    This is the unit returned to the LLM at draft time (macro-context preserved).
    """

    parent_id: str = Field(default_factory=_uuid)
    mongo_doc_id: str
    text: str
    page_number: int | None = None
    source_file: str


class ChildChunk(BaseModel):
    """A ~256-token slice of a parent, derived by us (Unstructured does not emit
    a second level). Children are what get embedded for high-precision matching.
    """

    child_id: str = Field(default_factory=_uuid)
    parent_id: str
    text: str


class OutlineSection(BaseModel):
    section_id: str = Field(default_factory=_uuid)
    title: str
    instructions: str


class Outline(BaseModel):
    job_id: str
    sections: list[OutlineSection] = Field(default_factory=list)
    approved: bool = False


class Citation(BaseModel):
    parent_id: str
    quote: str
    source_file: str = ""  # filled from the cited parent, never asked of the model
    verified: Literal["quote_verified", "entailed", "unverified"] | None = None


class DraftedSection(BaseModel):
    """Section text uses numbered markers [1], [2]… referencing `citations` by
    position (1-based). Text carries no parent_ids and no leading title heading.
    """

    section_id: str
    text: str
    citations: list[Citation]
