"""Connectivity check — verifies each external service independently.

Run BEFORE the full pipeline so a bad key/URL/region surfaces here, per-service,
instead of as an opaque 500 mid-flow.

    ./run.sh --no-install     # (in one shell, to build the venv) — or just:
    source .venv/bin/activate
    python scripts/check_connections.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/check_connections.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings

OK, FAIL = "  ✓", "  ✗"


def _try(name: str, fn) -> bool:
    try:
        detail = fn()
        print(f"{OK} {name}: {detail}")
        return True
    except Exception as e:  # noqa: BLE001 — we want the message, whatever it is
        print(f"{FAIL} {name}: {type(e).__name__}: {str(e)[:160]}")
        return False


def check_mongo() -> str:
    from app.stores.mongo import get_db

    db = get_db()
    db.command("ping")
    return f"connected to db '{db.name}'"


def check_qdrant() -> str:
    from app.stores.qdrant import ensure_collection, get_client

    ensure_collection()
    cols = [c.name for c in get_client().get_collections().collections]
    return f"reachable; collections={cols}"


def check_cohere() -> str:
    from app.retrieval.rerank import _client

    r = _client().rerank(
        model=get_settings().cohere_rerank_model,
        query="net payment terms",
        documents=["Payment is Net 30.", "The sky is blue."],
        top_n=1,
    )
    return f"rerank OK; top doc index={r.results[0].index}"


def check_openrouter() -> str:
    from app.drafting.llm import _model, _user

    _model().call([_user("Reply with the single word: ok")])
    return f"model responded ({get_settings().model_id})"


def check_embeddings() -> str:
    from app.retrieval.embeddings import embed_query

    dense, sparse = embed_query("payment terms")
    return f"dense dim={len(dense)}, sparse nnz={len(sparse.indices)}"


def check_unstructured() -> str:
    # No cheap no-op ping; just confirm the client constructs with the configured
    # key/url. A real partition happens during ingestion.
    from app.ingestion.partition import _client

    _client()
    s = get_settings()
    return f"client constructed (url={s.unstructured_api_url})"


def main() -> int:
    print("LexiGraph connectivity check\n" + "-" * 32)
    results = [
        _try("Embeddings (local fastembed)", check_embeddings),
        _try("MongoDB Atlas", check_mongo),
        _try("Qdrant Cloud", check_qdrant),
        _try("Cohere rerank", check_cohere),
        _try("OpenRouter LLM", check_openrouter),
        _try("Unstructured (client only)", check_unstructured),
    ]
    print("-" * 32)
    n_ok = sum(results)
    print(f"{n_ok}/{len(results)} checks passed")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
