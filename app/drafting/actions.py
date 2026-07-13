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

from burr.core import State, action

from app.drafting.llm import check_grounded, draft_section
from app.models import DraftedSection, ParentChunk
from app.retrieval.retriever import retrieve
from app.stores import mongo


@action(reads=["sections", "cursor"], writes=["candidates"])
def retrieve_sources(state: State) -> State:
    section = state["sections"][state["cursor"]]
    query = f"{section['title']} — {section['instructions']}"
    parents = retrieve(query, top_n=5)
    return state.update(candidates=[p.model_dump() for p in parents])


@action(
    reads=["sections", "cursor", "candidates", "running_summary"],
    writes=["draft"],
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
    )
    return state.update(draft=drafted.model_dump())


@action(reads=["draft", "candidates"], writes=["eval_ok"])
def evaluate(state: State) -> State:
    """D4: every citation must resolve to a candidate parent_id, and the cited
    source must actually ground the text. Any failure -> rewrite.
    """
    drafted = DraftedSection(**state["draft"])
    by_id = {c["parent_id"]: ParentChunk(**c) for c in state["candidates"]}

    if not drafted.citations:
        return state.update(eval_ok=False)

    ok = True
    for cite in drafted.citations:
        source = by_id.get(cite.parent_id)
        if source is None:  # fabricated / non-candidate parent_id
            ok = False
            break
        if not check_grounded(drafted.text, source).grounded:
            ok = False
            break
    return state.update(eval_ok=ok)


@action(
    reads=["draft", "cursor", "sections", "drafted_sections", "running_summary"],
    writes=["drafted_sections", "cursor", "running_summary"],
)
def commit(state: State) -> State:
    drafted = DraftedSection(**state["draft"])
    section = state["sections"][state["cursor"]]

    mongo.drafted_sections().insert_one(
        {**drafted.model_dump(), "title": section["title"]}
    )

    summary = state["running_summary"]
    summary = (summary + "\n\n" if summary else "") + f"## {section['title']}\n{drafted.text}"

    return state.update(
        drafted_sections=state["drafted_sections"] + [drafted.model_dump()],
        cursor=state["cursor"] + 1,
        running_summary=summary,
    )


@action(reads=["sections", "drafted_sections"], writes=["document"])
def assemble(state: State) -> State:
    parts = []
    for sec, drafted in zip(state["sections"], state["drafted_sections"]):
        cites = "; ".join(c["parent_id"] for c in drafted["citations"])
        parts.append(f"## {sec['title']}\n\n{drafted['text']}\n\n_Citations: {cites}_")
    return state.update(document="\n\n".join(parts))
