"""LLM interface — all calls route through OpenRouter (Mirascope native provider).

The model is a single config value (`MODEL_ID`), so swapping providers/models is a
one-line .env change. Mirascope ships a native `openrouter` provider, so no custom
OpenAI-client wiring is needed — we register the key once and address models as
`openrouter/<MODEL_ID>`. Two typed calls:

  draft_section   -> DraftedSection (text + citations)
  check_grounded  -> Grounded (yes/no + reason) for the evaluator (D4)

Prompt-caching note: native Anthropic cache_control is not guaranteed through
OpenRouter, so v1 does not depend on it. System context is kept as a stable prefix
so caching can be enabled later if the chosen route supports it.
"""

from __future__ import annotations

from functools import lru_cache

from mirascope import llm
from pydantic import BaseModel

from app.config import get_settings
from app.models import DraftedSection, ParentChunk


@lru_cache
def _model() -> llm.Model:
    """Register the OpenRouter key once and return the configured model handle."""
    settings = get_settings()
    llm.register_provider("openrouter", api_key=settings.openrouter_api_key)
    return llm.Model(f"openrouter/{settings.model_id}")


def _format_sources(sources: list[ParentChunk]) -> str:
    """Render retrieved parents as cite-able blocks keyed by parent_id."""
    return "\n\n---\n\n".join(
        f"[parent_id: {s.parent_id}] (from {s.source_file})\n{s.text}" for s in sources
    )


class Grounded(BaseModel):
    grounded: bool
    reason: str


_DRAFT_SYSTEM = (
    "You are a legal drafting co-counsel. Draft the requested section using ONLY "
    "the SOURCES provided. Every substantive claim or clause must be backed by a "
    "citation whose parent_id EXACTLY matches one of the provided sources. Do not "
    "invent parent_ids. If sources conflict on a term (e.g. Net 30 vs Net 60), "
    "present BOTH positions and their sources explicitly — never average or "
    "silently choose one. Set section_id to the id given in the instructions."
)


def draft_section(
    section_id: str,
    title: str,
    instructions: str,
    sources: list[ParentChunk],
    running_summary: str,
) -> DraftedSection:
    """Draft one section grounded strictly in the retrieved sources."""
    user = (
        f"SOURCES:\n{_format_sources(sources)}\n\n"
        f"CONTEXT SO FAR (previously drafted, for consistency):\n"
        f"{running_summary or '(none yet)'}\n\n"
        f"Section id: {section_id}\n"
        f"Section title: {title}\n"
        f"Instructions: {instructions}"
    )
    response = _model().call(
        [llm.SystemMessage(content=_DRAFT_SYSTEM), llm.UserMessage(content=user)],
        format=DraftedSection,
    )
    return response.parse()


_GROUND_SYSTEM = (
    "You verify citations. Decide whether the DRAFT TEXT can be reasonably "
    "supported by the CITED SOURCE alone. Set grounded=true only if the source "
    "substantiates the draft's claims; otherwise grounded=false with a short reason."
)


def check_grounded(section_text: str, source: ParentChunk) -> Grounded:
    """Ask the model whether section_text is supported by this cited source (D4)."""
    user = (
        f"CITED SOURCE (parent_id {source.parent_id}):\n{source.text}\n\n"
        f"DRAFT TEXT:\n{section_text}"
    )
    response = _model().call(
        [llm.SystemMessage(content=_GROUND_SYSTEM), llm.UserMessage(content=user)],
        format=Grounded,
    )
    return response.parse()
