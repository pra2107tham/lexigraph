"""C1 sessions: CRUD, timeline messages, auto-title, and Qdrant scope filter."""

from app.models import Outline, OutlineSection


def test_session_crud_roundtrip(client):
    sid = client.post("/sessions").json()["session_id"]
    assert client.get("/sessions").json()["sessions"][0]["session_id"] == sid
    full = client.get(f"/sessions/{sid}").json()
    assert full["messages"] == [] and full["title"] == ""
    assert client.get("/sessions/nope").status_code == 404


def test_job_creation_appends_timeline_and_title(client, monkeypatch):
    import app.api.routes as routes

    monkeypatch.setattr(
        routes, "generate_outline",
        lambda job_id, prompt, **kw: Outline(job_id=job_id, sections=[OutlineSection(title="T", instructions="i")]),
    )
    monkeypatch.setattr(routes, "make_title", lambda prompt: "Appointment Letter Summary")

    sid = client.post("/sessions").json()["session_id"]
    res = client.post("/jobs", json={"prompt": "Summarize the letter", "session_id": sid})
    assert res.status_code == 200

    s = client.get(f"/sessions/{sid}").json()
    assert s["title"] == "Appointment Letter Summary"
    assert [m["type"] for m in s["messages"]] == ["user_prompt", "outline_card"]
    assert s["messages"][0]["data"]["text"] == "Summarize the letter"
    assert s["messages"][1]["data"]["outline"]["sections"][0]["title"] == "T"


def test_run_appends_drafting_live_and_document_ready(client, monkeypatch):
    import functools

    import app.api.routes as routes
    import app.drafting.actions as actions
    from app.drafting.graph import build_app
    from app.models import Citation, DraftedSection, ParentChunk
    from app.stores import mongo

    parent = ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="f.pdf", text="Salary is 12 LPA.")
    monkeypatch.setattr(actions, "retrieve", lambda query, top_n=5, **kw: [parent])
    monkeypatch.setattr(actions, "check_claims", lambda pairs: [True] * len(pairs))
    monkeypatch.setattr(
        actions, "draft_section",
        lambda section_id, **kw: DraftedSection(
            section_id=section_id, text="Claim [1].",
            citations=[Citation(parent_id="p1", quote="Salary is 12 LPA", source_file="f.pdf")]),
    )
    import tempfile

    monkeypatch.setattr(routes, "build_app", functools.partial(
        build_app, db_path=tempfile.mktemp(suffix=".db")))

    sid = client.post("/sessions").json()["session_id"]
    mongo.jobs().insert_one(
        {"_id": "job-9", "prompt": "x", "status": "approved", "session_id": sid,
         "outline": {"approved": True,
                     "sections": [{"section_id": "s1", "title": "Salary", "instructions": "i"}]}}
    )
    assert client.post("/jobs/job-9/run").status_code == 200

    types = [m["type"] for m in client.get(f"/sessions/{sid}").json()["messages"]]
    assert types == ["drafting_live", "document_ready"]
    ready = client.get(f"/sessions/{sid}").json()["messages"][-1]["data"]
    assert ready == {"job_id": "job-9", "n_sections": 1, "n_citations": 1, "n_flagged": 0}


def test_hybrid_search_filter_construction(monkeypatch):
    from qdrant_client import models

    import app.retrieval.search as search

    captured = {}

    class _Client:
        def query_points(self, **kwargs):
            captured.update(kwargs)
            return type("R", (), {"points": []})

    monkeypatch.setattr(search, "get_client", lambda: _Client())
    monkeypatch.setattr(search, "embed_query", lambda q: ([0.0], models.SparseVector(indices=[], values=[])))

    search.hybrid_search("q", session_id="sess-1")
    flt = captured["prefetch"][0].filter
    assert flt.must[0].key == "session_id" and flt.must[0].match.value == "sess-1"

    captured.clear()
    search.hybrid_search("q")  # legacy unscoped
    assert captured["prefetch"][0].filter is None
