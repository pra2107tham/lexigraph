"""C1 sessions: one session = one conversation = one corpus scope.

The session doc persists the chat timeline (`messages[]`) so a reload restores
the conversation exactly — no client-side job-id bookkeeping.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.stores import mongo

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_message(session_id: str | None, mtype: str, data: dict) -> None:
    """Append a typed message to the session timeline (no-op without a session)."""
    if not session_id:
        return
    mongo.sessions().update_one(
        {"_id": session_id},
        {"$push": {"messages": {"id": str(uuid.uuid4()), "type": mtype, "ts": _now(), "data": data}},
         "$set": {"updated_at": _now()}},
    )


def set_title_once(session_id: str | None, title: str) -> None:
    """Set the auto-generated title if the session still has the placeholder."""
    if session_id and (s := mongo.sessions().find_one({"_id": session_id})):
        if not s.get("title"):
            mongo.sessions().update_one({"_id": session_id}, {"$set": {"title": title}})


@router.post("/sessions")
def create_session() -> dict:
    doc = {"_id": str(uuid.uuid4()), "title": "", "created_at": _now(),
           "updated_at": _now(), "messages": []}
    mongo.sessions().insert_one(doc)
    return {"session_id": doc["_id"], "title": doc["title"], "created_at": doc["created_at"]}


@router.get("/sessions")
def list_sessions() -> dict:
    rows = list(mongo.sessions().find({}, {"messages": 0}))
    rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return {"sessions": [{"session_id": r["_id"], "title": r.get("title", ""),
                          "created_at": r.get("created_at"), "updated_at": r.get("updated_at")}
                         for r in rows]}


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    s = mongo.sessions().find_one({"_id": session_id})
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": s["_id"], "title": s.get("title", ""),
            "created_at": s.get("created_at"), "updated_at": s.get("updated_at"),
            "messages": s.get("messages", [])}
