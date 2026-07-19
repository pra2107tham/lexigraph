# LexiGraph v2 — Design Spec (extreme detail)

**Status:** design, not yet implemented. v1 (test UI against current backend) ships first;
this document is the authoritative plan for v2.

**Scope of v2:** the four roadmap updates (A1 retry cap, C1 session scoping, B1 corpus-aware
outline, C4 streaming) **plus** the live SSE-driven pipeline visualization that makes the
frontend's retrieve→draft→evaluate animation reflect *real* per-step backend events.

This spec assumes v1 is in place: a React + Vite + Framer Motion frontend served by FastAPI,
talking to the current REST endpoints, with a pipeline viz that *replays* from final results.
v2 turns that replay into a live stream and adds sessions, safe loops, grounded outlines.

---

## 0. Guiding constraints (carried from v1)

- **LLM via OpenRouter**, model is a single config value (`MODEL_ID`) — never hardcode a model.
- **Commit per decision** — each numbered step below ends with its own git commit.
- **No new heavy deps without cause** — SSE uses stdlib + Starlette; sessions use existing
  Mongo + Qdrant payload filters; no message broker, no Redis for MVP scale.
- **Backward compatible** — existing blocking `/run` and unscoped retrieval keep working
  until the frontend fully moves to the streaming + session-scoped paths.
- **ponytail ceilings** — every deliberate shortcut gets a `ponytail:` comment naming the
  ceiling and upgrade path.

---

## 1. Feature A1 — Redraft retry cap (safety)

### Problem
`evaluate → draft → evaluate → draft …` (`graph.py:45`) has no attempt counter. If the
retrieved sources genuinely can't ground the section, the loop spins forever and hangs
`POST /jobs/{id}/run`.

### Design
Add a bounded-retry counter to Burr state and a graceful exit edge.

**State change** (`graph.py` `with_state(...)`):
- add `retries: int = 0`
- add `max_retries: int` seeded from config (`settings.max_redraft_retries`, default 3)
- add `needs_review: list[str] = []` — section_ids that hit the cap without grounding

**Action change** (`actions.py`):
- In `draft`, increment `retries` **only when re-entering after a failure**. Cleanest: reset
  `retries=0` in `retrieve_sources` (start of a section), increment in `draft`. So `retries`
  counts drafts *within the current section*.
- In `evaluate`, compute the exit condition. Keep writing `eval_ok`, but the transition now
  also considers the cap.

**Transition change** (`graph.py`):
```python
# pass: grounded OR we've exhausted retries (commit best-effort, flag it)
("evaluate", "commit", expr("eval_ok == True or retries >= max_retries")),
# fail AND retries left: redraft
("evaluate", "draft",  expr("eval_ok == False and retries < max_retries")),
```
`commit` must, when `eval_ok == False` but committing due to cap, append the section_id to
`needs_review` and persist the section with a `needs_review=True` marker (so the assembled
document and API can surface "this section couldn't be fully grounded").

**Config** (`config.py`): `max_redraft_retries: int = 3`.

### Edge cases
- A section that grounds on attempt 1 → `retries` stays low, no `needs_review`.
- A section that never grounds → exactly `max_retries` draft attempts, then committed with
  the flag. Loop is provably bounded: `retries` strictly increases each `draft`, capped edge
  fires deterministically.
- `assemble` renders a visible "⚠ needs review" note under any flagged section.

### Verification
- Unit: force `check_grounded` to always return `grounded=False`; assert the loop runs exactly
  `max_retries` drafts and the section lands in `needs_review`, no infinite loop.
- Unit: normal path — grounds on attempt 1, `needs_review` empty.

### Commit
`feat(v2): bounded redraft retry cap + needs_review flag (A1)`

---

## 2. Feature C1 — Session scoping ("chat with your documents")

### Problem
`mongo_doc_id` is per-document but nothing ties documents to a job/session. Every job's
retrieval hits the entire global Index A, so unrelated uploads bleed into each other. There is
no notion of "these documents belong to this conversation," the way ChatGPT scopes uploaded
files to a chat.

