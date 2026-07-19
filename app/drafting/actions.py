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

from burr.core import State, action

from app.config import get_settings
from app.drafting.evaluator import evaluate_draft
from app.drafting.llm import check_claims, draft_section
from app.models import DraftedSection, ParentChunk
from app.retrieval.retriever import retrieve
from app.stores import mongo


def _feedback(report: dict) -> str:
    """Render an eval report as targeted redraft feedback (§4)."""
    lines = [
        f"citation [{f['index']}]: {f['reason']} (parent_id {f['parent_id']})"
        for f in report.get("tier1_failed", [])
    ] + [f"citation [{i}]: claim not supported by its quote" for i in report.get("unverified", [])]
    return "\n".join(lines)


@action(reads=["sections", "cursor"], writes=["candidates", "retries"])
def retrieve_sources(state: State) -> State:
    section = state["sections"][state["cursor"]]
    query = f"{section['title']} — {section['instructions']}"
    parents = retrieve(query, top_n=5)
    # A1: fresh section -> reset the redraft counter.
    return state.update(candidates=[p.model_dump() for p in parents], retries=0)


@action(
    reads=["sections", "cursor", "candidates", "running_summary", "retries", "eval_report"],
    writes=["draft", "retries"],
)
def draft(state: State) -> State:
    section = state["sections"][state["cursor"]]
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
    # A1: count this draft attempt; the evaluate->commit edge fires at the cap.
    return state.update(draft=drafted.model_dump(), retries=state["retries"] + 1)


@action(reads=["draft", "candidates"], writes=["eval_ok", "eval_report", "draft"])
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
    return state.update(eval_ok=report.eval_ok, eval_report=asdict(report), draft=draft_out)


@action(
    reads=["job_id", "draft", "cursor", "sections", "drafted_sections",
           "running_summary", "eval_ok", "needs_review"],
    writes=["drafted_sections", "cursor", "running_summary", "needs_review"],
)
def commit(state: State) -> State:
    drafted = DraftedSection(**state["draft"])
    section = state["sections"][state["cursor"]]

    # A1: if we reached commit without passing eval, it's the retry cap firing —
    # save it but flag it so the API/document can surface "couldn't fully ground".
    flagged = not state["eval_ok"]
    needs_review = state["needs_review"] + ([section["section_id"]] if flagged else [])

    mongo.drafted_sections().insert_one(
        {
            **drafted.model_dump(),
            "job_id": state["job_id"],
            "title": section["title"],
            "needs_review": flagged,
        }
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
