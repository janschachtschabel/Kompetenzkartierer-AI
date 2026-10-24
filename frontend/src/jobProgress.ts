// How far a job has come: the progress codes the page has words for (jobs.progress),
// each with the numbers its words need. tests/jobProgressCodes.test.ts holds them to
// the codes the backend's jobs report.
import type { JobProgressNote } from "@/api";
import { t, type MessageParams } from "@/i18n/de";

export const JOB_PROGRESS: Readonly<Record<string, readonly string[]>> = {
  // source.check (backend app/sources/check_job.py)
  checking: ["done", "total"],
  // source.convert (backend app/conversion/job.py)
  converting: [],
  // extract.run (backend app/pipeline/progress.py, ProgressCode)
  extract_profile: [],
  extract_outline: ["headings"],
  extract_segments: ["units"],
  extract_frame: [],
  extract_statements: ["done", "total"],
};

/** The progress in the page's words; none for a code it has no words for, or numbers missing. */
export function progressText(progress: JobProgressNote | null | undefined): string {
  // its own codes only: "constructor" is every object's
  const needed = progress && Object.hasOwn(JOB_PROGRESS, progress.code) ? JOB_PROGRESS[progress.code] : undefined;
  if (!progress || !needed) return "";
  const params: MessageParams = {};
  for (const name of needed) {
    const value = progress.params[name];
    if (typeof value !== "number") return "";
    params[name] = value;
  }
  return t(`jobs.progress.${progress.code}`, params);
}