### Design
Introduce a first-class `session_id`. Documents, jobs, and retrieval all scope to it.

**New concept — Session** (Mongo `sessions` collection):
```
{ _id: session_id, title, created_at, document_ids: [mongo_doc_id, ...] }
```

**Ingestion changes** (`pipeline.py`, `partition.py`):
- `ingest_pdf(file_bytes, file_name, session_id)` — new required arg.
- Every Qdrant point payload gains `session_id` (`_persist_vectors`, alongside the existing
  `parent_id`, `parent_text`, `mongo_doc_id`, `source_file`).
- Mongo `documents` record gains `session_id`; the session's `document_ids` is appended.

**Retrieval changes** (`search.py`, `retriever.py`, `rerank.py` unaffected):
- `hybrid_search(query, session_id, ...)` adds a Qdrant payload filter so both prefetch
  branches only match points with the given `session_id`:
  ```python
  query_filter=models.Filter(
      must=[models.FieldCondition(key="session_id",
                                  match=models.MatchValue(value=session_id))]
  )
  ```
  Applied to the `query_points` call (filter propagates to prefetch in Qdrant native hybrid).
- `retrieve(query, session_id, ...)` threads `session_id` through.

**Drafting changes** (`actions.py`, `graph.py`):
- `retrieve_sources` reads `session_id` from state and passes it to `retrieve(...)`.
- `build_app(job_id, sections, session_id, ...)` seeds `session_id` into state.

**API changes** (`routes.py`):
- `POST /sessions` → create a session, returns `session_id`.
- `POST /documents` now takes `session_id` (form field), ingests into that session.
- `POST /jobs` takes `session_id`; the job runs only against that session's corpus.
- `GET /sessions` / `GET /sessions/{id}` for listing (feeds the chat sidebar).

### ponytail ceiling
`# ponytail: single global collection + session_id payload filter; move to per-session
collections only if isolation/scale demands it.` Payload filtering is correct and cheap at
MVP scale; per-collection isolation is the upgrade path.

### Backward compatibility
Retrieval without a `session_id` keeps the old global behavior (filter omitted). Existing data
lacking `session_id` is simply never matched by a scoped query — acceptable; re-ingest under a
session if needed. Document this.

### Verification
- Ingest doc X under session A, doc Y under session B. A job in session A must never retrieve
  a parent from doc Y. Assert via payload inspection + a retrieval that would otherwise match Y.

### Commit
`feat(v2): session scoping — sessions collection + payload-filtered retrieval (C1)`

---

## 3. Feature C2/C3 — Session document management + follow-up turns

*(Built on C1; smaller.)*

### C2 — list / remove documents in a session
- `GET /sessions/{id}/documents` — list ingested docs (from the session record).
- `DELETE /documents/{doc_id}` — remove from Mongo `documents` + `parents`, delete matching
  Qdrant points by `mongo_doc_id` filter, pull from the session's `document_ids`.

### C3 — follow-up / single-section revision
A job today is one-shot. Chat implies turns: "redraft §3 stricter", "add a confidentiality
section".
- `POST /jobs/{id}/sections/{section_id}/redraft` with new `instructions`. Because the Burr
  persister checkpoints per-section state keyed by `job_id`, we can resume the app, reset
  `cursor` to that section, overwrite its `instructions`, and run just that section's
  retrieve→draft→evaluate→commit, then re-assemble.
- `POST /jobs/{id}/sections` to append a new section (extends `sections`, drafts only the new
  one).

### ponytail ceiling
`# ponytail: re-run one section by resuming the persisted app; full conversational editing
(diffing, undo) is later.`

### Verification
- Redraft §3 with stricter instructions; assert only §3's `drafted_sections` entry changes and
  the rest are untouched; document re-assembles.

### Commit
`feat(v2): session doc management + single-section redraft turns (C2/C3)`

---

