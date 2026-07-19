"""§8 lifecycle: failure marks the job, resume continues from the checkpoint
without duplicating committed sections, audit metadata lands on the job."""

import functools

import pytest

from app.models import Citation, DraftedSection, ParentChunk

PARENT = ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="letter.pdf", text="Salary is 12 LPA. Notice is 60 days.")
SECTIONS = [
    {"section_id": f"s{i}", "title": t, "instructions": f"cover {t}"}
    for i, t in enumerate(["Salary", "Notice"], start=1)
]


def _drafted(section_id):
    return DraftedSection(
        section_id=section_id,
        text="Grounded claim [1].",
        citations=[Citation(parent_id="p1", quote="Salary is 12 LPA", source_file="letter.pdf")],
    )


@pytest.fixture
def lifecycle_env(monkeypatch, fake_db, tmp_path):
    import app.api.routes as routes
    import app.drafting.actions as actions
    from app.drafting.graph import build_app
    from app.stores import mongo

    monkeypatch.setattr(actions, "retrieve", lambda query, top_n=5, **kw: [PARENT])
    monkeypatch.setattr(actions, "check_claims", lambda pairs: [True] * len(pairs))
    monkeypatch.setattr(
        routes, "build_app", functools.partial(build_app, db_path=str(tmp_path / "burr.db"))
    )
    mongo.jobs().insert_one(
        {"_id": "job-1", "prompt": "x", "status": "approved",
         "outline": {"approved": True, "sections": SECTIONS}}
    )
    return monkeypatch, actions, mongo


def test_failure_then_resume_dedupes(lifecycle_env, client):
    monkeypatch, actions, mongo = lifecycle_env

    def draft_fail_on_s2(section_id, **kw):
        if section_id == "s2":
            raise RuntimeError("provider exploded")
        return _drafted(section_id)

    monkeypatch.setattr(actions, "draft_section", draft_fail_on_s2)
    res = client.post("/jobs/job-1/run")
    assert res.status_code == 500

    job = mongo.jobs().find_one({"_id": "job-1"})
    assert job["status"] == "failed"
    assert job["error"] == {"where": "run", "message": "provider exploded"}
    assert len(mongo.drafted_sections().find({"job_id": "job-1"})) == 1  # s1 committed

    # heal the provider and resume: continues from the checkpoint, no duplicates
    monkeypatch.setattr(actions, "draft_section", lambda section_id, **kw: _drafted(section_id))
    res = client.post("/jobs/job-1/resume")
    assert res.status_code == 200 and res.json()["status"] == "done"

    job = mongo.jobs().find_one({"_id": "job-1"})
    assert job["status"] == "done" and job["error"] is None
    rows = mongo.drafted_sections().find({"job_id": "job-1"})
    assert sorted(r["section_id"] for r in rows) == ["s1", "s2"]  # deduped
    assert set(job["audit"]["per_section"]) == {"s1", "s2"}
    assert job["audit"]["started_at"] and job["audit"]["finished_at"] and job["audit"]["model_id"]


def test_run_guards_status(lifecycle_env, client):
    _, actions, mongo = lifecycle_env
    mongo.jobs().update_one({"_id": "job-1"}, {"$set": {"status": "done"}})
    assert client.post("/jobs/job-1/run").status_code == 409
    assert client.post("/jobs/job-1/resume").status_code == 409


def test_get_job_status(lifecycle_env, client):
    res = client.get("/jobs/job-1")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
