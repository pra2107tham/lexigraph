// The live drafting chat block (§2): collapsed one-line status with a pulse,
// expandable to the full pipeline viz — modeled on Claude's tool-use blocks.

import { ChevronDown, ChevronRight, RotateCcw } from "lucide-react";
import { useState } from "react";

import Pipeline from "@/components/Pipeline";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store";

export default function DraftingLive({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const { live, approveAndRun, busy } = useStore();
  if (live?.jobId !== jobId) return null; // superseded by document_ready on reload

  const { viz, status } = live;
  const statusLine =
    status === "failed"
      ? "drafting failed"
      : viz.section
        ? `Drafting §${viz.section.index + 1}${viz.nSections ? ` of ${viz.nSections}` : ""} — ${viz.activeNode ?? "…"}`
        : status === "done"
          ? "Document assembled"
          : "Starting run…";

  return (
    <div className="my-2 rounded-lg border border-border bg-paper-deep/50">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 font-mono text-xs text-ink-soft"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        {status === "running" && <span className="size-2 animate-pulse rounded-full bg-emerald-live" />}
        {status === "failed" && <span className="size-2 rounded-full bg-alert" />}
        <span>{statusLine}</span>
      </button>
      {status === "failed" && (
        <div className="px-3 pb-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => approveAndRun(jobId)}>
            <RotateCcw /> Retry
          </Button>
        </div>
      )}
      {open && (
        <div className="border-t border-border p-3">
          <Pipeline viz={viz} />
        </div>
      )}
    </div>
  );
}
