"""C2 document removal (Mongo + Qdrant cascade) and C3 revision turns."""

import pytest

from app.models import Citation, DraftedSection, ParentChunk

PARENT = ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="letter.pdf",
                     text="The notice period is sixty days.")


@pytest.fixture
def done_job(fake_db):
    from app.stores import mongo

    sections = [{"section_id": f"s{i}", "title": t, "instructions": "i"}
                for i, t in enumerate(["Salary", "Notice"], start=1)]
    mongo.jobs().insert_one({"_id": "job-1", "prompt": "x", "status": "done",
                             "session_id": "sess-1", "document": "old",
                             "outline": {"approved": True, "sections": sections}})
    for s in sections:
        mongo.drafted_sections().insert_one(
            {"job_id": "job-1", "section_id": s["section_id"], "title": s["title"],
             "text": "Old text [1].",
             "citations": [{"parent_id": "p1", "quote": "sixty days", "source_file": "letter.pdf"}],
             "needs_review": False})
    return mongo


def test_revise_section_replaces_row_and_rebuilds_document(done_job, client, monkeypatch):
    import app.drafting.revision as revision

    monkeypatch.setattr(revision, "retrieve", lambda *a, **kw: [PARENT])
    monkeypatch.setattr(revision, "check_claims", lambda pairs: [True] * len(pairs))
    captured = {}

    def fake_draft(section_id, instructions, feedback, **kw):
        captured.update(instructions=instructions, feedback=feedback)
        return DraftedSection(
            section_id=section_id, text="Stricter notice terms [1].",
            citations=[Citation(parent_id="p1", quote="notice period is sixty days",
                                source_file="letter.pdf")])

    monkeypatch.setattr(revision, "draft_section", fake_draft)

    sid = client.post("/sessions").json()["session_id"]
    done_job.jobs().update_one({"_id": "job-1"}, {"$set": {"session_id": sid}})

    res = client.post("/jobs/job-1/sections/s2/revise", json={"instructions": "stricter on notice"})
    assert res.status_code == 200
    assert res.json()["section"]["text"] == "Stricter notice terms [1]."
    assert "REVISION REQUEST: stricter on notice" in captured["instructions"]
    assert "CURRENT TEXT" in captured["feedback"]

    rows = done_job.drafted_sections().find({"job_id": "job-1", "section_id": "s2"})
    assert len(rows) == 1  # replaced, not duplicated
    assert rows[0]["citations"][0]["verified"] == "quote_verified"

    job = done_job.jobs().find_one({"_id": "job-1"})
    assert "Stricter notice terms" in job["document"]
    assert job["document"].index("## Salary") < job["document"].index("## Notice")

    msgs = client.get(f"/sessions/{sid}").json()["messages"]
    assert msgs[-1]["type"] == "revision"
    assert msgs[-1]["data"]["section_id"] == "s2"


def test_revise_requires_done_job(done_job, client):
    done_job.jobs().update_one({"_id": "job-1"}, {"$set": {"status": "running"}})
    assert client.post("/jobs/job-1/sections/s1/revise", json={"instructions": "x"}).status_code == 409


def test_delete_document_cascades(client, fake_db, monkeypatch):
    from app.stores import mongo

    captured = {}

    class _Client:
        def delete(self, collection_name, points_selector):
            captured["filter"] = points_selector.filter

    import app.api.sessions as sessions_mod

    monkeypatch.setattr("app.stores.qdrant.get_client", lambda: _Client())
    assert sessions_mod  # imported for patch clarity

    mongo.documents().insert_one({"_id": "d1", "session_id": "sess-1", "source_file": "f.pdf"})
    mongo.parents().insert_many([{"parent_id": "p1", "mongo_doc_id": "d1"},
                                 {"parent_id": "p2", "mongo_doc_id": "d1"}])

    res = client.delete("/sessions/sess-1/documents/d1")
    assert res.status_code == 200 and res.json()["deleted"] == "d1"
    assert mongo.documents().find_one({"_id": "d1"}) is None
    assert mongo.parents().find({"mongo_doc_id": "d1"}) == []
    cond = captured["filter"].must[0]
    assert cond.key == "mongo_doc_id" and cond.match.value == "d1"

    assert client.delete("/sessions/sess-1/documents/ghost").status_code == 404
