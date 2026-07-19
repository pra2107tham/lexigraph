"""C3 single-section revision turns.

One section, one retrieve->draft->evaluate pass (plus one targeted retry on a
Tier-1 failure) — a full Burr run would be ceremony for a single-section edit.
The revised row upserts over the old one and the assembled document rebuilds.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import HTTPException

from app.config import get_settings
from app.drafting.evaluator import evaluate_draft
from app.drafting.llm import check_claims, draft_section
from app.retrieval.retriever import retrieve
from app.stores import mongo


def _rebuild_document(job: dict) -> str:
    by_id = {d["section_id"]: d
             for d in mongo.drafted_sections().find({"job_id": job["_id"]}, {"_id": 0})}
    parts = []
    for sec in job["outline"]["sections"]:
        d = by_id.get(sec["section_id"])
        if not d:
            continue
        sources = "\n".join(
            f"{i}. _{c.get('source_file') or 'unknown source'}_ — \"{c['quote']}\""
            for i, c in enumerate(d.get("citations", []), start=1))
        parts.append(f"## {sec['title']}\n\n{d['text']}" + (f"\n\n{sources}" if sources else ""))
    return "\n\n".join(parts)


def revise_section(job: dict, section_id: str, instructions: str) -> dict:
    section = next((s for s in job["outline"]["sections"] if s["section_id"] == section_id), None)
    current = mongo.drafted_sections().find_one({"job_id": job["_id"], "section_id": section_id})
    if not section or not current:
        raise HTTPException(status_code=404, detail="section not found")

    settings = get_settings()
    query = f"{section['title']} — {instructions}"
    sources = retrieve(query, top_n=5, session_id=job.get("session_id"))
    by_id = {p.parent_id: p for p in sources}

    feedback = f"CURRENT TEXT (revise per the new instructions):\n{current['text']}"
    drafted, report = None, None
    for _ in range(2):  # one targeted retry on a failed evaluation
        drafted = draft_section(
            section_id=section_id,
            title=section["title"],
            instructions=f"{section['instructions']}\nREVISION REQUEST: {instructions}",
            sources=sources,
            running_summary="",
            feedback=feedback,
        )
        report = evaluate_draft(drafted, by_id, check=check_claims,
                                pass_ratio=settings.entailment_pass_ratio,
                                quote_threshold=settings.quote_match_threshold)
        if report.eval_ok:
            break
        failures = "\n".join(f"citation [{f['index']}]: {f['reason']}" for f in report.tier1_failed)
        feedback += f"\n\nPREVIOUS ATTEMPT FAILED:\n{failures or 'unsupported claims'}"

    row = {
        **drafted.model_dump(),
        "citations": report.citations or [c.model_dump() for c in drafted.citations],
        "job_id": job["_id"],
        "title": section["title"],
        "needs_review": not report.eval_ok,
    }
    mongo.drafted_sections().replace_one(
        {"job_id": job["_id"], "section_id": section_id}, row, upsert=True)
    mongo.jobs().update_one(
        {"_id": job["_id"]}, {"$set": {"document": _rebuild_document(job)}})
    return {k: v for k, v in row.items() if k != "job_id"}
