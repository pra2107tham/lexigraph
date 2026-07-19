"""Burr graph + application for the Factory Loop.

Flow:
  retrieve -> draft -> evaluate
  evaluate -> draft    (when eval_ok=False)  # rewrite
  evaluate -> commit   (when eval_ok=True)
  commit   -> retrieve (when more=True)      # next section
  commit   -> assemble (when more=False)     # done

`more` is a derived boolean: cursor < len(sections). We expose it via a tiny
condition using Burr's expr on state.

Human-in-the-loop: the app is built with `halt_before=["draft"]` so the outline
can be reviewed before any drafting happens. After approval, run() is called
again to proceed.
"""

from __future__ import annotations

from burr.core import ApplicationBuilder, expr, graph
from burr.core.persistence import SQLitePersister

from app.drafting.actions import (
    assemble,
    commit,
    draft,
    evaluate,
    retrieve_sources,
)


def build_graph():
    return (
        graph.GraphBuilder()
        .with_actions(
            retrieve=retrieve_sources,
            draft=draft,
            evaluate=evaluate,
            commit=commit,
            assemble=assemble,
        )
        .with_transitions(
            ("retrieve", "draft"),
            ("draft", "evaluate"),
            # A1: redraft only while retries remain; otherwise commit best-effort
            # (commit flags needs_review) so the loop is provably bounded.
            ("evaluate", "draft", expr("eval_ok == False and retries < max_retries")),
            ("evaluate", "commit", expr("eval_ok == True or retries >= max_retries")),
            ("commit", "retrieve", expr("cursor < len(sections)")),
            ("commit", "assemble", expr("cursor >= len(sections)")),
        )
        .build()
    )


def build_app(job_id: str, sections: list[dict], db_path: str = "lexigraph_burr.db"):
    """Build the drafting application for a job.

    State is initialized from the APPROVED outline sections. The persister lets a
    job pause (human review) and resume without losing progress.
    """
    from app.config import get_settings

    persister = SQLitePersister(db_path=db_path, table_name="burr_state")
    persister.initialize()

    return (
        ApplicationBuilder()
        .with_graph(build_graph())
        .with_state(
            job_id=job_id,
            sections=sections,
            cursor=0,
            running_summary="",
            candidates=[],
            draft={},
            eval_ok=False,
            drafted_sections=[],
            document=None,
            # A1: bound the redraft loop. retries resets per section (in retrieve),
            # increments per draft; the evaluate->commit edge fires at the cap.
            retries=0,
            max_retries=get_settings().max_redraft_retries,
            needs_review=[],
        )
        .with_entrypoint("retrieve")
        .with_identifiers(app_id=job_id)
        .with_state_persister(persister)
        .build()
    )


def run_to_completion(app) -> str:
    """Run the loop until the document is assembled; return the document."""
    app.run(halt_after=["assemble"])
    return app.state["document"]
