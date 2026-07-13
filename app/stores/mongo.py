"""MongoDB Atlas — the system of record (truth store).

Collections:
  documents        raw ingested elements + doc metadata
  parents          ParentChunk records (looked up by parent_id at draft time)
  outlines         per-job outlines (with approval state)
  drafted_sections committed sections from the Burr loop
"""

from __future__ import annotations

from functools import lru_cache

import certifi
from pymongo import MongoClient
from pymongo.database import Database

from app.config import get_settings


@lru_cache
def get_db() -> Database:
    """Cached MongoDB database handle for the configured database.

    Pass certifi's CA bundle explicitly — on macOS the system Python often can't
    find the CA roots to validate Atlas's TLS cert, which otherwise fails with
    'CERTIFICATE_VERIFY_FAILED'.
    """
    settings = get_settings()
    client: MongoClient = MongoClient(
        settings.mongodb_uri, tlsCAFile=certifi.where()
    )
    return client[settings.mongodb_db]


# Convenience collection accessors — thin, so services read intent not strings.
def documents():
    return get_db()["documents"]


def parents():
    return get_db()["parents"]


def outlines():
    return get_db()["outlines"]


def drafted_sections():
    return get_db()["drafted_sections"]


def jobs():
    return get_db()["jobs"]
