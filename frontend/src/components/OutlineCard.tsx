// Interactive outline card: inline edit title/instructions, add/remove/reorder,
// then Approve & draft. Once the job leaves outline_pending the card locks.

import { ArrowDown, ArrowUp, Play, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useStore } from "@/store";
import type { Outline } from "@/types";

export default function OutlineCard({ jobId, outline }: { jobId: string; outline: Outline }) {
  const { outlineDrafts, editOutline, approveAndRun, busy, live, doc } = useStore();
  const draft = outlineDrafts[jobId] ?? outline;
  const locked = outline.approved || live?.jobId === jobId || doc?.jobId === jobId;

  const update = (sections: Outline["sections"]) => editOutline(jobId, { ...draft, sections });
  const move = (i: number, d: number) => {
    const s = [...draft.sections];
    [s[i], s[i + d]] = [s[i + d], s[i]];
    update(s);
  };

  return (
    <Card className="my-2">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="font-mono text-xs uppercase tracking-widest text-ink-soft">
          Proposed outline · {draft.sections.length} sections
        </CardTitle>
        {!locked && (
          <Button size="sm" onClick={() => approveAndRun(jobId)} disabled={busy}>
            <Play /> Approve & draft
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {draft.sections.map((sec, i) => (
          <div key={sec.section_id} className="rounded-md border border-border bg-paper p-3">
            {locked ? (
              <>
                <div className="font-medium">{i + 1}. {sec.title}</div>
                <p className="mt-1 text-sm text-ink-soft">{sec.instructions}</p>
              </>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-1">
                  <Input
                    value={sec.title}
                    onChange={(e) => update(draft.sections.map((s, k) => (k === i ? { ...s, title: e.target.value } : s)))}
                  />
                  <Button size="icon" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">
                    <ArrowUp />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    disabled={i === draft.sections.length - 1}
                    onClick={() => move(i, 1)}
                    aria-label="Move down"
                  >
                    <ArrowDown />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => update(draft.sections.filter((_, k) => k !== i))}
                    aria-label="Remove section"
                  >
                    <Trash2 className="text-alert" />
                  </Button>
                </div>
                <Textarea
                  value={sec.instructions}
                  onChange={(e) =>
                    update(draft.sections.map((s, k) => (k === i ? { ...s, instructions: e.target.value } : s)))
                  }
                />
              </div>
            )}
            {sec.source_files && sec.source_files.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {sec.source_files.map((f) => (
                  <Badge key={f} variant="bronze">{f}</Badge>
                ))}
              </div>
            ) : (
              sec.source_files && <p className="mt-2 text-xs text-ink-soft">no supporting documents</p>
            )}
          </div>
        ))}
        {!locked && (
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              update([
                ...draft.sections,
                { section_id: crypto.randomUUID(), title: "New section", instructions: "" },
              ])
            }
          >
            <Plus /> Add section
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
