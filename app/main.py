"""FastAPI entrypoint.

Ensures the Qdrant collection exists on startup, then exposes a health check.
Route modules (documents, jobs) are wired in later build steps.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.stores.qdrant import ensure_collection

# Built frontend bundle (vite build -> here). Optional: the API runs without it.
_FRONTEND_DIST = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Index A must exist before any ingest/retrieve. Idempotent.
    ensure_collection()
    yield


app = FastAPI(title="LexiGraph RAG", version="0.1.0", lifespan=lifespan)
app.include_router(router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    if "components" in openapi_schema and "schemas" in openapi_schema["components"]:
        for schema in openapi_schema["components"]["schemas"].values():
            for prop in schema.get("properties", {}).values():
                if prop.get("type") == "array" and "items" in prop:
                    items = prop["items"]
                    if items.get("type") == "string" and items.get("contentMediaType"):
                        items["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "model_id": settings.model_id,
        "collection": settings.qdrant_collection,
    }


# Serve the built SPA at / when present (prod/test). Mounted LAST so explicit API
# routes (/health, /documents, /jobs/...) always match before the catch-all.
# In dev, run the Vite server instead; it proxies /documents and /jobs to :8000.
if (_FRONTEND_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
