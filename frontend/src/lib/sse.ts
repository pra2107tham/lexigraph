// §7 SSE reader: GET /jobs/{id}/run/stream via EventSource, one JSON event per
// frame. Returns a close function; the browser auto-reconnects and the server
// replays a Mongo-derived job_snapshot on each connect.

import type { PipelineEvent } from "@/types";

export function streamRun(jobId: string, onEvent: (ev: PipelineEvent) => void): () => void {
  const es = new EventSource(`/jobs/${jobId}/run/stream`);
  es.onmessage = (msg) => {
    const ev = JSON.parse(msg.data) as PipelineEvent;
    onEvent(ev);
    if (ev.type === "job_done" || ev.type === "error") es.close();
  };
  es.onerror = () => {
    // EventSource retries on transient drops; a closed stream after a terminal
    // event lands here too, which is fine — onEvent already saw the terminal.
  };
  return () => es.close();
}