## 4. Feature B1 — Corpus-aware outline generation

### Problem
`generate_outline(job_id, prompt)` (`outline.py:34`) sees only the prompt — never the ingested
documents. It proposes a skeleton blind to what precedent actually exists, so it can invent
sections nothing in the corpus can ground.

### Design
Feed a **corpus summary** of the session's documents into the outline prompt.

**Two-tier summary source (cheap → richer):**
1. **Per-document abstract at ingest time** (built once, stored): after partitioning, take the
   first N parents (or a title-page heuristic) and ask the LLM for a 2–3 sentence abstract;
   store on the `documents` record as `abstract`. Cheap, reused across all jobs in the session.
2. **Prompt-relevant retrieval** at outline time: run the drafting prompt through
   `retrieve(prompt, session_id, top_n=~8)` to pull the most relevant parents; include short
   snippets.

**Outline call change** (`outline.py`):
```python
def generate_outline(job_id, prompt, session_id):
    abstracts = _session_abstracts(session_id)          # tier 1
    relevant  = retrieve(prompt, session_id, top_n=8)   # tier 2
    context   = _format_corpus_context(abstracts, relevant)
    # system prompt gains: "Propose an outline the provided corpus can actually ground.
    #   Available precedents: {context}. Do not propose sections unsupported by them."
```
`_OUTLINE_SYSTEM` updated to instruct grounding in the provided corpus context.

### ponytail ceiling
`# ponytail: abstracts from first-N parents; a map-reduce full-doc summary only if abstracts
prove too shallow for outline quality.`

### Verification
- Session with a payment-heavy precedent set + prompt "draft an MSA": outline should include
  payment/termination sections the corpus supports and NOT invent a section (e.g. "SLA credits")
  absent from the corpus. Compare blind vs corpus-aware outputs on the same prompt.

### Commit
`feat(v2): corpus-aware outline grounded in session summary (B1)`

---

## 5. Feature C4 + live viz — SSE streaming of real pipeline events

This is the centerpiece: make the frontend animation reflect **real** per-step backend events,
not a replay.

### 5.1 Event emission from the Burr loop

The Burr actions currently return final state and emit nothing. We add an **event sink** the
actions write to, and the SSE endpoint drains.

**Mechanism (chosen): per-run `queue.Queue` + threaded run.**
- The streaming endpoint creates a `queue.Queue`, stores it keyed by `job_id`, and starts the
  Burr loop in a worker thread.
- Actions get the queue via a lightweight context (passed through Burr state as a non-serialized
  handle, or a contextvar keyed by `job_id`). Each action `put`s typed events.
- The SSE generator `get`s from the queue and yields `text/event-stream` frames until a terminal
  `done`/`error` event.

`# ponytail: in-process queue keyed by job_id; a real broker (Redis/NATS) only when we run
multiple API workers or need cross-process fan-out.`

**Why a thread:** Burr's `app.run()` is synchronous; running it in a thread lets the async SSE
generator stream concurrently without rewriting actions as async.

### 5.2 The event contract (the durable interface)

Every event is JSON: `{ "type": ..., "section_id": ..., "section_index": ..., "data": {...} }`.
Types, in the order they fire per section:

| type | when | data payload |
|---|---|---|
| `job_start` | run begins | `{ n_sections, section_titles[] }` |
| `section_start` | entering `retrieve` | `{ section_id, title, index }` |
| `retrieve_query` | query built | `{ query }` |
| `candidates` | hybrid search returns | `{ n_candidates, sample:[{parent_id, snippet, source_file}] }` |
| `deduped` | dedupe to parents | `{ n_before, n_after, parent_ids[] }` |
| `reranked` | Cohere top-n | `{ ranked:[{parent_id, snippet, rank}] }` |
| `draft_start` | entering `draft` | `{ attempt }` |
| `draft_done` | draft produced | `{ text_preview, citations:[{parent_id, quote}] }` |
| `evaluate` | D4 result | `{ eval_ok, attempt, failures:[{parent_id, reason}] }` |
| `redraft` | eval fail, looping | `{ attempt, max }` |
| `committed` | section saved | `{ section_id, needs_review }` |
| `job_done` | assemble done | `{ document }` |
| `error` | any failure | `{ where, message }` |

