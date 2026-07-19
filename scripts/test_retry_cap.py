"""A1 self-check: the redraft loop is bounded and flags needs_review.

Runs the Burr graph with drafting + evaluation + Mongo commit all stubbed, so it
exercises ONLY the loop's control flow — no external services. Fails if the
evaluate->draft loop can run more than max_retries drafts (i.e. could spin).

    python scripts/test_retry_cap.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.drafting import actions
from app.drafting.graph import build_graph
from burr.core import ApplicationBuilder


def _run(monkey_grounded: bool, max_retries: int = 3):
    """Build an app with stubs; return (n_drafts, needs_review, doc_present)."""
    calls = {"draft": 0}

    # Stub draft: no LLM, just a fake section citing a real candidate parent_id.
    def fake_draft(state):
        calls["draft"] += 1
        sec = state["sections"][state["cursor"]]
        return state.update(
            draft={
                "section_id": sec["section_id"],
                "text": "stub text",
                "citations": [{"parent_id": "p1", "quote": "q"}],
            },
            retries=state["retries"] + 1,
        )

    def fake_retrieve(state):
        return state.update(
            candidates=[{"parent_id": "p1", "parent_text": "t", "mongo_doc_id": "",
                         "source_file": "f", "text": "t"}],
            retries=0,
        )

    def fake_evaluate(state):
        # grounded toggled by the test; parent_id p1 IS a candidate, so only the
        # groundedness check decides pass/fail.
        return state.update(eval_ok=monkey_grounded)

    committed = {"needs_review": None}

    def fake_commit(state):
        sec = state["sections"][state["cursor"]]
        flagged = not state["eval_ok"]
        committed["needs_review"] = flagged
        return state.update(
            drafted_sections=state["drafted_sections"] + [state["draft"]],
            cursor=state["cursor"] + 1,
            running_summary="",
            needs_review=state["needs_review"] + ([sec["section_id"]] if flagged else []),
        )

    # Patch the action functions the graph references.
    orig = (actions.retrieve_sources, actions.draft, actions.evaluate, actions.commit)
    actions.retrieve_sources.run = fake_retrieve  # type: ignore
    # Simpler: rebuild the graph with our stubs via with_actions override.
    from burr.core import action as burr_action

    g = build_graph()
    # Replace the action implementations on the built graph's action map.
    for a in g.actions:
        if a.name == "retrieve":
            a._fn = fake_retrieve  # type: ignore[attr-defined]
        elif a.name == "draft":
            a._fn = fake_draft  # type: ignore[attr-defined]
        elif a.name == "evaluate":
            a._fn = fake_evaluate  # type: ignore[attr-defined]
        elif a.name == "commit":
            a._fn = fake_commit  # type: ignore[attr-defined]

    app = (
        ApplicationBuilder()
        .with_graph(g)
        .with_state(
            job_id="t", sections=[{"section_id": "s1", "title": "T", "instructions": "i"}],
            cursor=0, running_summary="", candidates=[], draft={}, eval_ok=False,
            drafted_sections=[], document=None,
            retries=0, max_retries=max_retries, needs_review=[],
        )
        .with_entrypoint("retrieve")
        .build()
    )
    app.run(halt_after=["assemble"])
    actions.retrieve_sources, actions.draft, actions.evaluate, actions.commit = orig
    return calls["draft"], committed["needs_review"]


def main() -> int:
    # Case 1: always ungrounded -> loop must stop at exactly max_retries drafts,
    # and the section must be flagged needs_review. If unbounded, this hangs.
    n_drafts, flagged = _run(monkey_grounded=False, max_retries=3)
    assert n_drafts == 3, f"expected 3 bounded drafts, got {n_drafts}"
    assert flagged is True, "ungrounded section should be flagged needs_review"

    # Case 2: grounded on attempt 1 -> single draft, not flagged.
    n_ok, flagged_ok = _run(monkey_grounded=True, max_retries=3)
    assert n_ok == 1, f"expected 1 draft on clean path, got {n_ok}"
    assert flagged_ok is False, "grounded section must not be flagged"

    print("OK: redraft loop bounded (3 drafts, flagged) + clean path (1 draft)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
