// §5 citation trust UX: a superscript chip that opens a popover with the source
// document, the verbatim quote, and its verification badge.

import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Citation } from "@/types";

const BADGES = {
  quote_verified: { label: "✓ quote verified", variant: "live" as const },
  entailed: { label: "◐ entailed", variant: "bronze" as const },
  unverified: { label: "⚠ unverified", variant: "alert" as const },
};

export default function CitationChip({ n, citation }: { n: number; citation?: Citation }) {
  if (!citation) return <sup className="text-counsel">[{n}]</sup>;
  const badge = citation.verified ? BADGES[citation.verified] : null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <sup>
          <button className="cursor-pointer rounded px-0.5 font-mono text-[0.8em] text-counsel hover:bg-counsel/10 print:pointer-events-none">
            [{n}]
          </button>
        </sup>
      </PopoverTrigger>
      <PopoverContent className="no-print text-sm">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="truncate font-mono text-xs text-ink-soft">{citation.source_file || "unknown source"}</span>
          {badge && <Badge variant={badge.variant}>{badge.label}</Badge>}
        </div>
        <blockquote className="border-l-2 border-counsel pl-2 leading-snug">
          <mark className="bg-emerald-live/20 text-ink">“{citation.quote}”</mark>
        </blockquote>
      </PopoverContent>
    </Popover>
  );
}
