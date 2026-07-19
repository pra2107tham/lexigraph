// Replay driver: synthesizes the §7 event sequence from a finished job's
// sections so the pipeline animates. Removed in step 6 when SSE streams live.

import type { PipelineEvent, Section } from "@/types";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function replayJob(
  sections: Section[],
  emit: (ev: PipelineEvent) => void,
  speed = 2,
): Promise<void> {
  const t = (ms: number) => wait(ms / speed);
  emit({ type: "job_start", data: { n_sections: sections.length, section_titles: sections.map((s) => s.title) } });
  await t(400);

  for (let i = 0; i < sections.length; i++) {
    const sec = sections[i];
    const cites = sec.citations ?? [];
    const sample = cites.slice(0, 5).map((c, r) => ({
      parent_id: c.parent_id,
      snippet: (c.quote ?? "").slice(0, 90),
      rank: r + 1,
    }));
    const emitSec = (type: PipelineEvent["type"], data: PipelineEvent["data"]) =>
      emit({ type, section_id: sec.section_id, section_index: i, data });

    emitSec("section_start", { title: sec.title, index: i });
    await t(350);
    emitSec("retrieve_query", { query: `${sec.title} — ${sec.instructions ?? ""}`.trim() });
    await t(450);
    emitSec("candidates", { n_candidates: Math.max(cites.length * 6, 12), sample });
    await t(500);
    emitSec("deduped", {
      n_before: Math.max(cites.length * 6, 12),
      n_after: Math.max(cites.length, 1),
      parent_ids: cites.map((c) => c.parent_id),
    });
    await t(400);
    emitSec("reranked", { ranked: sample });
    await t(500);
    emitSec("draft_start", { attempt: 1 });
    await t(300);
    emitSec("draft_done", { text_preview: (sec.text ?? "").slice(0, 220), citations: cites });
    await t(450);
    emitSec("evaluate", { eval_ok: true, attempt: 1, tier1_failed: [], unverified: [] });
    await t(350);
    emitSec("section_committed", { ...sec, needs_review: sec.needs_review ?? false });
    await t(400);
  }
  emit({ type: "job_done", data: {} });
}
