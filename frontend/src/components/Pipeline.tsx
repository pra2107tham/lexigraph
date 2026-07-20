// Live pipeline viz — recolored port of v1. Pure and prop-driven: renders one
// Viz snapshot; the store folds replay/SSE events into it.

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";
import type { Viz } from "@/lib/viz";

const NODES = [
  { key: "retrieve", label: "retrieve", sub: "hybrid + rerank", color: "var(--counsel)" },
  { key: "draft", label: "draft", sub: "LLM · grounded", color: "var(--ink)" },
  { key: "evaluate", label: "evaluate", sub: "two-tier gate", color: "var(--bronze)" },
  { key: "commit", label: "commit", sub: "save section", color: "var(--emerald-live)" },
] as const;

export default function Pipeline({ viz }: { viz: Viz }) {
  const reduced = useReducedMotion();
  const { activeNode, section, query, candidates, ranked, log } = viz;

  return (
    <div className="font-mono text-xs">
      {section && (
        <div className="mb-3 text-ink-soft">
          §{section.index + 1}
          {viz.nSections ? ` of ${viz.nSections}` : ""} — <span className="text-ink">{section.title}</span>
        </div>
      )}

      <div className="mb-4 flex items-center gap-2">
        {NODES.map((n, i) => (
          <div key={n.key} className="flex items-center gap-2">
            {i > 0 && <span className="text-rule">→</span>}
            <motion.div
              className={cn(
                "rounded-md border px-3 py-2",
                activeNode === n.key ? "border-current bg-paper" : "border-border bg-paper-deep opacity-70",
              )}
              style={{ color: n.color }}
              animate={
                activeNode === n.key && !reduced
                  ? { scale: [1, 1.05, 1], boxShadow: ["0 0 0 rgba(46,139,106,0)", "0 0 14px rgba(46,139,106,0.45)", "0 0 0 rgba(46,139,106,0)"] }
                  : { scale: 1, boxShadow: "none" }
              }
              transition={{ repeat: activeNode === n.key && !reduced ? Infinity : 0, duration: 1.4 }}
            >
              <div className="font-semibold">{n.label}</div>
              <div className="text-[10px] text-ink-soft">{n.sub}</div>
            </motion.div>
          </div>
        ))}
      </div>

      {query && <div className="mb-2 truncate text-ink-soft">query: “{query}”</div>}

      <AnimatePresence mode="popLayout">
        {(ranked ?? candidates)?.map((c, idx) => (
          <motion.div
            key={`${c.parent_id}-${idx}`}
            layout
            initial={reduced ? false : { opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ delay: idx * 0.04 }}
            className={cn(
              "mb-1 truncate rounded border px-2 py-1",
              ranked ? "border-counsel/40 bg-counsel/5" : "border-border bg-paper-deep",
            )}
          >
            <span className="text-counsel">[{c.parent_id.slice(0, 8)}]</span> {c.snippet}
          </motion.div>
        ))}
      </AnimatePresence>

      {log.length > 0 && (
        <div className="mt-3 border-t border-border pt-2 text-ink-soft">
          {log.slice(-8).map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      )}
    </div>
  );
}
