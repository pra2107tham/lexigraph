# LexiGraph — Roadmap & Known Gaps

Deferred work, ordered by whether it's a **correctness gap** (the loop can misbehave),
an **agentic-quality improvement** (decisions get smarter), or a **product/UX** feature.
Nothing here is built yet — this is the backlog for the next update.

Phase-2 items already named in the plan (Index B episodic memory, CRAG entailment
evaluator) are listed here too, tied to the concrete gaps they fix.

---

## A. Correctness gaps (the loop can misbehave today)

### A1 — Redraft loop has no retry cap  ⚠️ highest priority
`evaluate → draft → evaluate → draft …` (`graph.py:45`) has **no attempt counter**. If the
retrieved sources genuinely can't ground the section, the loop spins **forever** and hangs
the whole `POST /jobs/{id}/run` request.
- **Fix:** add a `retries` counter in state (bump in `draft` or `evaluate`); add an exit edge
  `("evaluate", "commit", expr("eval_ok == True or retries >= N"))`. On cap-out, commit the
  best attempt with a `needs_review=True` flag rather than hanging.
- **Ceiling:** degrade gracefully; never spin.

### A2 — Failure re-drafts but never re-retrieves
On `eval_ok == False` the loop returns to `draft` with the **same `candidates`**. If the
sources are the problem (not the wording), redrafting can't help — it just burns retries into
A1's cap.
- **Fix (Phase 2 = CRAG):** on failure, route back through `retrieve` with a widened/rewritten
  query (more candidates, different phrasing) before redrafting.
- Pairs with A1: retry cap bounds it, CRAG makes the retries actually productive.

### A3 — `check_grounded` runs one LLM call *per citation*, sequentially
`evaluate` (`actions.py:63-70`) loops citations and calls the LLM for each, first-failure-breaks.
Fine for correctness, slow + costly for many-citation sections.
- **Fix:** batch the groundedness check into one call over all citations, or gate check-2
  behind a cheap lexical overlap pre-filter so obviously-grounded cites skip the LLM.

### A4 — No error handling around external calls
Any of Unstructured / Qdrant / Cohere / OpenRouter throwing mid-loop surfaces as an opaque 500
and (for `/run`) leaves the job stuck in `approved` with partial `drafted_sections` in Mongo.
- **Fix:** wrap each action's external call; on unrecoverable failure set job `status=failed`
  with the reason, so it's resumable/inspectable instead of silently half-done.

---

## B. Smarter agentic decisions (the model's reasoning gets better)

### B1 — Outline is generated BLIND to the corpus  ⭐ (user-requested)
`generate_outline(job_id, prompt)` (`outline.py:34`) sees **only the prompt** — never the
ingested documents. The skeleton is proposed with no knowledge of what precedent actually
exists, so it can propose sections nothing in the corpus can support.
- **Fix:** before generating, retrieve/assemble a **corpus summary** (top-k parents for the
  prompt, or per-document abstracts built at ingest time) and feed it into the outline prompt:
  *"Given these available precedents: {summary}, propose an outline the corpus can actually
  ground."* Makes the outline natively correct instead of aspirational.
- **Cheap first step:** at ingest, store a 2-3 sentence per-document abstract; feed the set of
  abstracts into `generate_outline`.

### B2 — Retrieval query is a naive title+instructions concat
`retrieve_sources` builds the query as `f"{title} — {instructions}"` (`actions.py:29`). Works,
but a section often needs *several* sub-queries (a Termination section wants "notice period",
"cause", "cure period" separately).
- **Fix:** let the drafter emit 1-3 focused sub-queries per section (query decomposition /
  the "retrieve tool" from D2), union the results, then dedupe+rerank as today.

### B3 — `running_summary` grows unbounded → context blowout (Phase 2 = Index B)
It's the full concatenated text of every prior section (`actions.py:87`). Fine for ~5-10
sections; at 100-page scale it overflows the context window.
- **Fix (Phase 2 = Index B):** replace with an episodic memory that *retrieves* only the
  relevant prior sections for the current one, instead of carrying all of them. The `draft`
  action already just reads `running_summary`, so the swap is localized.

### B4 — Evaluator only checks citations, not quality
D4 verifies groundedness only. It can't catch: section drifting off its instructions, missing
a required sub-topic, or internal contradiction with an earlier section.
- **Fix:** add a lightweight "does this section satisfy its instructions + stay consistent with
  the running summary?" check alongside the citation gate (still cheaper than full CRAG).

### B5 — No self-consistency check across the assembled document
`assemble` (`actions.py:97`) just concatenates. A term defined in §2 could be contradicted in
§7 and nothing notices.
- **Fix:** a final pass over the whole document flagging cross-section contradictions (this is
  the D3 contradiction-preservation principle applied at document scope, not just retrieval).

---

## C. Product / session model (make it work like a chat)

### C1 — No session; jobs retrieve across the ENTIRE global index  ⭐ (user-requested)
Documents are global — `mongo_doc_id` exists per doc, but **nothing scopes documents to a
job/session**. Every job's retrieval hits all of Index A, so uploads from unrelated work bleed
into each other. There's no "these documents belong to this chat," the way ChatGPT keeps
uploaded files inside a conversation.
- **Fix:** introduce a `session_id` (or reuse `job_id` as the scope key).
  - Tag each ingested point's payload with its `session_id`.
  - Filter hybrid search by `session_id` (Qdrant payload filter in the `query_points` call) so
    a job only retrieves from *its* documents.
  - `POST /documents` takes/returns a session; `POST /jobs` runs within that session's corpus.
- **Ceiling:** payload filter is fine at MVP scale; a per-session collection only if isolation
  or scale demands it.

### C2 — Documents aren't listable / removable per session
No way to see "what's uploaded in this session" or drop a document. Chat UX needs both.
- **Fix:** `GET /sessions/{id}/documents` and `DELETE /documents/{doc_id}` (remove from Mongo
  + delete points from Qdrant by `mongo_doc_id` filter).

### C3 — One document per job; no follow-up / revision turns
A job is one-shot: prompt → outline → run → done. Chat implies *turns* — "now redraft §3 to be
stricter", "add a confidentiality section".
- **Fix:** allow re-running a single section against new instructions without regenerating the
  whole document (the Burr persister already checkpoints per-section state — resume at a chosen
  cursor).

### C4 — No streaming / progress; `/run` is a blocking call
`run_job` runs the whole loop synchronously (`routes.py:82-93`); the client waits with no
visibility. A chat UX wants per-section progress.
- **Fix:** stream section-by-section (SSE/websocket) or make `/run` async + a
  `GET /jobs/{id}/status` that reports `cursor`/`drafted_sections` as they land.

---

## Priority for the next update
1. **A1** (retry cap) — safety, tiny change.
2. **C1** (session scoping) — the core "chat with your documents" model; unblocks C2/C3.
3. **B1** (corpus-aware outline) — biggest quality win for the outline step.
4. Then A2/B3 as the Phase-2 CRAG + Index B pair.
