"""FastAPI entrypoint.

Ensures the Qdrant collection exists on startup, then exposes a health check.
Route modules (documents, jobs) are wired in later build steps.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.stores.qdrant import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Index A must exist before any ingest/retrieve. Idempotent.
    ensure_collection()
    yield


app = FastAPI(title="LexiGraph RAG", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "model_id": settings.model_id,
        "collection": settings.qdrant_collection,
    }
