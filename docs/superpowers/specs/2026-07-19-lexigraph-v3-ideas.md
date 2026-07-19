# LexiGraph v3 — Ideas & Direction (post-chat-edition horizon)

**Status:** idea backlog, deliberately NOT specced to v2 depth — these get real designs only
when v2 ships and usage teaches us which ones matter. Ordered by how directly they serve a
practicing advocate's day.

## 1. Matters (projects / case studies) — the organizing layer
The feature the user named directly. A **Matter** is a long-lived container above sessions:
*Sharma v. NxtPe* holds every session, document, draft, and export related to one engagement.
- Sessions become threads inside a matter (like Claude Projects); matter-level corpus =
  union of its sessions' documents, with per-session override.
- Matter dashboard: parties, dates, deadlines, document inventory, draft history.
- **Case studies**: a closed matter can be anonymized and archived as a reusable precedent
  bundle — "draft this like the Mehta settlement" retrieves from that bundle.
- Cross-matter conflict surface: same counterparty appearing in two matters is something an
  advocate ethically must notice.

## 2. Clause & precedent library
Advocates reuse their own battle-tested language. Let them pin a drafted (or uploaded)
clause into a personal library with tags; drafting turns can then cite the library alongside
session documents. The library becomes a first-class retrieval source (its own collection or
payload tag). This is the stickiest possible feature — their own work compounds.

## 3. Privacy modes & self-hosting (the adoption blocker)
Privileged documents currently transit four external services (Unstructured, Qdrant Cloud,
Cohere, OpenRouter). For real practice adoption:
- **Tier 1:** data-flow transparency page + per-service data-retention notes (cheap, v2.x).
- **Tier 2:** BYO-keys so a chamber uses its own accounts.
- **Tier 3:** local mode — local parsing (unstructured OSS), local Qdrant, local reranker,
  local LLM via the same OpenRouter-shaped config seam. The `MODEL_ID`-as-config decision
  was made for exactly this door.

## 4. Q&A over the corpus as a first-class turn
"What does the letter say about ESOP vesting?" shouldn't need an outline+loop — a single
retrieve→answer turn with the same citation/verification machinery. Half the daily value of
a chat assistant is questions, not drafts. (Stretch-listed in v2; belongs fully in v3 with
conversation memory across turns.)

## 5. Scale: Index B + full CRAG (the deferred architecture)
- **Index B** episodic memory unlocks 100-page documents (running_summary retrieval instead
  of concatenation) — the original Phase-2 design, still valid.
- **Full CRAG**: on evaluator failure, rewrite the query and re-retrieve before redrafting
  (v2 still redrafts against the same candidates). Pairs with per-citation failure signals
  from the v2 evaluator, which tell CRAG *what* to re-search for.

## 6. Multilingual & jurisdiction awareness
India-first reality: pleadings and precedents in Hindi and regional languages; templates
differ by court/state. Multilingual embedding model + drafting-language control + a
jurisdiction knob on outline generation ("Maharashtra rent control matter").

## 7. Collaboration & roles
Multi-user chambers: shared matters, reviewer role (a senior approves outlines/flags),
comment threads on sections, hand-off between juniors and partners. Requires auth (absent
by design through v2) — do auth only when this lands, not before.

## 8. Deliverable & workflow integrations
- PDF export with court-formatting profiles (margins, line numbering, cause-title blocks).
- DMS/Drive sync; email-in a document to a matter.
- Calendar/limitation-date extraction from ingested documents (dates are retrievable facts).

## 9. Analytics & self-improvement loop
Per-matter and per-user: verification rates, sections most edited after generation, retrieval
hit quality. Edited-after-export diffs are free supervised signal for prompt tuning — the
advocate's red pen teaches the system.

## Sequencing instinct (subject to v2 learnings)
Matters (1) and Q&A turns (4) first — they're the two things users will ask for in week one.
Privacy tiers (3) gate any real-chamber adoption and should start as documentation early.
Everything else follows demand.
