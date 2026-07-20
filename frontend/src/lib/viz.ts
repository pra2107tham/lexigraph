// Pure event -> viz-state reducer (typed port of the v1 reduceViz), under the
// §7 spec event names. Driven identically by replay (step 5) and SSE (step 6).

import type { PipelineEvent } from "@/types";

export interface Viz {
  activeNode: "retrieve" | "draft" | "evaluate" | "commit" | null;
  section: { index: number; title: string } | null;
  nSections: number;
  query: string | null;
  candidates: { parent_id: string; snippet: string }[] | null;
  ranked: { parent_id: string; snippet: string; rank: number }[] | null;
  evalOk: boolean | null;
  attempt: number;
  log: string[];
}

export const EMPTY_VIZ: Viz = {
  activeNode: null,
  section: null,
  nSections: 0,
  query: null,
  candidates: null,
  ranked: null,
  evalOk: null,
  attempt: 0,
  log: [],
};

export function applyVizEvent(v: Viz, ev: PipelineEvent): Viz {
  const push = (line: string): Viz => ({ ...v, log: [...v.log, line] });
  switch (ev.type) {
    case "job_start":
      return { ...EMPTY_VIZ, nSections: ev.data.n_sections, log: [`job started · ${ev.data.n_sections} sections`] };
    case "job_snapshot":
      return {
        ...v,
        nSections: v.nSections || (ev.data.cursor ?? 0) + 1,
        log: [...v.log, `reconnected · ${ev.data.committed_sections?.length ?? 0} sections committed`],
      };
    case "section_start":
      return {
        ...v,
        activeNode: "retrieve",
        section: { index: ev.section_index ?? ev.data.index, title: ev.data.title },
        query: null,
        candidates: null,
        ranked: null,
        evalOk: null,
        attempt: 0,
        log: [...v.log, `▸ section ${(ev.section_index ?? ev.data.index) + 1}: ${ev.data.title}`],
      };
    case "retrieve_query":
      return { ...v, activeNode: "retrieve", query: ev.data.query };
    case "candidates":
      return { ...push(`retrieved ${ev.data.n_candidates} candidates`), activeNode: "retrieve", candidates: ev.data.sample };
    case "deduped":
      return push(`deduped ${ev.data.n_before} → ${ev.data.n_after} parents`);
    case "reranked":
      return { ...push(`reranked → top ${ev.data.ranked.length}`), activeNode: "retrieve", ranked: ev.data.ranked };
    case "draft_start":
      return { ...push(`drafting · attempt ${ev.data.attempt}`), activeNode: "draft", attempt: ev.data.attempt };
    case "draft_done":
      return { ...push(`drafted · ${ev.data.citations.length} citations`), activeNode: "draft" };
    case "evaluate":
      return {
        ...push(
          ev.data.eval_ok
            ? "evaluate: pass ✓"
            : `evaluate: fail (${ev.data.tier1_failed?.length ?? 0} bad quotes, ${ev.data.unverified?.length ?? 0} unverified)`,
        ),
        activeNode: "evaluate",
        evalOk: ev.data.eval_ok,
      };
    case "redraft":
      return push(`redraft ↺ attempt ${ev.data.attempt}/${ev.data.max}`);
    case "section_committed":
      return { ...push(ev.data.needs_review ? "committed ⚠ needs review" : "committed ✓"), activeNode: "commit" };
    case "job_done":
      return { ...push("document assembled ✓"), activeNode: null };
    case "error":
      return { ...push(`✗ error in ${ev.data.where}: ${ev.data.message}`), activeNode: null };
    default:
      return v;
  }
}
