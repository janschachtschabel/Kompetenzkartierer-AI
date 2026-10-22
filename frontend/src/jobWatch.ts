// Following a job until it ends: asked again after 1, 2, 4 and then every 8
// seconds. A page that starts a job and stays open asks a few times in the
// first seconds, when most fetches end, and rarely after; at a steady second a
// dozen open pages were a dozen requests a second for as long as they stayed
// open (the old app's JobProgress, which only backed off on failures).
import { ApiError, getJob, type Job, type JobStatus } from "@/api";

const FIRST_DELAY_MS = 1000;
const MAX_DELAY_MS = 8000;
const ENDED: ReadonlySet<JobStatus> = new Set(["done", "failed", "cancelled"]);

/** Whether a job in `status` is over: nothing it does changes any more. */
export function hasEnded(status: JobStatus): boolean {
  return ENDED.has(status);
}

/** Why there is nothing left to ask: no session, an account that may not, a job the server does not have. */
export type JobGone = "unauthorized" | "forbidden" | "not_found";

export interface JobWatchHandlers {
  /** Each answer, the last one with the job ended. */
  onState: (job: Job) => void;
  /** Asking stopped for good, without an answer. */
  onGone: (why: JobGone) => void;
  /** An answer did not come; the next question follows on schedule. */
  onTrouble?: (error: unknown) => void;
}

export interface JobWatch {
  stop: () => void;
}

function goneReason(error: unknown): JobGone | null {
  if (!(error instanceof ApiError)) return null;
  if (error.kind === "unauthorized") return "unauthorized";
  if (error.kind === "forbidden") return "forbidden";
  return error.status === 404 ? "not_found" : null;
}

/** Asks for job `id` until it ends, is gone or `stop()` is called. */
export function watchJob(id: string, handlers: JobWatchHandlers): JobWatch {
  let delay = FIRST_DELAY_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;

  function schedule(): void {
    timer = setTimeout(() => void ask(), delay);
    delay = Math.min(delay * 2, MAX_DELAY_MS);
  }

  async function ask(): Promise<void> {
    try {
      const job = await getJob(id);
      if (stopped) return; // let go of while the answer was on its way
      handlers.onState(job);
      if (hasEnded(job.status)) return;
    } catch (error) {
      if (stopped) return;
      const gone = goneReason(error);
      if (gone) return handlers.onGone(gone);
      handlers.onTrouble?.(error);
    }
    if (!stopped) schedule(); // a handler may have let go of it
  }

  schedule();
  return {
    stop() {
      stopped = true;
      clearTimeout(timer);
    },
  };
}
