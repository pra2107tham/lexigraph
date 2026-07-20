import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";

export default function SessionSidebar() {
  const { sessions, activeSessionId, newSession, openSession, busy } = useStore();

  return (
    <aside className="no-print flex h-full flex-col border-r border-border bg-paper-deep/60">
      <div className="flex items-center justify-between p-3">
        <span className="font-mono text-xs uppercase tracking-widest text-ink-soft">Sessions</span>
        <Button size="sm" variant="outline" onClick={newSession} disabled={busy}>
          <Plus /> New
        </Button>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {sessions.map((s) => (
          <button
            key={s.session_id}
            onClick={() => openSession(s.session_id)}
            className={cn(
              "mb-1 block w-full truncate rounded-md border-l-2 px-3 py-2 text-left text-sm hover:bg-paper",
              s.session_id === activeSessionId
                ? "border-counsel bg-paper font-medium"
                : "border-transparent text-ink-soft",
            )}
          >
            {s.title || "Untitled session"}
          </button>
        ))}
        {sessions.length === 0 && (
          <p className="px-3 py-2 text-sm text-ink-soft">No sessions yet — start one.</p>
        )}
      </nav>
    </aside>
  );
}
