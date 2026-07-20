"""§7 SSE plumbing: per-job in-process event queues.

Emitters run inside the Burr worker thread; the async SSE generator consumes on
the event loop via asyncio.to_thread — queue.Queue is thread-safe on both ends.
emit() is a no-op when no channel is open, so the blocking /run path and every
unit test work unchanged.

# ponytail: in-process queues, one consumer per job (last connection wins).
# A broker (Redis/NATS) only when multi-worker fan-out is real.
"""

from __future__ import annotations

import json
import queue

_queues: dict[str, queue.Queue] = {}


def channel(job_id: str) -> queue.Queue:
    return _queues.setdefault(job_id, queue.Queue())


def close(job_id: str) -> None:
    _queues.pop(job_id, None)


def is_open(job_id: str) -> bool:
    return job_id in _queues


def emit(
    job_id: str,
    type: str,  # noqa: A002 — mirrors the wire field name
    section_id: str | None = None,
    section_index: int | None = None,
    **data,
) -> None:
    q = _queues.get(job_id)
    if q is None:
        return
    event: dict = {"type": type, "data": data}
    if section_id is not None:
        event["section_id"] = section_id
    if section_index is not None:
        event["section_index"] = section_index
    q.put(event)


def sse(event: dict) -> str:
    """Encode one event as an SSE data-only frame."""
    return f"data: {json.dumps(event)}\n\n"
