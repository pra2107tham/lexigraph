// Typed contracts mirroring the backend Pydantic models + the §7 SSE event
// table. These shapes are frozen: the same events the live stream emits are
// synthesized by the replay driver, so the reducer never cares about source.

export interface Citation {
  parent_id: string;
  quote: string;
  source_file: string;
  verified: "quote_verified" | "entailed" | "unverified" | null;
}

export interface Section {
  section_id: string;
  title: string;
  instructions: string;
  text: string;
  citations: Citation[];
  needs_review: boolean;
}

export interface OutlineSection {
  section_id: string;
  title: string;
  instructions: string;
  source_files?: string[];
}

export interface Outline {
  job_id: string;
  sections: OutlineSection[];
  approved: boolean;
}

export interface SessionMeta {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface JobStatus {
  job_id: string;
  status: "outline_pending" | "approved" | "running" | "done" | "failed";
  error?: { where: string; message: string } | null;
  audit?: Record<string, unknown> | null;
  session_id?: string | null;
}

// ---- session timeline (§2 message types) ----------------------------------

export type Message = { id: string; ts: string } & (
  | { type: "user_prompt"; data: { text: string; job_id: string } }
  | { type: "ingest_receipt"; data: { source_file: string; mongo_doc_id: string; n_parents: number } }
  | { type: "outline_card"; data: { job_id: string; outline: Outline } }
  | { type: "drafting_live"; data: { job_id: string } }
  | { type: "document_ready"; data: { job_id: string; n_sections: number; n_citations: number; n_flagged: number } }
  | { type: "revision"; data: { job_id: string; section_id: string; instructions: string } }
);

// ---- §7 pipeline event contract -------------------------------------------

export interface PipelineEvent {
  type:
    | "job_start"
    | "job_snapshot"
    | "section_start"
    | "retrieve_query"
    | "candidates"
    | "deduped"
    | "reranked"
    | "draft_start"
    | "draft_done"
    | "evaluate"
    | "redraft"
    | "section_committed"
    | "job_done"
    | "error";
  section_id?: string;
  section_index?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: Record<string, any>;
}
