// Three-pane chat shell (§2): sessions | conversation | document panel.
// Collapses to conversation-only below lg; the doc panel hides, sidebar narrows.

import { useEffect } from "react";

import Conversation from "@/components/Conversation";
import DocumentPanel from "@/components/DocumentPanel";
import SessionSidebar from "@/components/SessionSidebar";
import { useStore } from "@/store";

export default function App() {
  const loadSessions = useStore((s) => s.loadSessions);
  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  return (
    <div className="grid h-screen grid-cols-[220px_1fr] lg:grid-cols-[240px_1fr_minmax(360px,42%)]">
      <SessionSidebar />
      <Conversation />
      <DocumentPanel />
    </div>
  );
}
