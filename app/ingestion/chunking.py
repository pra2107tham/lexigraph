"""Derive child chunks from parent chunks (decision D1).

Unstructured's `by_title` chunking yields ONE level of chunks (CompositeElements
capped at max_characters) — the parents. There is no native second level, so we
create children ourselves by sub-splitting each parent into ~256-token windows
with a small overlap. Children are embedded for high-precision matching; the
parent is what we ultimately return to the LLM.

Tokenization here is a word-count approximation (whitespace split). Chunk
boundaries don't need exact BPE token counts — a ~1.3x words->tokens ratio is
close enough for retrieval windows, and it avoids a tokenizer dependency.
"""

from __future__ import annotations

from app.models import ChildChunk, ParentChunk


def _split_words(text: str) -> list[str]:
    return text.split()


def derive_children(
    parent: ParentChunk,
    target_tokens: int = 256,
    overlap_tokens: int = 20,
) -> list[ChildChunk]:
    """Sub-split a parent into overlapping child windows.

    A parent shorter than one window becomes a single child (never zero), so
    every parent is retrievable.
    """
    words = _split_words(parent.text)
    if not words:
        return []

    # Approximate: ~0.75 words per token -> window measured in words.
    window = max(1, int(target_tokens * 0.75))
    overlap = max(0, int(overlap_tokens * 0.75))
    step = max(1, window - overlap)

    children: list[ChildChunk] = []
    for start in range(0, len(words), step):
        chunk_words = words[start : start + window]
        if not chunk_words:
            break
        children.append(
            ChildChunk(parent_id=parent.parent_id, text=" ".join(chunk_words))
        )
        if start + window >= len(words):
            break  # last window reached the end; don't emit a trailing dup
    return children
