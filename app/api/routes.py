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

from typing import Annotated
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.drafting.graph import build_app, run_to_completion
from app.drafting.outline import generate_outline
from app.ingestion.pipeline import ingest_pdf
from app.models import Outline
from app.stores import mongo

router = APIRouter()


# ---- documents -----------------------------------------------------------

@router.post("/documents")
async def upload_documents(files: list[UploadFile]) -> dict:
    results = []
    for f in files:
        content = await f.read()
        results.append(ingest_pdf(content, f.filename or "upload.pdf"))
    return {"ingested": results}


# ---- jobs ----------------------------------------------------------------

class CreateJob(BaseModel):
    prompt: str  # e.g. "Draft a Master Services Agreement for ..."


@router.post("/jobs")
def create_job(body: CreateJob) -> dict:
    job_id = str(uuid.uuid4())
    outline = generate_outline(job_id, body.prompt)
    mongo.jobs().insert_one(
        {"_id": job_id, "prompt": body.prompt, "outline": outline.model_dump(),
         "status": "outline_pending"}
    )
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


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str) -> dict:
    job = _get_job(job_id)
    outline = job["outline"]
    if not outline.get("approved"):
        raise HTTPException(status_code=409, detail="outline not approved")

    app = build_app(job_id=job_id, sections=outline["sections"])
    document = run_to_completion(app)
    mongo.jobs().update_one(
        {"_id": job_id}, {"$set": {"status": "done", "document": document}}
    )
    return {"job_id": job_id, "status": "done"}


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
            ordered.append(
                {
                    "section_id": sec["section_id"],
                    "title": sec["title"],
                    "instructions": sec.get("instructions", ""),
                    "text": d.get("text", ""),
                    "citations": d.get("citations", []),
                    "needs_review": d.get("needs_review", False),
                }
            )
    return {"job_id": job_id, "sections": ordered}
