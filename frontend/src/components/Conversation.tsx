// Middle pane: the session timeline + composer. Message renderers are small,
// so they live here; OutlineCard and DraftingLive have their own files.

import { FileText, Paperclip, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import DraftingLive from "@/components/DraftingLive";
import OutlineCard from "@/components/OutlineCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useStore } from "@/store";
import type { Message } from "@/types";

function MessageView({ m }: { m: Message }) {
  const { loadFinishedJob } = useStore();
  switch (m.type) {
    case "user_prompt":
      return (
        <div className="my-2 ml-auto max-w-[85%] rounded-lg bg-counsel px-4 py-2 text-paper">
          {m.data.text}
        </div>
      );
    case "ingest_receipt":
      return (
        <div className="my-1 flex items-center gap-2 font-mono text-xs text-ink-soft">
          <FileText className="size-3.5 text-counsel" />
          Indexed <span className="text-ink">{m.data.source_file}</span> — {m.data.n_parents} passages
        </div>
      );
    case "outline_card":
      return <OutlineCard jobId={m.data.job_id} outline={m.data.outline} />;
    case "drafting_live":
      return <DraftingLive jobId={m.data.job_id} />;
    case "document_ready":
      return (
        <button
          onClick={() => loadFinishedJob(m.data.job_id)}
          className="my-2 flex w-full items-center gap-3 rounded-lg border border-counsel/30 bg-paper-deep/60 px-4 py-3 text-left hover:bg-paper-deep"
        >
          <span className="text-lg">✓</span>
          <span className="text-sm">
            Document ready — {m.data.n_sections} sections · {m.data.n_citations} citations
            {m.data.n_flagged > 0 && (
              <Badge variant="alert" className="ml-2">{m.data.n_flagged} flagged</Badge>
            )}
          </span>
        </button>
      );
    case "revision":
      return (
        <div className="my-2 ml-auto max-w-[85%] rounded-lg bg-counsel/80 px-4 py-2 text-sm text-paper">
          Revise section: {m.data.instructions}
        </div>
      );
    default:
      return null;
  }
}

export default function Conversation() {
  const { activeSessionId, sessionTitle, timeline, sessionDocs, removeDoc, sendPrompt, busy, error } =
    useStore();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [timeline.length]);

  if (!activeSessionId) {
    return (
      <main className="flex h-full items-center justify-center text-ink-soft">
        <p>Start a new session to hand your junior associate some PDFs.</p>
      </main>
    );
  }

  const submit = async () => {
    if (!text.trim() && files.length === 0) return;
    await sendPrompt(text, files);
    setText("");
    setFiles([]);
  };

  return (
    <main className="flex h-full min-w-0 flex-col">
      <header className="no-print border-b border-border px-4 py-2">
        <div className="font-mono text-xs uppercase tracking-widest text-ink-soft">
          {sessionTitle || "New session"}
        </div>
        {sessionDocs.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {sessionDocs.map((d) => (
              <Badge key={d.mongo_doc_id} variant="outline" title={d.abstract}>
                <FileText className="mr-1 size-3 text-counsel" />
                {d.source_file}
                <button
                  onClick={() => void removeDoc(d.mongo_doc_id)}
                  className="ml-1 hover:text-alert"
                  aria-label={`Remove ${d.source_file}`}
                  disabled={busy}
                >
                  ×
                </button>
              </Badge>
            ))}
          </div>
        )}
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {timeline.map((m) => (
          <MessageView key={m.id} m={m} />
        ))}
        {error && <div className="my-2 rounded-md border border-alert/40 bg-alert/10 px-3 py-2 text-sm text-alert">{error}</div>}
        <div ref={bottom} />
      </div>
      <footer className="no-print border-t border-border p-3">
        {files.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {files.map((f) => (
              <Badge key={f.name} variant="outline">{f.name}</Badge>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            multiple
            hidden
            onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])])}
          />
          <Button variant="outline" size="icon" onClick={() => fileInput.current?.click()} aria-label="Attach PDFs">
            <Paperclip />
          </Button>
          <Textarea
            value={text}
            placeholder="Ask for a draft, a summary, or attach precedent PDFs…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
            className="max-h-40"
          />
          <Button onClick={() => void submit()} disabled={busy} aria-label="Send">
            <Send />
          </Button>
        </div>
      </footer>
    </main>
  );
}
