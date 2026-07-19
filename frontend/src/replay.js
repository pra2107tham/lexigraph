// v1 replay driver.
//
// v2 will stream the SAME event shapes live over SSE. In v1 we synthesize them
// from the finished job's structured sections, so the animation code (Pipeline.jsx)
// is identical across v1 and v2 — only the event SOURCE changes later.
//
// Event contract (subset of the v2 spec, §5.2):
//   job_start, section_start, retrieve_query, candidates, deduped, reranked,
//   draft_done, evaluate, committed, job_done
//
// replayJob(sections, emit, opts) calls emit(event) on a timed schedule and
// resolves when done. `emit` returns nothing; caller drives state from events.

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

export async function replayJob(sections, emit, { speed = 1 } = {}) {
  const t = (ms) => wait(ms / speed);

  emit({
    type: "job_start",
    data: {
      n_sections: sections.length,
      section_titles: sections.map((s) => s.title),
    },
  });
  await t(400);

  for (let i = 0; i < sections.length; i++) {
    const sec = sections[i];
    const cites = sec.citations ?? [];
    const parentIds = cites.map((c) => c.parent_id);

    emit({
      type: "section_start",
      section_id: sec.section_id,
      section_index: i,
      data: { title: sec.title, index: i },
    });
    await t(350);

    emit({
      type: "retrieve_query",
      section_id: sec.section_id,
      data: { query: `${sec.title} — ${sec.instructions ?? ""}`.trim() },
    });
    await t(450);

    // In v1 we don't have the raw 50 candidates; we approximate the wide net
    // from the real cited parents (the ones that actually survived to the draft).
    emit({
      type: "candidates",
      section_id: sec.section_id,
      data: {
        n_candidates: Math.max(parentIds.length * 6, 12),
        sample: cites.slice(0, 5).map((c) => ({
          parent_id: c.parent_id,
          snippet: (c.quote ?? "").slice(0, 90),
        })),
      },
    });
    await t(500);

    emit({
      type: "deduped",
      section_id: sec.section_id,
      data: {
        n_before: Math.max(parentIds.length * 6, 12),
        n_after: Math.max(parentIds.length, 1),
        parent_ids: parentIds,
      },
    });
    await t(400);

    emit({
      type: "reranked",
      section_id: sec.section_id,
      data: {
        ranked: cites.slice(0, 5).map((c, r) => ({
          parent_id: c.parent_id,
          snippet: (c.quote ?? "").slice(0, 90),
          rank: r + 1,
        })),
      },
    });
    await t(500);

    emit({
      type: "draft_done",
      section_id: sec.section_id,
      data: {
        text_preview: (sec.text ?? "").slice(0, 220),
        citations: cites,
      },
    });
    await t(450);

    // v1 shows the real committed result as a pass. (The redraft loop isn't
    // observable from final state — v2's live stream will surface real failures.)
    emit({
      type: "evaluate",
      section_id: sec.section_id,
      data: { eval_ok: true, attempt: 1, failures: [] },
    });
    await t(350);

    emit({
      type: "committed",
      section_id: sec.section_id,
      data: { section_id: sec.section_id, needs_review: false },
    });
    await t(400);
  }

  emit({ type: "job_done", data: {} });
}
