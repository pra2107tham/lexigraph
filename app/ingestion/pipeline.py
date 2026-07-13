"""End-to-end ingestion: PDF bytes -> parents+children -> MongoDB + Qdrant.

Truth store (MongoDB): raw elements + one document record + every ParentChunk.
Vector store (Qdrant Index A): one point per CHILD, carrying the parent expansion
in its payload so retrieval returns parent context without a second lookup.
"""

from __future__ import annotations

import uuid

from qdrant_client import models

from app.config import get_settings
from app.ingestion.chunking import derive_children
from app.ingestion.partition import partition_pdf
from app.models import ChildChunk, ParentChunk
from app.retrieval.embeddings import embed_dense, embed_sparse
from app.stores import mongo
from app.stores.qdrant import get_client


def _persist_truth(
    mongo_doc_id: str, file_name: str, raw_elements: list[dict], parents: list[ParentChunk]
) -> None:
    mongo.documents().insert_one(
        {
            "_id": mongo_doc_id,
            "source_file": file_name,
            "n_elements": len(raw_elements),
            "raw_elements": raw_elements,
        }
    )
    if parents:
        mongo.parents().insert_many([p.model_dump() for p in parents])


def _persist_vectors(parents: list[ParentChunk], children: list[ChildChunk]) -> int:
    """Embed child texts and upsert them into Index A. Returns points written."""
    if not children:
        return 0
    settings = get_settings()
    parent_by_id = {p.parent_id: p for p in parents}

    texts = [c.text for c in children]
    dense = embed_dense(texts)
    sparse = embed_sparse(texts)

    points = []
    for child, dvec, svec in zip(children, dense, sparse):
        parent = parent_by_id[child.parent_id]
        points.append(
            models.PointStruct(
                id=child.child_id,
                vector={"dense": dvec, "sparse": svec},
                payload={
                    "parent_id": parent.parent_id,
                    "parent_text": parent.text,
                    "mongo_doc_id": parent.mongo_doc_id,
                    "source_file": parent.source_file,
                },
            )
        )
    get_client().upsert(
        collection_name=settings.qdrant_collection, points=points, wait=True
    )
    return len(points)


def ingest_pdf(file_bytes: bytes, file_name: str) -> dict:
    """Ingest one PDF. Returns a summary of what was stored."""
    mongo_doc_id = str(uuid.uuid4())

    parents, raw_elements = partition_pdf(file_bytes, file_name, mongo_doc_id)

    children: list[ChildChunk] = []
    settings = get_settings()
    for parent in parents:
        children.extend(
            derive_children(
                parent,
                target_tokens=settings.child_target_tokens,
                overlap_tokens=settings.child_overlap_tokens,
            )
        )

    _persist_truth(mongo_doc_id, file_name, raw_elements, parents)
    n_points = _persist_vectors(parents, children)

    return {
        "mongo_doc_id": mongo_doc_id,
        "source_file": file_name,
        "n_parents": len(parents),
        "n_children": len(children),
        "n_vectors": n_points,
    }
