import { useState, useRef, useCallback } from "react";
import {
  uploadDocuments,
  createJob,
  approveOutline,
  runJob,
  getSections,
} from "./api.js";
import { replayJob } from "./replay.js";
import Pipeline from "./Pipeline.jsx";

const EMPTY_VIZ = {
  activeNode: null,
  section: null,
  query: null,
  candidates: null,
  ranked: null,
  evalOk: null,
  log: [],
};

// Map an event (v1 replay shape == v2 SSE shape) onto viz state.
function reduceViz(v, ev) {
  const push = (line) => ({ ...v, log: [...v.log, line] });
  switch (ev.type) {
    case "job_start":
      return { ...EMPTY_VIZ, log: [`job started · ${ev.data.n_sections} sections`] };
    case "section_start":
      return {
        ...v,
        activeNode: "retrieve",
        section: { index: ev.section_index, title: ev.data.title },
        query: null,
        candidates: null,
        ranked: null,
        evalOk: null,
        log: [...v.log, `▸ section ${ev.section_index + 1}: ${ev.data.title}`],
      };
    case "retrieve_query":
      return { ...v, activeNode: "retrieve", query: ev.data.query };
    case "candidates":
      return {
        ...push(`retrieved ${ev.data.n_candidates} candidates`),
        activeNode: "retrieve",
        candidates: ev.data.sample,
      };
    case "deduped":
      return push(`deduped ${ev.data.n_before} → ${ev.data.n_after} parents`);
    case "reranked":
      return {
        ...push(`reranked → top ${ev.data.ranked.length}`),
        activeNode: "retrieve",
        ranked: ev.data.ranked,
      };
    case "draft_done":
      return {
        ...push(`drafted · ${ev.data.citations.length} citations`),
        activeNode: "draft",
      };
    case "evaluate":
      return {
        ...push(ev.data.eval_ok ? "evaluate: pass ✓" : "evaluate: redraft ↺"),
        activeNode: "evaluate",
        evalOk: ev.data.eval_ok,
      };
    case "committed":
      return { ...push("committed ✓"), activeNode: "commit" };
    case "job_done":
      return { ...push("document assembled ✓"), activeNode: null };
    default:
      return v;
  }
}

const STEPS = ["Upload", "Prompt", "Review", "Draft"];

