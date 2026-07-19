// Right pane: the drafted document, rendered as real markdown with per-section
// citation footers. Fills section by section once SSE lands (step 6).

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { useStore } from "@/store";

export default function DocumentPanel() {
  const { doc } = useStore();

  if (!doc) {
    return (
      <aside className="doc-panel hidden h-full items-center justify-center border-l border-border bg-paper lg:flex">
        <p className="max-w-xs text-center text-sm text-ink-soft">
          The drafted document renders here, section by section, with verifiable citations.
        </p>
      </aside>
    );
  }

  return (
    <aside className="doc-panel h-full overflow-y-auto border-l border-border bg-paper px-6 py-4">
      {doc.sections.map((s) => (
        <section key={s.section_id} className="mb-8">
          <h2 className="mb-2 flex items-center gap-2 border-b border-border pb-1 text-lg font-semibold">
            {s.title}
            {s.needs_review && <Badge variant="alert">⚠ needs review</Badge>}
          </h2>
          <div className="prose-sm leading-relaxed [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:ml-4 [&_li]:list-disc [&_p]:my-2 [&_strong]:font-semibold">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.text}</ReactMarkdown>
          </div>
          {s.citations.length > 0 && (
            <div className="mt-3 border-t border-border/60 pt-2 font-mono text-[11px] text-ink-soft">
              {s.citations.map((c, i) => (
                <div key={i} className="mb-1">
                  <span className="text-counsel">[{i + 1}]</span> {c.source_file || "source"} — “{c.quote}”
                </div>
              ))}
            </div>
          )}
        </section>
      ))}
    </aside>
  );
}
