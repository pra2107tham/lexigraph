// Reducer contract test: the full §7 event sequence folds into sane viz state.
import { describe, expect, it } from "vitest";

import { applyVizEvent, EMPTY_VIZ, type Viz } from "./viz";
import type { PipelineEvent } from "@/types";

const SEQUENCE: PipelineEvent[] = [
  { type: "job_start", data: { n_sections: 2, section_titles: ["A", "B"] } },
  { type: "section_start", section_id: "s1", section_index: 0, data: { title: "A", index: 0 } },
  { type: "retrieve_query", section_id: "s1", data: { query: "A — details" } },
  { type: "candidates", section_id: "s1", data: { n_candidates: 50, sample: [{ parent_id: "p1", snippet: "x" }] } },
  { type: "deduped", section_id: "s1", data: { n_before: 50, n_after: 4, parent_ids: ["p1"] } },
  { type: "reranked", section_id: "s1", data: { ranked: [{ parent_id: "p1", snippet: "x", rank: 1 }] } },
  { type: "draft_start", section_id: "s1", data: { attempt: 1 } },
  { type: "draft_done", section_id: "s1", data: { text_preview: "t", citations: [{}] } },
  { type: "evaluate", section_id: "s1", data: { eval_ok: false, attempt: 1, tier1_failed: [{ index: 1 }], unverified: [] } },
  { type: "redraft", section_id: "s1", data: { attempt: 2, max: 3 } },
  { type: "draft_start", section_id: "s1", data: { attempt: 2 } },
  { type: "draft_done", section_id: "s1", data: { text_preview: "t", citations: [{}] } },
  { type: "evaluate", section_id: "s1", data: { eval_ok: true, attempt: 2, tier1_failed: [], unverified: [] } },
  { type: "section_committed", section_id: "s1", data: { section_id: "s1", needs_review: false } },
  { type: "job_done", data: {} },
];

const run = (events: PipelineEvent[], from: Viz = EMPTY_VIZ) => events.reduce(applyVizEvent, from);

describe("applyVizEvent", () => {
  it("folds the full spec sequence", () => {
    const v = run(SEQUENCE);
    expect(v.nSections).toBe(2);
    expect(v.activeNode).toBeNull(); // job_done clears
    expect(v.log.at(-1)).toContain("assembled");
    expect(v.log.join("\n")).toContain("redraft ↺ attempt 2/3");
    expect(v.log.join("\n")).toContain("1 bad quotes");
  });

  it("section_start resets per-section state but keeps the log", () => {
    const mid = run(SEQUENCE.slice(0, 6));
    const next = applyVizEvent(mid, { type: "section_start", section_index: 1, data: { title: "B", index: 1 } });
    expect(next.candidates).toBeNull();
    expect(next.section?.title).toBe("B");
    expect(next.log.length).toBeGreaterThan(0);
  });

  it("handles reconnect snapshot and error frames", () => {
    const v = applyVizEvent(EMPTY_VIZ, { type: "job_snapshot", data: { cursor: 3, committed_sections: [1, 2, 3] } });
    expect(v.log[0]).toContain("3 sections committed");
    const e = applyVizEvent(v, { type: "error", data: { where: "run", message: "boom" } });
    expect(e.log.at(-1)).toContain("boom");
    expect(e.activeNode).toBeNull();
  });
});
