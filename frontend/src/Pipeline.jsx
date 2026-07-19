import { motion, AnimatePresence } from "framer-motion";

// Pure view: renders the live pipeline state derived from events. Driven by the
// parent (App) which feeds it the current event-derived `viz` object. The SAME
// component works for v1 replay and v2 SSE — it only reads viz state.

const NODES = [
  { key: "retrieve", label: "retrieve", sub: "hybrid + rerank" },
  { key: "draft", label: "draft", sub: "LLM · grounded" },
  { key: "evaluate", label: "evaluate", sub: "D4 gate" },
  { key: "commit", label: "commit", sub: "save section" },
];

const pulse = {
  active: {
    scale: [1, 1.05, 1],
    boxShadow: [
      "0 0 0 rgba(138,43,31,0)",
      "0 0 0 6px rgba(138,43,31,0.12)",
      "0 0 0 rgba(138,43,31,0)",
    ],
    transition: { duration: 1.1, repeat: Infinity },
  },
  idle: { scale: 1, boxShadow: "0 0 0 rgba(0,0,0,0)" },
};

export default function Pipeline({ viz }) {
  const { activeNode, section, query, candidates, ranked, evalOk, log } = viz;

  return (
    <div>
      <div className="pipe">
        {NODES.map((n, i) => (
          <div key={n.key} style={{ display: "contents" }}>
            <motion.div
              className={`node ${n.key}`}
              variants={pulse}
              animate={activeNode === n.key ? "active" : "idle"}
            >
              <div className="nlabel">{n.label}</div>
              <div className="nsub">{n.sub}</div>
              <div className="nmeta">
                {n.key === "retrieve" && candidates?.length
                  ? `${candidates.length} candidates`
                  : ""}
                {n.key === "evaluate" && evalOk === true ? "pass ✓" : ""}
                {n.key === "evaluate" && evalOk === false ? "redraft ↺" : ""}
              </div>
            </motion.div>
            {i < NODES.length - 1 && <span className="arrow">→</span>}
          </div>
        ))}
      </div>

      {section && (
        <div className="logline" style={{ marginBottom: 12 }}>
          <b>§ {section.index + 1}</b> &nbsp;{section.title}
        </div>
      )}

      {query && (
        <div className="log" style={{ marginBottom: 14 }}>
          <span className="logline">
            query&nbsp; <b>{query}</b>
          </span>
        </div>
      )}

      {/* candidate chunks flying in, then reranked top set highlighted */}
      <AnimatePresence mode="popLayout">
        {(ranked?.length ? ranked : candidates ?? []).map((c, idx) => (
          <motion.span
            key={c.parent_id + idx}
            layout
            initial={{ opacity: 0, x: -18 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, scale: 0.85 }}
            transition={{ duration: 0.35, delay: idx * 0.04 }}
            className={`chunk ${ranked?.length ? "top" : ""}`}
            title={c.parent_id}
          >
            {ranked?.length ? `#${c.rank} ` : ""}
            {(c.snippet || c.parent_id).slice(0, 46) || c.parent_id}
          </motion.span>
        ))}
      </AnimatePresence>

      <div className="log" style={{ marginTop: 20 }}>
        {log.slice(-8).map((l, i) => (
          <div className="logline" key={i}>
            {l}
          </div>
        ))}
      </div>
    </div>
  );
}