export default function App() {
  const [step, setStep] = useState(0); // 0 upload,1 prompt,2 review,3 draft/done
  const [files, setFiles] = useState([]);
  const [drag, setDrag] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [jobId, setJobId] = useState(() => localStorage.getItem("lexi_job_id"));
  const [loadId, setLoadId] = useState("");
  const [outline, setOutline] = useState(null);
  const [sections, setSections] = useState(null);
  const [viz, setViz] = useState(EMPTY_VIZ);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [speed, setSpeed] = useState(1);
  const speedRef = useRef(1);

  // Remember the current job across refreshes so a finished doc isn't lost.
  const rememberJob = (id) => {
    localStorage.setItem("lexi_job_id", id);
    setJobId(id);
  };

  // Load a finished job's sections directly (skips the run; just view result).
  const onLoadJob = (id) =>
    guard(async () => {
      const target = (id || loadId || jobId || "").trim();
      if (!target) throw new Error("Enter a job id to load.");
      const { sections } = await getSections(target); // 409 if not done yet
      rememberJob(target);
      setSections(sections);
      setStep(3);
      setViz({ ...EMPTY_VIZ, activeNode: null, log: ["loaded finished job"] });
    });

  const guard = async (fn) => {
    setErr(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const onUpload = () =>
    guard(async () => {
      await uploadDocuments(files);
      setStep(1);
    });

  const onCreateJob = () =>
    guard(async () => {
      const { job_id, outline } = await createJob(prompt);
      rememberJob(job_id);
      setOutline(outline);
      setStep(2);
    });

  const onApproveAndRun = () =>
    guard(async () => {
      await approveOutline(jobId);
      setStep(3);
      setViz(EMPTY_VIZ);
      await runJob(jobId); // blocking in v1
      const { sections } = await getSections(jobId);
      setSections(sections);
      // Replay the pipeline animation from the real finished sections.
      await replayJob(
        sections,
        (ev) => setViz((v) => reduceViz(v, ev)),
        { speed: speedRef.current }
      );
    });

  const setSpeedBoth = useCallback((s) => {
    setSpeed(s);
    speedRef.current = s;
  }, []);

  const onFiles = (list) => setFiles(Array.from(list));

  return (
    <div className="app">
      {/* ---------- control rail ---------- */}
      <aside className="rail">
        <div className="brand">
          Lexi<b>Graph</b> · Console
        </div>
        <h1 className="wordmark">
          Draft, <em>grounded</em>.
        </h1>
        <p className="tagline">Upload precedent · propose an outline · watch it draft.</p>

        {/* Load a finished job by id (survives refresh; run is blocking in v1). */}
        <div className="loadjob">
          <input
            type="text"
            placeholder="job id — view a finished document"
            value={loadId}
            onChange={(e) => setLoadId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onLoadJob()}
          />
          <button className="ghost" disabled={busy} onClick={() => onLoadJob()}>
            Load
          </button>
        </div>
        {jobId && (
          <div className="hint" style={{ marginBottom: 14 }}>
            current job: <span className="filechip">{jobId.slice(0, 8)}…</span>
          </div>
        )}

        {STEPS.map((label, i) => (
          <div
            key={label}
            className={`step ${step === i ? "active" : ""} ${step > i ? "done" : ""}`}
          >
            <div className="step-label">
              <span className="step-num">{step > i ? "✓" : i + 1}</span>
              {label}
            </div>

            {i === 0 && step === 0 && (
              <>
                <div
                  className={`dropzone ${drag ? "drag" : ""}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    onFiles(e.dataTransfer.files);
                  }}
                  onClick={() => document.getElementById("fileinput").click()}
                >
                  Drop legal PDFs here, or click to choose
                </div>
                <input
                  id="fileinput"
                  type="file"
                  accept="application/pdf"
                  multiple
                  style={{ display: "none" }}
                  onChange={(e) => onFiles(e.target.files)}
                />
                <div className="filelist">
                  {files.map((f) => (
                    <span className="filechip" key={f.name}>
                      {f.name}
                    </span>
                  ))}
                </div>
                <div className="row">
                  <button className="seal" disabled={!files.length || busy} onClick={onUpload}>
                    {busy ? "Ingesting…" : "Ingest documents"}
                  </button>
                </div>
                <div className="hint">
                  Large PDFs take a while — Unstructured hi-res partitioning runs server-side.
                </div>
              </>
            )}

            {i === 1 && step === 1 && (
              <>
                <textarea
                  rows={4}
                  placeholder="e.g. Draft a Master Services Agreement covering scope, payment (Net terms), term, termination, and confidentiality."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                />
                <div className="row">
                  <button className="seal" disabled={!prompt.trim() || busy} onClick={onCreateJob}>
                    {busy ? "Proposing…" : "Propose outline"}
                  </button>
                </div>
              </>
            )}

            {i === 2 && step === 2 && outline && (
              <>
                {outline.sections.map((s) => (
                  <div className="outline-sec" key={s.section_id}>
                    <h4>{s.title}</h4>
                    <p>{s.instructions}</p>
                  </div>
                ))}
                <div className="row">
                  <button className="seal" disabled={busy} onClick={onApproveAndRun}>
                    {busy ? "Drafting…" : "Approve & draft"}
                  </button>
                </div>
                <div className="hint">
                  v1 approves as-is. Editing the outline before approval comes in v2.
                </div>
              </>
            )}
          </div>
        ))}

        {err && <div className="err">{err}</div>}
      </aside>

      {/* ---------- stage ---------- */}
      <main className="stage">
        <div className="stage-head">
          <h2>{sections ? "Document" : "Pipeline"}</h2>
          <span className="sub">
            {step < 3 ? "awaiting a run" : sections ? "drafted & cited" : "drafting…"}
          </span>
          {step === 3 && (
            <div className="speed" style={{ marginLeft: "auto" }}>
              speed
              {[1, 2, 4].map((s) => (
                <button
                  key={s}
                  className="ghost"
                  onClick={() => setSpeedBoth(s)}
                  style={{ opacity: speed === s ? 1 : 0.5 }}
                >
                  {s}×
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="stage-body">
          {step < 3 && (
            <div className="empty">
              <div>
                <div className="big">Nothing drafting yet.</div>
                <div>Ingest a document, propose an outline, and approve it to watch the loop run.</div>
              </div>
            </div>
          )}

          {step === 3 && <Pipeline viz={viz} />}

          {sections && (
            <div style={{ marginTop: 30 }}>
              {sections.map((s) => (
                <div className="doc-section" key={s.section_id}>
                  <h3>
                    {s.title}
                    {s.needs_review && <span className="needs-review">⚠ needs review</span>}
                  </h3>
                  <div className="body">{s.text}</div>
                  {s.citations.map((c, i) => (
                    <div className="cite" key={i}>
                      <span className="pid">[{c.parent_id.slice(0, 8)}]</span> {c.quote}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
