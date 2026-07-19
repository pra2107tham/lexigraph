"""FastAPI routes — thin layer delegating to ingestion / drafting services.

Job lifecycle:
  POST /documents                     ingest precedent PDFs into Index A
  POST /jobs                          create job + generate a draft outline
  GET  /jobs/{id}/outline             fetch the outline for review
  POST /jobs/{id}/outline/approve     approve (optionally override) the outline
  POST /jobs/{id}/run                 run the Factory Loop to completion
  GET  /jobs/{id}/document            fetch the assembled document
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from typing import Annotated
from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.sessions import add_message, set_title_once
from app.config import get_settings
from app.drafting.graph import build_app, run_to_completion
from app.drafting.llm import make_title
from app.drafting.outline import generate_outline
from app.drafting.postprocess import clean_section
from app.ingestion.pipeline import ingest_pdf
from app.models import Citation, Outline
from app.stores import mongo

router = APIRouter()


# ---- documents -----------------------------------------------------------

@router.post("/documents")
async def upload_documents(
    files: list[UploadFile], session_id: Annotated[str | None, Form()] = None
) -> dict:
    results = []
    for f in files:
        content = await f.read()
        summary = ingest_pdf(content, f.filename or "upload.pdf", session_id=session_id)
        add_message(session_id, "ingest_receipt", {
            "source_file": summary["source_file"],
            "mongo_doc_id": summary["mongo_doc_id"],
            "n_parents": summary["n_parents"],
        })
        results.append(summary)
    return {"ingested": results}


# ---- jobs ----------------------------------------------------------------

class CreateJob(BaseModel):
    prompt: str  # e.g. "Draft a Master Services Agreement for ..."
    session_id: str | None = None


@router.post("/jobs")
def create_job(body: CreateJob) -> dict:
    job_id = str(uuid.uuid4())
    outline = generate_outline(job_id, body.prompt)
    mongo.jobs().insert_one(
        {"_id": job_id, "prompt": body.prompt, "session_id": body.session_id,
         "outline": outline.model_dump(), "status": "outline_pending"}
    )
    if body.session_id:
        set_title_once(body.session_id, make_title(body.prompt))
        add_message(body.session_id, "user_prompt", {"text": body.prompt, "job_id": job_id})
        add_message(body.session_id, "outline_card",
                    {"job_id": job_id, "outline": outline.model_dump()})
    return {"job_id": job_id, "outline": outline.model_dump()}


def _get_job(job_id: str) -> dict:
    job = mongo.jobs().find_one({"_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/jobs/{job_id}/outline")
def get_outline(job_id: str) -> dict:
    return _get_job(job_id)["outline"]


@router.post("/jobs/{job_id}/outline/approve")
def approve_outline(job_id: str, override: Outline | None = None) -> dict:
    """Approve the current outline, or replace it with an overridden one."""
    job = _get_job(job_id)
    outline = override.model_dump() if override else job["outline"]
    outline["approved"] = True
    mongo.jobs().update_one(
        {"_id": job_id}, {"$set": {"outline": outline, "status": "approved"}}
    )
    return {"job_id": job_id, "approved": True, "n_sections": len(outline["sections"])}


def _execute_run(job: dict) -> dict:
    """§8 lifecycle: approved/failed -> running -> done | failed (with reason)."""
    job_id = job["_id"]

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
    mongo.jobs().update_one(
        {"_id": job_id},
        {"$set": {"status": "running", "audit.model_id": get_settings().model_id,
                  "audit.started_at": now()}},
    )
    add_message(job.get("session_id"), "drafting_live", {"job_id": job_id})
    try:
        app = build_app(job_id=job_id, sections=job["outline"]["sections"],
                        session_id=job.get("session_id"))
        document = run_to_completion(app)
    except Exception as e:  # noqa: BLE001 — loop boundary: any failure marks the job
        mongo.jobs().update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "error": {"where": "run", "message": str(e)}}},
        )
        raise HTTPException(status_code=500, detail=f"run failed: {e}") from e
    mongo.jobs().update_one(
        {"_id": job_id},
        {"$set": {"status": "done", "document": document, "error": None,
                  "audit.finished_at": now()}},
    )
    sections = list(mongo.drafted_sections().find({"job_id": job_id}, {"_id": 0}))
    n_citations = sum(len(s.get("citations", [])) for s in sections)
    add_message(job.get("session_id"), "document_ready", {
        "job_id": job_id,
        "n_sections": len(job["outline"]["sections"]),
        "n_citations": n_citations,
        "n_flagged": sum(1 for s in sections if s.get("needs_review")),
    })
    return {"job_id": job_id, "status": "done"}


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str) -> dict:
    job = _get_job(job_id)
    if not job["outline"].get("approved"):
        raise HTTPException(status_code=409, detail="outline not approved")
    if job.get("status") not in ("approved", "failed"):
        raise HTTPException(status_code=409, detail=f"job status: {job.get('status')}")
    return _execute_run(job)


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    """§8: continue a failed (or crashed mid-'running') job from its last
    Burr checkpoint; already-committed sections dedupe on re-commit."""
    job = _get_job(job_id)
    if job.get("status") not in ("failed", "running"):
        raise HTTPException(status_code=409, detail=f"job status: {job.get('status')}")
    return _execute_run(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = _get_job(job_id)
    return {"job_id": job_id, "status": job.get("status"),
            "error": job.get("error"), "audit": job.get("audit"),
            "session_id": job.get("session_id")}


@router.get("/jobs/{job_id}/document")
def get_document(job_id: str) -> dict:
    job = _get_job(job_id)
    if job.get("status") != "done":
        raise HTTPException(status_code=409, detail=f"job status: {job.get('status')}")
    return {"job_id": job_id, "document": job["document"]}


@router.get("/jobs/{job_id}/sections")
def get_sections(job_id: str) -> dict:
    """Structured drafted sections (text + citations) for the UI replay animation.

    The stitched `document` string loses per-citation quotes; the frontend pipeline
    viz replays from this structured shape instead.
    """
    job = _get_job(job_id)
    if job.get("status") != "done":
        raise HTTPException(status_code=409, detail=f"job status: {job.get('status')}")
    # Committed sections live in Mongo, scoped to this job; order by the outline.
    by_id = {
        d["section_id"]: d
        for d in mongo.drafted_sections().find({"job_id": job_id}, {"_id": 0})
    }
    ordered = []
    for sec in job["outline"]["sections"]:
        d = by_id.get(sec["section_id"])
        if d:
            # Read-time cleanup: idempotent on v2 rows, repairs legacy v1 rows
            # (inline UUIDs, duplicated headings) without a data migration.
            citations = [Citation(**c) for c in d.get("citations", [])]
            text, citations = clean_section(d.get("text", ""), sec["title"], citations)
            ordered.append(
                {
                    "section_id": sec["section_id"],
                    "title": sec["title"],
                    "instructions": sec.get("instructions", ""),
                    "text": text,
                    "citations": [c.model_dump() for c in citations],
                    "needs_review": d.get("needs_review", False),
                }
            )
    return {"job_id": job_id, "sections": ordered}
