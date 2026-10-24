// A job's state (backend app/api/jobs.py): what a page follows once it has started one.
import { apiFetch } from "./http";

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

/** What a job reports doing: a code the page words (jobProgress.ts), with its numbers. */
export interface JobProgressNote {
  code: string;
  params: Record<string, unknown>;
}

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  progress: JobProgressNote | null;
  /** Why it failed, as a code (backend app/jobs/outcome.py and the job's own). */
  error_code: string | null;
  cancel_requested: boolean;
  attempts: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export function getJob(id: string): Promise<Job> {
  return apiFetch<Job>(`/api/v1/jobs/${encodeURIComponent(id)}`);
}

/**
 * Cancels the job: a waiting one ends at once, a running one is asked to stop and does at its
 * worker's next heartbeat - every third of the lease, 20 s by default - and a few seconds after
 * at most where its work does not stop (backend app/jobs/worker.py); a worker gone ends it once
 * its lease runs out. 409 once it has ended.
 */
export function cancelJob(id: string): Promise<Job> {
  return apiFetch<Job>(`/api/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}
