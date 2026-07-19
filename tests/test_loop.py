"""Full Burr loop with patched externals: targeted redrafts + retry cap."""

import pytest

from app.models import Citation, DraftedSection, ParentChunk

PARENT = ParentChunk(parent_id="p1", mongo_doc_id="d1", source_file="letter.pdf", text="Salary is 12 LPA per annum.")
SECTIONS = [{"section_id": "s1", "title": "Salary", "instructions": "cover salary"}]


def _drafted(quote):
    return DraftedSection(
        section_id="s1",
        text="Salary is 12 LPA [1].",
        citations=[Citation(parent_id="p1", quote=quote, source_file="letter.pdf")],
    )


@pytest.fixture
def loop_env(monkeypatch, fake_db, tmp_path):
    import app.drafting.actions as actions

    monkeypatch.setattr(actions, "retrieve", lambda query, top_n=5, **kw: [PARENT])
    monkeypatch.setattr(actions, "check_claims", lambda pairs: [True] * len(pairs))

    def run(draft_fn):
        from app.drafting.graph import build_app, run_to_completion

        monkeypatch.setattr(actions, "draft_section", draft_fn)
        app = build_app("job-1", SECTIONS, db_path=str(tmp_path / "burr.db"))
        run_to_completion(app)
        return app

    return run


def test_tier1_failure_triggers_targeted_redraft(loop_env):
    calls = []

    def draft_fn(**kwargs):
        calls.append(kwargs["feedback"])
        # first attempt fabricates the quote; the retry quotes verbatim
        return _drafted("made-up text" if len(calls) == 1 else "Salary is 12 LPA")

    app = loop_env(draft_fn)
    assert len(calls) == 2
    assert calls[0] == ""  # first attempt drafts blind
    assert "citation [1]" in calls[1] and "quote not found" in calls[1]  # redraft is targeted
    assert app.state["needs_review"] == []
    assert app.state["draft"]["citations"][0]["verified"] == "quote_verified"


def test_retry_cap_commits_flagged(loop_env, fake_db):
    from app.stores import mongo

    always_bad = lambda **kw: _drafted("never in the source")
    app = loop_env(always_bad)
    assert app.state["needs_review"] == ["s1"]
    rows = mongo.drafted_sections().find({"job_id": "job-1"})
    assert len(rows) == 1 and rows[0]["needs_review"] is True
