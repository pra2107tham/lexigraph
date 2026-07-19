"""§7 SSE: exact event order per section, rendered committed payloads,
terminal error frames, and the emit-without-channel no-op."""

import functools
import json

import pytest

from app.drafting import events
from app.models import Citation, DraftedSection, ParentChunk

PARENT = ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="f.pdf", text="Salary is 12 LPA.")
SECTIONS = [{"section_id": "s1", "title": "Salary", "instructions": "cover salary"}]


def _drafted(section_id="s1"):
    return DraftedSection(
        section_id=section_id, text="Claim [1].",
        citations=[Citation(parent_id="p1", quote="Salary is 12 LPA", source_file="f.pdf")])


@pytest.fixture
def sse_env(monkeypatch, fake_db, tmp_path):
    import app.api.routes as routes
    import app.drafting.actions as actions
    import app.retrieval.retriever as retriever
    from app.drafting.graph import build_app
    from app.stores import mongo

    monkeypatch.setattr(retriever, "hybrid_search", lambda *a, **kw: [])
    monkeypatch.setattr(retriever, "dedupe_parents", lambda points: [PARENT])
    monkeypatch.setattr(retriever, "rerank_parents", lambda q, parents, top_n=5: parents)
    monkeypatch.setattr(actions, "check_claims", lambda pairs: [True] * len(pairs))
    monkeypatch.setattr(actions, "draft_section", lambda section_id, **kw: _drafted(section_id))
    monkeypatch.setattr(routes, "build_app",
                        functools.partial(build_app, db_path=str(tmp_path / "burr.db")))
    mongo.jobs().insert_one(
        {"_id": "job-1", "prompt": "x", "status": "approved",
         "outline": {"approved": True, "sections": SECTIONS}})
    return monkeypatch, actions


def _stream_events(client, job_id):
    evs = []
    with client.stream("GET", f"/jobs/{job_id}/run/stream") as res:
        assert res.status_code == 200
        for line in res.iter_lines():
            if line.startswith("data: "):
                evs.append(json.loads(line[6:]))
    return evs


def test_event_order_and_committed_payload(sse_env, client):
    evs = _stream_events(client, "job-1")
    assert [e["type"] for e in evs] == [
        "job_snapshot", "job_start", "section_start", "retrieve_query", "candidates",
        "deduped", "reranked", "draft_start", "draft_done", "evaluate",
        "section_committed", "job_done",
    ]
    committed = next(e for e in evs if e["type"] == "section_committed")
    assert committed["section_id"] == "s1"
    assert committed["data"]["title"] == "Salary"
    assert committed["data"]["text"] == "Claim [1]."
    assert committed["data"]["citations"][0]["verified"] == "quote_verified"
    assert evs[-1]["data"]["document"].startswith("## Salary")


def test_error_frame_and_failed_status(sse_env, client):
    monkeypatch, actions = sse_env

    def boom(**kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(actions, "draft_section", boom)
    evs = _stream_events(client, "job-1")
    assert evs[-1]["type"] == "error"
    assert "provider down" in evs[-1]["data"]["message"]

    from app.stores import mongo

    assert mongo.jobs().find_one({"_id": "job-1"})["status"] == "failed"


def test_emit_without_channel_is_noop():
    events.emit("ghost-job", "draft_start", attempt=1)  # must not raise
    assert not events.is_open("ghost-job")


def test_sse_framing():
    frame = events.sse({"type": "job_done", "data": {}})
    assert frame == 'data: {"type": "job_done", "data": {}}\n\n'
