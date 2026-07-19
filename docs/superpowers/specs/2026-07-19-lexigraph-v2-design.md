# LexiGraph v2 — Design Spec (Advocate Chat Edition)

**Status:** design, not yet implemented. Supersedes the earlier draft of this file.
**Product reframe:** v2 turns the developer console into a **chat-first assistant for legal
advocates** — sessions like Claude/ChatGPT conversations, documents scoped per session, live
drafting shown in-stream, and a citation experience an advocate can actually trust and verify.

## 0. Inputs to this design (what we learned from the v1 big-document run)

A real appointment-letter PDF was ingested and a 10-section summary drafted end-to-end.
Findings that drive v2 (each maps to a numbered feature below):

| # | Observation from the live run | Root cause | v2 feature |
|---|---|---|---|
| F1 | Raw parent_id UUIDs inline in body text after nearly every paragraph | Draft prompt says "cite by parent_id"; model complies *in the text*; UI renders verbatim | §3 draft output contract |
| F2 | `##`/`###`/`**bold**`/`- lists` shown literally | Model emits markdown; UI renders plain `pre-wrap` | §3 + §6 renderer |
| F3 | Section title duplicated (UI heading + model's `## Title`) | No instruction against it; no post-strip | §3 |
| F4 | **10/10 sections flagged needs_review** | `check_grounded(section_text, source)` judges the WHOLE section against ONE source "alone" — structurally impossible for multi-source sections (one had 22 citations → guaranteed fail → 3 wasted redrafts) | §4 evaluator redesign |
| F5 | Eval cost exploded (22 cites × 3 attempts ≈ 66 LLM calls for one section) | Same as F4 + per-citation sequential LLM calls | §4 (deterministic first pass) |
| F6 | Frozen "DRAFTING…" screen for minutes | Blocking /run; replay only after completion | §7 SSE live stream |
| F7 | Job stranded at 8/10 in `approved` when the server process died mid-run | No `running/failed` states, no resume | §8 run lifecycle |
| F8 | Advocates can't use job-UUID ergonomics, can't tell which document a quote came from, can't export | Console UX, not product UX | §2 chat shell, §5 citation UX, §9 export |

Also carried forward (already specced, still valid): **C1 sessions**, **B1 corpus-aware
outline**, **C2/C3 doc management + revision turns**, SSE event contract. **A1 retry cap is
DONE in v1** (bounded loop + `needs_review` flag) and is assumed below.

Guiding constraints (unchanged): OpenRouter with `MODEL_ID` as the single swappable knob;
commit per decision; no new heavy deps without cause; `ponytail:` comments on deliberate
ceilings; backward-compatible API during migration.

---

## 1. Product definition — who is this for and what is a "chat"

**User:** a practicing advocate (India-first context per our test corpus, but not limited).
They live in Word, bill hours, and are professionally liable for anything they sign. They will
not trust generated text unless they can **verify every claim against the source in one click**.

**Mental model:** LexiGraph is a junior associate in a chat window. You open a **session**
(one matter-conversation), hand it PDFs, and converse:

- "Summarize this appointment letter's salary terms" → drafted doc with citations
- "Draft an MSA using these three precedents" → outline card → approve → live drafting
- "Redraft §3, stricter on notice period" → single-section revision turn (C3)
- "What does the letter say about ESOP vesting?" → *(v2 stretch: direct Q&A turn — same
  retrieval, single grounded answer, no outline/loop)*

**Session = conversation = corpus scope.** Documents uploaded in a session are retrievable
only in that session (C1). The sidebar lists sessions like Claude lists chats.

**Explicitly NOT in v2** (see v3 doc): matters/projects hierarchy, multi-user/auth,
collaboration, clause library, on-prem mode, multilingual drafting, 100-page scale (Index B),
full CRAG re-retrieval.

---

## 2. The chat shell (frontend architecture)

Three-pane layout, collapsing gracefully to one pane on mobile:

```
┌──────────┬─────────────────────────────┬──────────────────────┐
│ SESSIONS │ CONVERSATION                │ DOCUMENT PANEL       │
│          │                             │ (artifact-style)     │
│ + New    │ [user] prompt / uploads     │                      │
│ ● Appt   │ [asst] outline card         │ Drafted doc renders  │
│   letter │   ├ editable sections       │ here as it commits;  │
│ ○ MSA    │   └ [Approve & draft]       │ citation chips link  │
│   draft  │ [asst] ⟳ drafting… (live    │ to source passages   │
│          │   pipeline, SSE-driven)     │ in a hover/side view │
│          │ [asst] ✓ Document ready →   │                      │
└──────────┴─────────────────────────────┴──────────────────────┘
```

**Conversation message types** (a session's timeline is a list of these):
- `user_prompt` — text; may carry file attachments (uploads ingest into the session)
- `ingest_receipt` — assistant: "Indexed *appointment_letter.pdf* — 42 passages" per file
- `outline_card` — assistant: interactive card; sections are editable inline (title +
  instructions, add/remove/reorder); Approve button transitions it to a locked state
- `drafting_live` — assistant: the live pipeline block (§7). Collapsed = one-line status
  ("Drafting §4 of 10 — evaluating citations…") with a subtle pulse; expanded = full
  pipeline viz with nodes/particles. Modeled on Claude's tool-use blocks.
- `document_ready` — assistant: summary line (sections, citation count, flags) + button that
  focuses the document panel
- `revision` (C3) — user asks for a section change; assistant runs a single-section turn

**State/storage:** the conversation timeline persists in Mongo (`sessions.messages[]`) so a
session reloads exactly (kills the v1 "job id in localStorage" hack). React state is derived
from the timeline + live SSE events.

**Stack:** unchanged (React + Vite + Framer Motion). Add `react-markdown` for document
rendering (§6). No state-management lib until the timeline demonstrably outgrows
useState/useReducer. `# ponytail: useReducer for timeline; Zustand only if prop-drilling hurts.`

### 2.1 Green design system (the rebrand)

Direction: **counsel green on parchment** — the palette of law-library leather and bank-note
engraving. Green becomes the primary/action color; the v1 oxblood is retired to a *warning
accent only* (needs_review), because red must stay meaningful to a lawyer.

Tokens:

```
--paper        #f3f0e7   parchment background (kept — it reads "document", not "app")
--paper-deep   #e9e5d6   panels/cards
--ink          #17211b   green-black ink (all body text)
--ink-soft     #45514a   secondary text
--counsel      #1d5c47   PRIMARY — actions, active nodes, links, focus rings
--emerald      #2e8b6a   live/pulse states, success, streaming indicators
--bronze       #8a6d1e   keyword/sparse-search accents, metadata
--alert        #a33d2a   needs_review, errors ONLY (retired as brand color)
--rule         #c6c2ad   hairlines
```

Type stays serif-led (document gravitas) with the mono utility face for pipeline/metadata.
The pipeline nodes recolor: retrieve=counsel, draft=ink, evaluate=bronze, commit=emerald;
the pulsating animation uses `--emerald` glows. Sessions sidebar is deep parchment with a
counsel-green active indicator. All interactive states derive from `--counsel`.

Accessibility floor: AA contrast on all text tokens against both papers; visible focus
(`--counsel` 2px ring); `prefers-reduced-motion` swaps particle motion for state highlights.

---

## 3. Draft output contract (fixes F1/F2/F3) — backend prompt + shape

The drafted text must be **clean prose with lightweight citation markers**, not UUID soup.

**New contract:** `DraftedSection.text` uses **numbered markers** `[1]`, `[2]`… and
`citations` becomes an ordered list where index position = marker number:

```python
class Citation(BaseModel):
    parent_id: str
    quote: str            # verbatim quote from the source (unchanged)

class DraftedSection(BaseModel):
    section_id: str
    text: str             # markdown, NO parent_ids, NO leading title heading,
                          # claims marked [1][2]… referencing citations by position
    citations: list[Citation]
```

**Prompt changes** (`_DRAFT_SYSTEM`):
- "Cite with bracketed numbers [1], [2] in the text; list each citation once in `citations`
  in that order. NEVER write parent_ids in the text."
- "Do not repeat the section title; start directly with the content."
- "Output GitHub-flavored markdown (paragraphs, `###` sub-heads, lists, bold)."

**Defense in depth (post-processing, because prompts drift):** after parsing, strip any
UUID-shaped `[...]` tokens from `text`, strip a leading heading that duplicates the title,
and renumber markers to match the citations list. Deterministic, ~15 lines.

**Migration:** `GET /jobs/{id}/sections` keeps its shape; old jobs render fine (the
post-processor also runs at read time for legacy sections).
`# ponytail: read-time cleanup for legacy rows; no data migration.`

---

## 4. Evaluator redesign (fixes F4/F5) — claim-level groundedness

The flagship trust feature, rebuilt on the v1 lesson: **grade citations, not sections.**

**Current (broken) semantics:** whole `section_text` vs one source, "supported by this source
*alone*" → structurally fails any multi-source section → 3 wasted redrafts → every section
flagged → flag becomes noise → advocate trust destroyed.

**New two-tier check, per citation:**

**Tier 1 — deterministic quote verification (no LLM, ~free):**
The citation's `quote` must actually appear in the cited parent's text. Exact substring
first; fall back to normalized fuzzy match (casefold, collapse whitespace,
`difflib.SequenceMatcher` ratio ≥ 0.85 over a sliding window). Catches fabricated quotes and
wrong-source attributions instantly. This alone would have validated most of the v1 run's
citations at zero cost.

**Tier 2 — claim entailment (one LLM call per SECTION, batched):**
One call: here are claims (the sentence(s) around each marker, extracted by position) paired
with their quoted sources — return per-claim `supported: bool` for all of them. Replaces
~22 sequential calls per attempt with 1.

**Verdict semantics:**
- Any Tier-1 failure (fabricated/misattributed quote) → `eval_ok=False` → targeted redraft.
  The redraft prompt names WHICH citations failed and why (today the model redrafts blind).
- Tier-2 failures below a threshold (e.g. ≥80% claims supported) → pass, but mark the
  *individual* citations `unverified` — per-citation flags, not a section-wide scarlet letter.
- `needs_review` (section-level) now fires only on retry-cap exhaustion (A1, unchanged).

**Data shape:** `citations[i]` gains `verified: "quote_verified" | "entailed" | "unverified"`,
stored on the drafted section and surfaced in the UI (§5).

**Cost math (the F5 win):** worst v1 section = 22 cites × 3 attempts × 1 call = 66 calls.
v2 = 3 attempts × 1 batched call = ≤3 calls + free Tier 1. ~95% eval-cost reduction.
`# ponytail: sliding-window fuzzy match is O(n·m) per quote; fine at parent scale (~1.5KB).`

---

## 5. Citation UX (advocate trust, F8)

- In the document panel, markers render as **superscript chips** `[1]` in `--counsel`.
- Hover/click a chip → popover: source **document name** + the verbatim quote with the
  matched span highlighted + verification badge (✓ quote verified / ◐ entailed / ⚠ unverified).
- Requires `source_file` (already in the parent payload) to flow into `Citation` at draft
  time — one field addition.
- Per-section footer: "12 citations · 11 verified · 1 unverified" replacing the v1 monospace
  quote wall (which moves into the popovers).
- A document-level **"Verification" summary** at top: total claims, verified %, flagged
  sections — the first thing a liability-conscious advocate looks for.

---

## 6. Document rendering

- `react-markdown` (+ `remark-gfm`) renders `text`; the citation-marker chips are a tiny
  custom renderer over the `[n]` pattern. One new dependency, justified: hand-rolling
  markdown is the classic false economy.
- Sub-headings, lists, bold now render properly (F2). Print stylesheet included (advocates
  print) — clean margins, chips become real footnotes at section end.

---

## 7. Live drafting stream (C4)

**Mechanics:** `GET /jobs/{id}/run/stream` → `text/event-stream`. The endpoint creates a
per-run `queue.Queue` keyed by `job_id`, runs the Burr loop in a worker thread (Burr's
`app.run()` is sync; a thread lets the async SSE generator stream concurrently), actions
`put` typed events, the generator `get`s and yields frames until `job_done`/`error`.
SSE auto-reconnect is handled by resending a `job_snapshot` (current cursor + committed
sections) on connect. Blocking `/run` is retained for scripts.
`# ponytail: in-process queue; a broker (Redis/NATS) only when multi-worker fan-out is real.`

**Event contract** (JSON: `{type, section_id?, section_index?, data}`) — the same shapes the
v1 replay driver already synthesizes, so `Pipeline.jsx` needs only a source swap:

| type | when | data |
|---|---|---|
| `job_start` | run begins | `n_sections, section_titles[]` |
| `job_snapshot` | (re)connect mid-run | `cursor, committed_sections[]` |
| `section_start` | entering retrieve | `title, index` |
| `retrieve_query` | query built | `query` |
| `candidates` | hybrid search returns | `n_candidates, sample[]` |
| `deduped` | parent dedupe | `n_before, n_after, parent_ids[]` |
| `reranked` | Cohere top-n | `ranked[{parent_id, snippet, rank}]` |
| `draft_start` / `draft_done` | drafting | `attempt` / `text_preview, citations[]` |
| `evaluate` | §4 verdict | `eval_ok, attempt, tier1_failed[], unverified[]` |
| `redraft` | eval fail, looping | `attempt, max` |
| `section_committed` | section saved | `section_id, needs_review,` **rendered section payload** |
| `job_done` / `error` | terminal | `document` / `where, message` |

**Presentation:** the stream drives the `drafting_live` chat block (§2) — collapsed one-line
status by default, expandable to the full pipeline viz. The `evaluate` tier results let the
viz show *why* a redraft happens. Because `section_committed` carries the rendered section,
the document panel fills **section by section during the run** — the advocate reads §1 while
§4 drafts. This, plus the status line, kills the F6 frozen screen.

---

## 8. Run lifecycle & resumability (F7 — promoted from "A4 nice-to-have" to required)

The v1 incident (server died mid-run → job stranded at 8/10 in `approved`) becomes a
first-class design concern:

- **Job states:** `outline_pending → approved → running → done | failed`. `/run` (and the
  SSE variant) sets `running` at start; any unhandled action exception is caught at the loop
  boundary → `failed` + `{error: {where, message}}` on the job; SSE emits `error` and closes.
- **Resume:** `POST /jobs/{id}/resume` rebuilds the Burr app via the SQLite persister
  (`initialize_from`, `app_id=job_id` — the checkpoints already exist in v1!) and continues
  from the last committed section. Already-committed sections in Mongo are the source of
  truth for dedupe on re-commit.
- **UI:** a `failed` job renders a retry affordance in the chat timeline; a `running` job
  re-attaches to its SSE stream on page reload (session timeline knows the active job).
- Server ops: `run.sh` stays reload-free (v1 lesson, already shipped).

---

## 9. Export (advocate must-have, F8)

`GET /jobs/{id}/export?format=docx|md`. Advocates live in Word.
- **DOCX** via `python-docx`: title, sections as Heading 2, markdown-lite rendering (bold,
  lists), citations as real footnotes (document name + quote), verification summary as a
  final table. One new backend dep, small and boring.
- **Markdown** export is free (we already have it) and feeds their other tools.
- PDF deferred to v3 (printing the DOCX/print-stylesheet covers v2).
- Every export appends a configurable disclaimer block ("AI-assisted draft — verify before
  use; not legal advice") — professional-responsibility hygiene, on by default.

---

## 10. Sessions, corpus-aware outline, revision turns (carried forward)

**C1 sessions** — as previously specced (sessions collection, `session_id` on Qdrant
payloads, filtered `query_points`, scoped ingestion/jobs) with two additions:
`sessions.messages[]` for the chat timeline (§2) and `title` auto-generated from the first
prompt (one cheap LLM call, like Claude's chat titles).

**B1 corpus-aware outline** — as previously specced (per-doc abstracts at ingest + prompt-
relevant retrieval feeding `generate_outline`). Now also feeds the **outline card**: each
proposed section shows *which documents* inform it, so the advocate edits the skeleton with
eyes open. The v1 run is the cautionary tale: a blind 10-section outline against one letter
produced sections the corpus strained to support.

**C2/C3** — document list/remove and single-section revision turns as previously specced,
surfaced as natural chat actions (attach/remove in the session header; "redraft §3…" as a
`revision` message).

**Audit metadata (small, new):** every job stores `{model_id, started_at, finished_at,
per_section: {attempts, eval_results}}`; shown in a details drawer on `document_ready`.
An advocate (or their regulator) can answer "what produced this text?".

---

## 11. Build order (each step independently verifiable, one commit each)

| # | Step | Why this order |
|---|---|---|
| 1 | §3 draft contract + §6 markdown rendering | Cheapest, transforms perceived quality immediately; everything downstream renders through it |
| 2 | §4 evaluator redesign | Fixes the trust feature + ~95% eval cost; unblocks honest per-citation UX |
| 3 | §8 run lifecycle (`running/failed`, resume) | Safety net under all later live-run work |
| 4 | C1 sessions backend + timeline storage | The data backbone for the chat shell |
| 5 | §2 chat shell + §2.1 green rebrand | The product reframe, on stable foundations |
| 6 | §7 SSE live stream into the chat block | Live experience (event contract already frozen) |
| 7 | B1 corpus-aware outline + outline card | Quality of the skeleton, now visible in chat |
| 8 | C2/C3 doc mgmt + revision turns | Completes the conversational loop |
| 9 | §5 citation popovers + §9 DOCX export | Trust + deliverable polish |

Verification per step mirrors the previous draft's practices (unit checks for contract
post-processing and Tier-1 matching; scripted end-to-end against a real PDF; SSE event-order
assertions; a forced-kill resume test for §8).

## 12. Explicitly deferred to v3
See `2026-07-19-lexigraph-v3-ideas.md`: matters/projects, clause library, multi-user,
collaboration, privacy/self-host modes, multilingual, Index B scale, full CRAG, Q&A-over-
corpus as a first-class turn, integrations, PDF export, analytics.
