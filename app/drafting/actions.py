"""Burr actions for the Factory Loop.

State fields:
  sections          list[dict]  the approved outline sections (id/title/instructions)
  cursor            int         index of the section being drafted
  running_summary   str         rolling context (v1 stand-in for Index B)
  candidates        list[dict]  reranked ParentChunks for the current section
  draft             dict        the current DraftedSection
  eval_ok           bool        whether the draft passed the groundedness check
  drafted_sections  list[dict]  committed sections
  document          str | None  assembled final document (set by assemble)

Each action reads/writes only the fields it needs, so the flow is inspectable.
"""

from __future__ import annotations

from dataclasses import asdict
from functools import partial

from burr.core import State, action

from app.config import get_settings
from app.drafting import events
from app.drafting.evaluator import evaluate_draft
from app.drafting.llm import check_claims, draft_section
from app.models import DraftedSection, ParentChunk
from app.retrieval.retriever import retrieve
from app.stores import mongo


def _emitter(state: State):
    """emit(type, **data) scoped to the current job + section (§7)."""
    section = state["sections"][state["cursor"]]
    return partial(events.emit, state["job_id"],
                   section_id=section["section_id"], section_index=state["cursor"])


def _feedback(report: dict) -> str:
    """Render an eval report as targeted redraft feedback (§4)."""
    lines = [
        f"citation [{f['index']}]: {f['reason']} (parent_id {f['parent_id']})"
        for f in report.get("tier1_failed", [])
    ] + [f"citation [{i}]: claim not supported by its quote" for i in report.get("unverified", [])]
    return "\n".join(lines)


@action(reads=["sections", "cursor", "session_id", "job_id"], writes=["candidates", "retries"])
def retrieve_sources(state: State) -> State:
    section = state["sections"][state["cursor"]]
    emit = _emitter(state)
    emit("section_start", title=section["title"], index=state["cursor"])
    query = f"{section['title']} — {section['instructions']}"
    emit("retrieve_query", query=query)
    parents = retrieve(query, top_n=5, session_id=state["session_id"], emit=emit)
    # A1: fresh section -> reset the redraft counter.
    return state.update(candidates=[p.model_dump() for p in parents], retries=0)


@action(
    reads=["sections", "cursor", "candidates", "running_summary", "retries",
           "eval_report", "job_id"],
    writes=["draft", "retries"],
)
def draft(state: State) -> State:
    section = state["sections"][state["cursor"]]
    emit = _emitter(state)
    emit("draft_start", attempt=state["retries"] + 1)
    sources = [ParentChunk(**c) for c in state["candidates"]]
    drafted = draft_section(
        section_id=section["section_id"],
        title=section["title"],
        instructions=section["instructions"],
        sources=sources,
        running_summary=state["running_summary"],
        # §4: redrafts name WHICH citations failed instead of redrafting blind.
        feedback=_feedback(state["eval_report"]) if state["retries"] > 0 else "",
    )
    emit("draft_done", text_preview=drafted.text[:220],
         citations=[c.model_dump() for c in drafted.citations])
    # A1: count this draft attempt; the evaluate->commit edge fires at the cap.
    return state.update(draft=drafted.model_dump(), retries=state["retries"] + 1)


@action(
    reads=["draft", "candidates", "sections", "cursor", "job_id", "retries", "max_retries"],
    writes=["eval_ok", "eval_report", "draft"],
)
def evaluate(state: State) -> State:
    """§4: Tier-1 deterministic quote verification, then one batched Tier-2
    entailment call. Failing citations are named in the report so the redraft
    is targeted; passing sections carry per-citation `verified` flags.
    """
    settings = get_settings()
    drafted = DraftedSection(**state["draft"])
    by_id = {c["parent_id"]: ParentChunk(**c) for c in state["candidates"]}
    report = evaluate_draft(
        drafted,
        by_id,
        check=check_claims,
        pass_ratio=settings.entailment_pass_ratio,
        quote_threshold=settings.quote_match_threshold,
    )
    draft_out = state["draft"]
    if report.citations:  # tier 1 passed: persist the per-citation verdicts
        draft_out = {**draft_out, "citations": report.citations}

    emit = _emitter(state)
    emit("evaluate", eval_ok=report.eval_ok, attempt=state["retries"],
         tier1_failed=report.tier1_failed, unverified=report.unverified)
    if not report.eval_ok and state["retries"] < state["max_retries"]:
        emit("redraft", attempt=state["retries"] + 1, max=state["max_retries"])
    return state.update(eval_ok=report.eval_ok, eval_report=asdict(report), draft=draft_out)


@action(
    reads=["job_id", "draft", "cursor", "sections", "drafted_sections",
           "running_summary", "eval_ok", "needs_review", "retries", "eval_report"],
    writes=["drafted_sections", "cursor", "running_summary", "needs_review"],
)
def commit(state: State) -> State:
    drafted = DraftedSection(**state["draft"])
    section = state["sections"][state["cursor"]]

    # A1: if we reached commit without passing eval, it's the retry cap firing —
    # save it but flag it so the API/document can surface "couldn't fully ground".
    flagged = not state["eval_ok"]
    needs_review = state["needs_review"] + ([section["section_id"]] if flagged else [])

    # §8: replace-not-insert so a resumed run re-committing a section dedupes;
    # Mongo is the source of truth for committed sections.
    mongo.drafted_sections().replace_one(
        {"job_id": state["job_id"], "section_id": drafted.section_id},
        {
            **drafted.model_dump(),
            "job_id": state["job_id"],
            "title": section["title"],
            "needs_review": flagged,
        },
        upsert=True,
    )
    mongo.jobs().update_one(
        {"_id": state["job_id"]},
        {"$set": {f"audit.per_section.{drafted.section_id}": {
            "attempts": state["retries"], "eval": state["eval_report"]}}},
    )
    # §7: carry the rendered /sections row (minus section_id, which rides on the
    # event envelope) so the document panel appends the section live.
    _emitter(state)(
        "section_committed",
        title=section["title"],
        instructions=section.get("instructions", ""),
        text=drafted.text,
        citations=[c.model_dump() for c in drafted.citations],
        needs_review=flagged,
    )

    summary = state["running_summary"]
    summary = (summary + "\n\n" if summary else "") + f"## {section['title']}\n{drafted.text}"

    return state.update(
        drafted_sections=state["drafted_sections"] + [drafted.model_dump()],
        cursor=state["cursor"] + 1,
        running_summary=summary,
        needs_review=needs_review,
    )


@action(reads=["sections", "drafted_sections"], writes=["document"])
def assemble(state: State) -> State:
    parts = []
    for sec, drafted in zip(state["sections"], state["drafted_sections"]):
        sources = "\n".join(
            f"{i}. _{c.get('source_file') or 'unknown source'}_ — \"{c['quote']}\""
            for i, c in enumerate(drafted["citations"], start=1)
        )
        parts.append(f"## {sec['title']}\n\n{drafted['text']}" + (f"\n\n{sources}" if sources else ""))
    return state.update(document="\n\n".join(parts))
