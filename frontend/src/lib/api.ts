// Thin typed fetch client. Session scoping is threaded through uploads/jobs.

import type { JobStatus, Outline, Section, SessionMeta, Message } from "@/types";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail).catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

const post = <T,>(url: string, body?: unknown) =>
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? null),
  }).then((r) => j<T>(r));

export const uploadDocuments = (files: File[], sessionId: string) => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  form.append("session_id", sessionId);
  return fetch("/documents", { method: "POST", body: form }).then((r) => j<{ ingested: unknown[] }>(r));
};

export const createJob = (prompt: string, sessionId: string) =>
  post<{ job_id: string; outline: Outline }>("/jobs", { prompt, session_id: sessionId });

export const approveOutline = (jobId: string, override: Outline | null = null) =>
  post<{ job_id: string; approved: boolean }>(`/jobs/${jobId}/outline/approve`, override);

export const runJob = (jobId: string) => post<{ job_id: string; status: string }>(`/jobs/${jobId}/run`);

export const resumeJob = (jobId: string) => post<{ job_id: string; status: string }>(`/jobs/${jobId}/resume`);

export const getJob = (jobId: string) => fetch(`/jobs/${jobId}`).then((r) => j<JobStatus>(r));

export const getSections = (jobId: string) =>
  fetch(`/jobs/${jobId}/sections`).then((r) => j<{ job_id: string; sections: Section[] }>(r));

export const listSessions = () =>
  fetch("/sessions").then((r) => j<{ sessions: SessionMeta[] }>(r));

export const createSession = () => post<{ session_id: string; title: string }>("/sessions");

export const getSession = (sessionId: string) =>
  fetch(`/sessions/${sessionId}`).then((r) =>
    j<{ session_id: string; title: string; messages: Message[] }>(r),
  );

export interface SessionDoc {
  mongo_doc_id: string;
  source_file: string;
  abstract: string;
  n_parents: number;
}

export const listSessionDocs = (sessionId: string) =>
  fetch(`/sessions/${sessionId}/documents`).then((r) => j<{ documents: SessionDoc[] }>(r));

export const deleteSessionDoc = (sessionId: string, docId: string) =>
  fetch(`/sessions/${sessionId}/documents/${docId}`, { method: "DELETE" }).then((r) =>
    j<{ deleted: string }>(r),
  );

export const reviseSection = (jobId: string, sectionId: string, instructions: string) =>
  post<{ job_id: string; section: Section }>(`/jobs/${jobId}/sections/${sectionId}/revise`, {
    instructions,
  });
