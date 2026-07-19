"""§4 two-tier claim-level evaluator — grade citations, not sections.

Tier 1 (deterministic, free): every citation's quote must actually appear in
its cited parent (exact substring on normalized text, else fuzzy sliding
window). Any failure means a fabricated or misattributed quote → redraft with
targeted feedback.

Tier 2 (one batched LLM call per section): each marker's surrounding claim is
checked for entailment against its quote. Unsupported claims mark individual
citations `unverified`; the section passes if the supported ratio clears the
threshold. `needs_review` (section-level) fires only on retry-cap exhaustion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.models import Citation, DraftedSection, ParentChunk

_WS = re.compile(r"\s+")
_MARKER = re.compile(r"\[(\d+)\]")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().casefold()


def quote_in_parent(quote: str, parent: str, threshold: float = 0.85) -> bool:
    """Exact normalized substring, else ordered-match coverage >= threshold.

    Coverage = share of the quote's characters found in order within the parent
    (SequenceMatcher matching blocks) — tolerant of typos/ellipses, unlike
    fixed sliding windows which are alignment-sensitive.
    # ponytail: O(len(parent)·len(quote)) per quote; fine at parent scale (~1.5KB).
    """
    q, p = _norm(quote), _norm(parent)
    if not q:
        return False
    if q in p:
        return True
    matched = sum(b.size for b in SequenceMatcher(None, p, q, autojunk=False).get_matching_blocks())
    return matched / len(q) >= threshold


def extract_claims(text: str, n_citations: int) -> dict[int, str]:
    """Map marker number -> the sentence containing it (the claim to entail)."""
    claims: dict[int, str] = {}
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        for m in _MARKER.finditer(sentence):
            n = int(m.group(1))
            if 1 <= n <= n_citations and n not in claims:
                claims[n] = _MARKER.sub("", sentence).strip()
    return claims


@dataclass
class EvalReport:
    eval_ok: bool
    tier1_failed: list[dict] = field(default_factory=list)  # [{index, parent_id, reason}]
    unverified: list[int] = field(default_factory=list)  # 1-based citation indices
    citations: list[dict] = field(default_factory=list)  # dumps with `verified` set


def evaluate_draft(
    drafted: DraftedSection,
    by_id: dict[str, ParentChunk],
    check=None,
    pass_ratio: float = 0.8,
    quote_threshold: float = 0.85,
) -> EvalReport:
    """Two-tier verdict. `check(pairs) -> list[bool]` is the batched entailment
    call (injected so tests never touch an LLM); None skips Tier 2, leaving
    Tier-1 verdicts standing.
    """
    if not drafted.citations:
        return EvalReport(eval_ok=False)

    cites: list[Citation] = [c.model_copy() for c in drafted.citations]

    tier1_failed = []
    for i, c in enumerate(cites, start=1):
        parent = by_id.get(c.parent_id)
        if parent is None:
            tier1_failed.append({"index": i, "parent_id": c.parent_id, "reason": "parent_id is not a retrieved source"})
        elif not quote_in_parent(c.quote, parent.text, quote_threshold):
            tier1_failed.append({"index": i, "parent_id": c.parent_id, "reason": "quote not found in the cited source"})
    if tier1_failed:
        return EvalReport(eval_ok=False, tier1_failed=tier1_failed)

    for c in cites:
        c.verified = "quote_verified"

    claims = extract_claims(drafted.text, len(cites))
    unverified = [i for i in range(1, len(cites) + 1) if i not in claims]  # markerless
    if claims and check is not None:
        indices = sorted(claims)
        verdicts = check([(claims[i], cites[i - 1].quote) for i in indices])
        unsupported = [i for i, ok in zip(indices, verdicts) if not ok]
        unverified += unsupported
        ratio = 1 - len(unsupported) / len(indices)
    else:
        ratio = 1.0

    for i in unverified:
        cites[i - 1].verified = "unverified"

    return EvalReport(
        eval_ok=ratio >= pass_ratio,
        unverified=sorted(unverified),
        citations=[c.model_dump() for c in cites],
    )
