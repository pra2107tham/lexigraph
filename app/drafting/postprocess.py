"""Deterministic cleanup of drafted section text (§3 defense-in-depth).

Prompts drift: models still slip parent_id UUIDs into prose, repeat the section
title, or number citation markers out of order. `clean_section` repairs all
three; it is idempotent, so it also runs at read time on legacy v1 rows.
"""

from __future__ import annotations

import re

from app.models import Citation

_UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
# [uuid], (uuid), [parent_id: uuid] — any bracketed UUID-shaped token.
_UUID_TOKEN = re.compile(rf"[\[\(]\s*(?:parent[_ ]?id\s*[:=]?\s*)?{_UUID}\s*[\]\)]")
_MARKER = re.compile(r"\[(\d+)\]")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[#*_`]", "", s)).strip().casefold()


def clean_section(text: str, title: str, citations: list[Citation]) -> tuple[str, list[Citation]]:
    """Strip UUID tokens, drop a duplicated leading title, renumber markers.

    Markers are renumbered 1..k in order of first appearance and `citations`
    reordered to match; markers with no backing citation are removed; citations
    never referenced keep their relative order at the tail.
    """
    text = _UUID_TOKEN.sub("", text)

    head, _, rest = text.lstrip().partition("\n")
    if _norm(title) and _norm(head) == _norm(title):
        text = rest

    # Renumber: distinct in-range markers, in order of first appearance.
    seen: dict[int, int] = {}
    for m in _MARKER.finditer(text):
        n = int(m.group(1))
        if 1 <= n <= len(citations) and n not in seen:
            seen[n] = len(seen) + 1

    def _sub(m: re.Match) -> str:
        return f"[{seen[int(m.group(1))]}]" if int(m.group(1)) in seen else ""

    text = _MARKER.sub(_sub, text).strip()
    referenced = [citations[n - 1] for n in seen]
    tail = [c for i, c in enumerate(citations, start=1) if i not in seen]
    return text, referenced + tail
