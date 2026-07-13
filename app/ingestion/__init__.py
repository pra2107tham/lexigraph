"""Ingestion pipeline: partition PDFs -> parent chunks -> derived children -> stores.

Import `ingest_pdf` from `app.ingestion.pipeline` directly. We intentionally do
not re-export it here so that lightweight modules (e.g. chunking) stay importable
without pulling in the qdrant/fastembed stack.
"""
