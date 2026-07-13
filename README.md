# LexiGraph RAG (MVP)

Agentic RAG that ingests legal precedent PDFs and drafts short, citation-grounded
multi-section documents. Built as a Planner–Drafter–Evaluator loop over a
parent-child hybrid retrieval index.

## Stack
- **API:** FastAPI
- **Ingestion:** Unstructured.io (serverless) → parent chunks → derived child chunks
- **Truth store:** MongoDB Atlas
- **Vector store:** Qdrant Cloud (Index A) — native dense+sparse RRF hybrid search
- **Reranker:** Cohere Rerank v3.5
- **Orchestration:** Apache Burr (state machine, human-in-the-loop pause/resume)
- **LLM:** via **OpenRouter** (OpenAI-compatible) — model is a config value (`MODEL_ID`), swappable

## Scope (v1)
Parent-child chunking + hybrid search + rerank + a Burr drafting loop producing a
~5–10 section document with paragraph-level citations. Dual-index rolling memory
(Index B) and the CRAG entailment evaluator are deferred to Phase 2.

Full design, data-flow diagrams, HLD and LLD:
`~/.claude/plans/i-am-trying-to-lively-cat.md` (approved plan).

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in keys
uvicorn app.main:app --reload
```
