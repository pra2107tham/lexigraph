// §5: the first thing a liability-conscious advocate looks for — document-level
// verification stats, with jump links to any flagged sections.

import { Badge } from "@/components/ui/badge";
import type { Section } from "@/types";

export default function VerificationSummary({ sections }: { sections: Section[] }) {
  const citations = sections.flatMap((s) => s.citations);
  const verified = citations.filter((c) => c.verified === "quote_verified" || c.verified === "entailed");
  const flagged = sections.filter((s) => s.needs_review);
  if (citations.length === 0) return null;
  const pct = Math.round((100 * verified.length) / citations.length);

  return (
    <div className="mb-6 rounded-lg border border-counsel/30 bg-paper-deep/50 px-4 py-3 font-mono text-xs">
      <div className="mb-1 uppercase tracking-widest text-ink-soft">Verification</div>
      <div className="flex flex-wrap items-center gap-3">
        <span>{citations.length} claims</span>
        <Badge variant={pct >= 90 ? "live" : "bronze"}>{pct}% verified</Badge>
        {flagged.length > 0 ? (
          <span className="flex flex-wrap items-center gap-1 text-alert">
            {flagged.length} flagged:
            {flagged.map((s) => (
              <a key={s.section_id} href={`#sec-${s.section_id}`} className="underline">
                {s.title}
              </a>
            ))}
          </span>
        ) : (
          <span className="text-counsel">no flagged sections</span>
        )}
      </div>
    </div>
  );
}
