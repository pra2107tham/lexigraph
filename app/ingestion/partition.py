"""Partition a PDF into parent chunks via the Unstructured serverless API.

`chunking_strategy="by_title"` produces layout-aware CompositeElements that respect
document structure (multi-column contracts, tables) — each becomes one ParentChunk.
"""

from __future__ import annotations

from unstructured_client import UnstructuredClient
from unstructured_client.models import operations, shared

from app.config import get_settings
from app.models import ParentChunk


def _client() -> UnstructuredClient:
    settings = get_settings()
    return UnstructuredClient(
        api_key_auth=settings.unstructured_api_key,
        server_url=settings.unstructured_api_url,
    )


def partition_pdf(
    file_bytes: bytes, file_name: str, mongo_doc_id: str
) -> tuple[list[ParentChunk], list[dict]]:
    """Return (parent_chunks, raw_elements).

    raw_elements is the untouched Unstructured output, kept in the truth store.
    """
    settings = get_settings()
    client = _client()

    resp = client.general.partition(
        request=operations.PartitionRequest(
            partition_parameters=shared.PartitionParameters(
                files=shared.Files(content=file_bytes, file_name=file_name),
                strategy=shared.Strategy.HI_RES,
                chunking_strategy="by_title",
                max_characters=settings.parent_max_chars,
                combine_under_n_chars=500,
                overlap=50,
            )
        )
    )

    raw_elements = resp.elements or []
    parents: list[ParentChunk] = []
    for el in raw_elements:
        text = (el.get("text") or "").strip()
        if not text:
            continue
        meta = el.get("metadata") or {}
        parents.append(
            ParentChunk(
                mongo_doc_id=mongo_doc_id,
                text=text,
                page_number=meta.get("page_number"),
                source_file=file_name,
            )
        )
    return parents, raw_elements
