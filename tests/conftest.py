"""Key-free test fixtures: dict-backed Mongo fake + TestClient with no external dials.

LLM boundaries are patched per-test at OUR function seams (draft_section,
check_claims, generate_outline, …) — never inside Mirascope.
"""

from __future__ import annotations

import copy

import pytest


def _matches(doc: dict, flt: dict) -> bool:
    return all(doc.get(k) == v for k, v in flt.items())


class FakeCollection:
    """The slice of pymongo the app actually uses, backed by a dict on _id."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    def _new_id(self, doc: dict) -> str:
        import uuid

        return str(doc.get("_id") or uuid.uuid4())

    def insert_one(self, doc: dict) -> str:
        doc = copy.deepcopy(doc)
        doc["_id"] = self._new_id(doc)
        self.docs[doc["_id"]] = doc
        return doc["_id"]

    def insert_many(self, docs: list[dict]):
        for d in docs:
            self.insert_one(d)

    def find_one(self, flt: dict, projection: dict | None = None):
        for d in self.docs.values():
            if _matches(d, flt):
                return self._project(d, projection)
        return None

    def find(self, flt: dict | None = None, projection: dict | None = None):
        return [self._project(d, projection) for d in self.docs.values() if _matches(d, flt or {})]

    def _project(self, doc: dict, projection: dict | None):
        doc = copy.deepcopy(doc)
        if projection:
            if all(v in (0, False) for v in projection.values()):
                for k in projection:
                    doc.pop(k, None)
            else:
                keep = {k for k, v in projection.items() if v} | {"_id"}
                doc = {k: v for k, v in doc.items() if k in keep}
                if projection.get("_id") in (0, False):
                    doc.pop("_id", None)
        return doc

    def update_one(self, flt: dict, update: dict, upsert: bool = False):
        doc = next((d for d in self.docs.values() if _matches(d, flt)), None)
        if doc is None:
            if not upsert:
                return
            doc = self.docs[self.insert_one(dict(flt))]
        for key, value in update.get("$set", {}).items():
            target, parts = doc, key.split(".")
            for p in parts[:-1]:
                target = target.setdefault(p, {})
            target[parts[-1]] = copy.deepcopy(value)
        for key, value in update.get("$push", {}).items():
            doc.setdefault(key, []).append(copy.deepcopy(value))

    def replace_one(self, flt: dict, doc: dict, upsert: bool = False):
        existing = next((d for d in self.docs.values() if _matches(d, flt)), None)
        if existing:
            new = {**copy.deepcopy(doc), "_id": existing["_id"]}
            self.docs[existing["_id"]] = new
        elif upsert:
            self.insert_one({**flt, **doc})

    def delete_one(self, flt: dict):
        for _id, d in list(self.docs.items()):
            if _matches(d, flt):
                del self.docs[_id]
                return

    def delete_many(self, flt: dict):
        for _id, d in list(self.docs.items()):
            if _matches(d, flt):
                del self.docs[_id]

    def count_documents(self, flt: dict) -> int:
        return len(self.find(flt))


@pytest.fixture
def fake_db(monkeypatch):
    """Replace every mongo accessor with per-test FakeCollections."""
    from app.stores import mongo

    cols: dict[str, FakeCollection] = {}

    def accessor(name):
        return lambda: cols.setdefault(name, FakeCollection())

    for name in ["documents", "parents", "outlines", "drafted_sections", "jobs", "sessions"]:
        if hasattr(mongo, name):
            monkeypatch.setattr(mongo, name, accessor(name))
    return type("DB", (), {"col": staticmethod(lambda n: cols.setdefault(n, FakeCollection()))})


@pytest.fixture
def client(monkeypatch, fake_db):
    """TestClient whose lifespan skips the Qdrant dial."""
    import app.main as main

    monkeypatch.setattr(main, "ensure_collection", lambda: None)
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
