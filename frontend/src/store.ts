// Single Zustand store: sessions sidebar, the active session's timeline,
// the live drafting viz, and the document panel. All API effects live here so
// components stay presentational.

import { create } from "zustand";

import * as api from "@/lib/api";
import { replayJob } from "@/lib/replay";
import { applyVizEvent, EMPTY_VIZ, type Viz } from "@/lib/viz";
import type { Message, Outline, PipelineEvent, Section, SessionMeta } from "@/types";

interface Store {
  sessions: SessionMeta[];
  activeSessionId: string | null;
  sessionTitle: string;
  timeline: Message[];
  outlineDrafts: Record<string, Outline>; // job_id -> in-progress outline edits
  live: { jobId: string; viz: Viz; status: "running" | "done" | "failed" } | null;
  doc: { jobId: string; sections: Section[] } | null;
  busy: boolean;
  error: string | null;

  loadSessions: () => Promise<void>;
  newSession: () => Promise<void>;
  openSession: (id: string) => Promise<void>;
  sendPrompt: (text: string, files: File[]) => Promise<void>;
  editOutline: (jobId: string, outline: Outline) => void;
  approveAndRun: (jobId: string) => Promise<void>;
  loadFinishedJob: (jobId: string) => Promise<void>;
  applyEvent: (ev: PipelineEvent) => void;
}

const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export const useStore = create<Store>((set, get) => {
  const refreshTimeline = async (sessionId: string) => {
    const s = await api.getSession(sessionId);
    set({ timeline: s.messages, sessionTitle: s.title });
  };

  const guard = async (fn: () => Promise<void>) => {
    set({ busy: true, error: null });
    try {
      await fn();
    } catch (e) {
      set({ error: errMsg(e) });
    } finally {
      set({ busy: false });
    }
  };

  return {
    sessions: [],
    activeSessionId: localStorage.getItem("lexi_session_id"),
    sessionTitle: "",
    timeline: [],
    outlineDrafts: {},
    live: null,
    doc: null,
    busy: false,
    error: null,

    loadSessions: async () => {
      const { sessions } = await api.listSessions();
      set({ sessions });
      const active = get().activeSessionId;
      if (active && sessions.some((s) => s.session_id === active)) await get().openSession(active);
      else if (active) set({ activeSessionId: null });
    },

    newSession: () =>
      guard(async () => {
        const { session_id } = await api.createSession();
        localStorage.setItem("lexi_session_id", session_id);
        set({ activeSessionId: session_id, timeline: [], sessionTitle: "", doc: null, live: null });
        const { sessions } = await api.listSessions();
        set({ sessions });
      }),

    openSession: (id) =>
      guard(async () => {
        localStorage.setItem("lexi_session_id", id);
        set({ activeSessionId: id, doc: null, live: null });
        await refreshTimeline(id);
        // restore the document panel for the latest finished job in this session
        const ready = [...get().timeline].reverse().find((m) => m.type === "document_ready");
        if (ready) await get().loadFinishedJob(ready.data.job_id);
      }),

    sendPrompt: (text, files) =>
      guard(async () => {
        const sessionId = get().activeSessionId;
        if (!sessionId) return;
        if (files.length) {
          await api.uploadDocuments(files, sessionId);
          await refreshTimeline(sessionId);
        }
        if (text.trim()) {
          await api.createJob(text.trim(), sessionId);
          await refreshTimeline(sessionId);
          const { sessions } = await api.listSessions(); // title may have been set
          set({ sessions });
        }
      }),

    editOutline: (jobId, outline) =>
      set((s) => ({ outlineDrafts: { ...s.outlineDrafts, [jobId]: outline } })),

    approveAndRun: (jobId) =>
      guard(async () => {
        const sessionId = get().activeSessionId;
        const override = get().outlineDrafts[jobId] ?? null;
        await api.approveOutline(jobId, override);
        set({ live: { jobId, viz: EMPTY_VIZ, status: "running" }, doc: null });
        try {
          await api.runJob(jobId); // blocking in step 5; SSE replaces this in step 6
        } catch (e) {
          set((s) => ({ live: s.live && { ...s.live, status: "failed" }, error: errMsg(e) }));
          if (sessionId) await refreshTimeline(sessionId);
          return;
        }
        const { sections } = await api.getSections(jobId);
        await replayJob(sections, get().applyEvent, 4);
        set({ live: { jobId, viz: get().live?.viz ?? EMPTY_VIZ, status: "done" }, doc: { jobId, sections } });
        if (sessionId) await refreshTimeline(sessionId);
      }),

    loadFinishedJob: async (jobId) => {
      const { sections } = await api.getSections(jobId).catch(() => ({ sections: [] as Section[] }));
      if (sections.length) set({ doc: { jobId, sections } });
    },

    applyEvent: (ev) =>
      set((s) => (s.live ? { live: { ...s.live, viz: applyVizEvent(s.live.viz, ev) } } : {})),
  };
});