This contract is versioned and documented; the frontend renders purely from it. **It is the
same contract the v1 replay uses** — v1 synthesizes these events from final results, v2 emits
them live. So the frontend animation code does not change between v1 and v2; only the event
source does.

### 5.3 Endpoints
- `GET /jobs/{id}/run/stream` → `text/event-stream`. Runs the loop, streams events, ends with
  `job_done`. Replaces the blocking `/run` for the UI (blocking `/run` retained for scripts).
- Reconnect: SSE auto-reconnects; on reconnect we resend the last known state snapshot
  (`job_snapshot` event) so a dropped connection doesn't lose the animation state.

### 5.4 Frontend (already React + Framer Motion from v1)
- Swap the v1 replay driver for a native `EventSource` on `/jobs/{id}/run/stream`.
- `PipelineViz` consumes the event stream → drives Framer Motion:
  - nodes (`retrieve/draft/evaluate/commit`) **pulse** on their matching events;
  - `candidates` spawn particle chunks flying into the retrieve node;
  - `deduped` collapses duplicates (particles merge);
  - `reranked` reorders the top-n with layout animation;
  - `evaluate` fail flashes red + a `redraft` particle loops back to draft;
  - `committed` slides the section into the document panel.
- Respect `prefers-reduced-motion`: fall back to state highlights without particle motion.

### Verification
- Run a real multi-section job; assert the browser receives every event type in order and the
  document assembled from `job_done` matches `GET /jobs/{id}/document`.
- Kill the connection mid-run; assert reconnect resumes the animation via `job_snapshot`.

### Commit
`feat(v2): SSE pipeline event stream + live Framer Motion viz (C4)`

---

## 6. Build order for v2

Each step independently verifiable, each its own commit.

1. **A1 retry cap** — smallest, pure safety, no API surface change. *(§1)*
2. **C1 session scoping** — the backbone; unblocks C2/C3/B1. *(§2)*
3. **C2/C3 session doc mgmt + redraft turns** — built on C1. *(§3)*
4. **B1 corpus-aware outline** — needs C1's session corpus. *(§4)*
5. **C4 SSE streaming + live viz** — the event contract + threaded queue + frontend swap. *(§5)*

Rationale: safety first (1), then the data-model backbone (2) everything else needs, then the
features that ride on it (3,4), then the streaming layer (5) that turns the whole thing live.

---

## 7. Data model summary (after v2)

```
Mongo
  sessions         { _id, title, created_at, document_ids[] }              NEW
  documents        { _id, session_id, source_file, abstract, raw_elements } +session_id +abstract
  parents          ParentChunk (unchanged)
  jobs             { _id, session_id, prompt, outline, status, document, needs_review[] } +session_id +needs_review
  drafted_sections { ..., needs_review }                                    +needs_review
  outlines         (unchanged)

Qdrant Index A (per point payload)
  { parent_id, parent_text, mongo_doc_id, source_file, session_id }         +session_id

Burr state (per job)
  sections, cursor, running_summary, candidates, draft, eval_ok,
  drafted_sections, document, session_id, retries, max_retries, needs_review  +last four
```

---

## 8. Explicitly deferred beyond v2
- **B3 / Index B** episodic memory (100-page scale) — `running_summary` stays full-text in v2.
- **A2 full CRAG** re-retrieval on failure — v2 has the retry cap (A1) but still redrafts on the
  same candidates; query-rewrite-and-re-retrieve is post-v2.
- **B2** query decomposition, **B4/B5** quality + cross-section consistency evaluators.
- **Auth / multi-user** — sessions are unauthenticated in v2 (single-user test/product).
- Real message broker for SSE (multi-worker fan-out).
