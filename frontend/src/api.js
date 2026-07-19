// Thin API client for the current (v1) backend. No session scoping yet (v2).

async function j(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export async function uploadDocuments(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  return j(await fetch("/documents", { method: "POST", body: form }));
}

export async function createJob(prompt) {
  return j(
    await fetch("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    })
  );
}

export async function approveOutline(jobId, override = null) {
  // override: full Outline object to replace the AI's, or null to approve as-is.
  return j(
    await fetch(`/jobs/${jobId}/outline/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: override ? JSON.stringify(override) : "null",
    })
  );
}

export async function runJob(jobId) {
  // Blocking in v1 — resolves when the whole document is drafted.
  return j(await fetch(`/jobs/${jobId}/run`, { method: "POST" }));
}

export async function getSections(jobId) {
  return j(await fetch(`/jobs/${jobId}/sections`));
}

export async function getDocument(jobId) {
  return j(await fetch(`/jobs/${jobId}/document`));
}
