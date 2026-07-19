"""LLM interface — all calls route through OpenRouter (Mirascope native provider).

The model is a single config value (`MODEL_ID`), so swapping providers/models is a
one-line .env change. Mirascope ships a native `openrouter` provider, so no custom
OpenAI-client wiring is needed — we register the key once and address models as
`openrouter/<MODEL_ID>`. Two typed calls:

  draft_section   -> DraftedSection (text + numbered citations)
  check_claims    -> list[bool], one batched entailment call per section (§4 Tier 2)

Prompt-caching note: native Anthropic cache_control is not guaranteed through
OpenRouter, so v1 does not depend on it. System context is kept as a stable prefix
so caching can be enabled later if the chosen route supports it.
"""

from __future__ import annotations

import os
from functools import lru_cache

from mirascope import llm
from pydantic import BaseModel

from app.config import get_settings
from app.drafting.postprocess import clean_section
from app.models import DraftedSection, ParentChunk


@lru_cache
def _model() -> llm.Model:
    """Return the configured model handle.

    Mirascope's openrouter provider reads the OPENROUTER_API_KEY env var at call
    time (passing api_key to register_provider is not honored), so we export the
    settings value into the environment here.
    """
    settings = get_settings()
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
    return llm.Model(f"openrouter/{settings.model_id}")


def _user(text: str) -> llm.UserMessage:
    return llm.messages.user(text)


def _system(text: str) -> llm.SystemMessage:
    return llm.messages.system(text)


def _format_sources(sources: list[ParentChunk]) -> str:
    """Render retrieved parents as cite-able blocks keyed by parent_id."""
    return "\n\n---\n\n".join(
        f"[parent_id: {s.parent_id}] (from {s.source_file})\n{s.text}" for s in sources
    )


class _ClaimVerdicts(BaseModel):
    supported: list[bool]


_DRAFT_SYSTEM = (
    "You are a legal drafting co-counsel. Draft the requested section using ONLY "
    "the SOURCES provided. Write GitHub-flavored markdown (paragraphs, ### "
    "sub-headings, lists, bold). Do NOT repeat the section title; start directly "
    "with the content. Mark every substantive claim with a bracketed number [1], "
    "[2]… and list each citation exactly once in `citations` in that order: the "
    "citation's parent_id must EXACTLY match a provided source and its quote must "
    "be a VERBATIM excerpt from that source supporting the claim. NEVER write "
    "parent_ids in the text — only numbered markers. If sources conflict on a "
    "term (e.g. Net 30 vs Net 60), present BOTH positions and their sources "
    "explicitly — never average or silently choose one. Set section_id to the id "
    "given in the instructions."
)


def draft_section(
    section_id: str,
    title: str,
    instructions: str,
    sources: list[ParentChunk],
    running_summary: str,
    feedback: str = "",
) -> DraftedSection:
    """Draft one section grounded strictly in the retrieved sources.

    `feedback` names the previous attempt's failed citations so redrafts are
    targeted instead of blind (§4).
    """
    user = (
        f"SOURCES:\n{_format_sources(sources)}\n\n"
        f"CONTEXT SO FAR (previously drafted, for consistency):\n"
        f"{running_summary or '(none yet)'}\n\n"
        f"Section id: {section_id}\n"
        f"Section title: {title}\n"
        f"Instructions: {instructions}"
        + (f"\n\nPREVIOUS ATTEMPT FAILED:\n{feedback}" if feedback else "")
    )
    response = _model().call(
        [_system(_DRAFT_SYSTEM), _user(user)],
        format=DraftedSection,
    )
    drafted = response.parse()
    files = {s.parent_id: s.source_file for s in sources}
    for c in drafted.citations:
        c.source_file = files.get(c.parent_id, "")
    drafted.text, drafted.citations = clean_section(drafted.text, title, drafted.citations)
    return drafted


class _Title(BaseModel):
    title: str


def make_title(prompt: str) -> str:
    """3-6 word session title from the first prompt; falls back to a truncation
    so sessions still get named when no LLM is reachable."""
    try:
        response = _model().call(
            [_system("Write a 3-6 word title for this legal drafting request. No quotes."),
             _user(prompt)],
            format=_Title,
        )
        return response.parse().title.strip() or prompt[:60]
    except Exception:  # noqa: BLE001
        return prompt[:60]


_CLAIMS_SYSTEM = (
    "You verify citations. For EACH numbered claim/quote pair, decide whether "
    "the quoted source text reasonably supports the claim. Return `supported` "
    "as a list of booleans, one per pair, in the same order."
)


def check_claims(pairs: list[tuple[str, str]]) -> list[bool]:
    """One batched entailment call for a whole section (§4 Tier 2)."""
    if not pairs:
        return []
    user = "\n\n".join(
        f"{i}. CLAIM: {claim}\n   QUOTE: {quote}" for i, (claim, quote) in enumerate(pairs, 1)
    )
    response = _model().call([_system(_CLAIMS_SYSTEM), _user(user)], format=_ClaimVerdicts)
    verdicts = response.parse().supported
    # models drift on list lengths; missing verdicts count as unsupported
    return (verdicts + [False] * len(pairs))[: len(pairs)]
