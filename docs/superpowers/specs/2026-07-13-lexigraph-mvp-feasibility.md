# LexiGraph RAG — MVP Feasibility & Design

**Date:** 2026-07-13
**Status:** Draft (feasibility assessment + v1 scope)

## Context

The user has a detailed architecture doc for **LexiGraph**, an agentic RAG system that
ingests legal precedent documents and drafts long, citation-grounded legal documents
(MSAs, M&A contracts). They asked one question: **is this doable?**

Short answer: **yes, the architecture is sound and every named technology is real and
currently maintained.** The load-bearing capabilities were verified against current docs
(via Context7): Apache Burr supports explicit pause/resume + human-in-the-loop; Qdrant has
native server-side Reciprocal Rank Fusion for dense+sparse hybrid search; Unstructured.io,
Mirascope, and Cohere Rerank all exist and are documented.

But the doc has correctness problems that would waste effort if built as-written, and it
tries to build ~3 substantial subsystems at once. This spec scopes a **working end-to-end
MVP** (the user's chosen goal) and records the corrections.

## Corrections to the original doc

1. **Model choices are outdated.** The doc names **Claude 3.5 Sonnet** as primary LLM and
   `text-embedding-3-small` for embeddings. As of 2026-07, Claude 3.5 Sonnet is retired /
   not in the current catalog. Use **`claude-opus-4-8`** as the drafter/evaluator model
   (`claude-fable-5` optional for the hardest drafting). Prompt caching (the doc's cost
   lever) works as hoped: cache the system prompt + definitions + outline and pay ~0.1×
   on cache reads.
2. **Self-RAG "reflection tokens" (§3.4) is mis-stated.** You are not fine-tuning a hosted
   model to emit `[RETRIEVE]` tokens. The equivalent, and far simpler, mechanism is
   **tool-calling**: give the Drafter a `retrieve(query)` tool; when it calls the tool the
   state machine pauses, fetches, and resumes. Same behavior, no fine-tuning.
3. **Scope.** Ingestion, retrieval/rerank, and the Burr drafting loop are each a real
   project. The doc conflates them into one build. This spec builds a thin slice through
   all three, then defers the scale features.

## v1 Scope (what we build)

**In scope (user-selected):**
- Ingestion: Unstructured.io → parent/child chunking → MongoDB (truth) + Qdrant Index A.
- **Parent-child hierarchical retrieval**: embed 256-tok child chunks, return ~1000-tok
  parent chunks to the LLM.
- **Hybrid search + rerank**: Qdrant dense+sparse RRF (`query_points` with `prefetch` +
  `FusionQuery(RRF)`) → Cohere Rerank v3.5 → top-5.
- Burr state machine: `Retrieve → Draft → Evaluate → Commit`, looping over an
  **approved outline** to produce a **short multi-section document** (≈5–10 sections)
  with paragraph-level citations.
- Human-in-the-loop "Plan Mode": user approves the JSON outline before drafting
  (Burr `halt_before` the drafting loop).

**Deferred to Phase 2 (documented, not built):**
- **Index B / dual-index rolling memory** (episodic summaries of prior chapters). This is
  what unlocks the 100-page claim; without it, v1 keeps the outline + a running summary in
  context and targets a short document. The state is designed so adding Index B is an
  extension, not a rewrite.
- **CRAG entailment evaluator** as a separate rewrite-forcing node. v1 uses a lighter
  citation check (drafter must cite a real `parent_id`; a basic groundedness check can be
  added). Full entailment loop is Phase 2.

## Architecture (v1)

### Tech stack (corrected)
| Component | Technology | Notes |
|---|---|---|
| Ingestion | Unstructured.io (serverless) | `chunk_by_title`, layout-aware |
| Truth store | MongoDB Atlas | raw JSON, docs, outlines, drafted sections |
| Vector DB | Qdrant Cloud | Index A only in v1; native RRF hybrid |
| Reranker | Cohere Rerank v3.5 | top-50 → top-5 |
| Orchestration | Apache Burr | explicit state machine, pause/resume |
| LLM interface | Mirascope | Pydantic-typed calls |
| **Primary LLM** | **`claude-opus-4-8`** | **corrected from Claude 3.5 Sonnet** |
| Embeddings | pick current model at build time | **corrected from text-embedding-3-small** |
| API | FastAPI | upload + job endpoints |

### Ingestion flow (Phase 1)
`Upload PDFs → Unstructured.io (chunk_by_title) → build parent (~1000 tok) + child
(~256 tok) chunks → save raw JSON + metadata to MongoDB (get mongo_doc_ids) → embed child
chunks → upsert child vectors to Qdrant Index A with payload {parent_text, parent_id,
mongo_doc_id}.`

### Drafting loop (Phase 2 of build — the Factory Loop)
Burr state machine, initialized from an **approved** JSON outline:
```
[approved outline] → Burr init → (halt_before draft: human approves)
  loop over sections:
    Retrieve  → Qdrant Index A hybrid (dense+sparse RRF) → Cohere rerank top-5
    Draft     → claude-opus-4-8 via Mirascope; may call retrieve() tool (active retrieval)
    Evaluate  → citation check (cited parent_id exists / groundedness); fail → back to Draft
    Commit    → save section to MongoDB
  more sections? → yes: next section; no: assemble final document
```

## Key reused/native capabilities (don't reinvent)

- **Qdrant native RRF**: `client.query_points(collection, prefetch=[Prefetch(dense, using="dense", limit=50), Prefetch(sparse_vec, using="sparse", limit=50)], query=FusionQuery(fusion=Fusion.RRF), limit=10)`. Do not hand-roll fusion.
- **Burr pause/resume**: `ApplicationBuilder().with_graph(...).initialize_from(tracker, resume_at_next_action=True, ...)`; `halt_before=["draft"]` for the human approval gate; persisters (SQLite/Postgres/Redis) for state.
- **Anthropic prompt caching**: `cache_control: {"type": "ephemeral"}` on the system prompt / definitions / outline blocks; verify hits via `usage.cache_read_input_tokens`.
- **Active retrieval = tool use**, not fine-tuned reflection tokens: define a `retrieve` tool on the drafter and handle the tool call in the Burr loop.

## Verification (how we'll know each slice works)

1. **Ingestion**: upload 2–3 sample legal PDFs; assert MongoDB has raw JSON + parent chunks
   and Qdrant Index A has child vectors whose payload carries the correct `parent_id`.
2. **Retrieval**: query a known clause (e.g. "payment terms"); assert hybrid+rerank returns
   the correct parent chunk in top-5; verify a deliberately contradictory pair
   (Net 30 vs Net 60) surfaces *both* rather than averaging.
3. **Drafting loop**: approve a small outline; run Burr to completion; assert every drafted
   section has ≥1 citation resolving to a real `parent_id`, and the evaluate node forces a
   rewrite when a citation is fabricated.
4. **End-to-end**: upload → approve outline → generate a ≈5-section document with citations.

## Open questions for the user
- Language/runtime confirmation (stack implies **Python** — FastAPI/Burr/Mirascope).
- Which embedding model + provider (affects Qdrant vector config and cost).
- Confirm short-document v1 target is acceptable before Index B is built.
