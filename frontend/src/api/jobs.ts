// A job's state (backend app/api/jobs.py): what a page follows once it has started one.
import { apiFetch } from "./http";

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  /** What the job reports doing: a code the page words, with its numbers. */
  progress: { code: string; params: Record<string, unknown> } | null;
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
