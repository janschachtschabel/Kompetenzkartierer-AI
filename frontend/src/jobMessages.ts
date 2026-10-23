// Why a job failed, in German: the job names it by a code (its `error_code`),
// the page says it in its own words. tests/jobMessages.test.ts checks that
// every code listed is one a job ends with.
import { t } from "@/i18n/de";

export const JOB_FAILURE_CODES = [
  // source.fetch (backend app/sources/fetch_job.py)
  "url_not_allowed",
  "download_refused",
  "unsupported_type",
  "archive_too_large",
  "source_missing",
  "file_too_large",
  "too_many_redirects",
  "bad_answer",
  "download_throttled",
  // source.convert (backend app/conversion/job.py, FailureCode in app/db/conversions.py)
  "conversion_gone",
  "unreadable",
  "too_many_pages",
  "needs_ocr",
  "empty",
  "timed_out",
  "died",
  "not_pdf",
  "file_gone",
  // any job (app/jobs/outcome.py, app/jobs/queue.py)
  "handler_error",
  "result_not_storable",
  "lease_lost",
] as const;

type JobFailureCode = (typeof JOB_FAILURE_CODES)[number];

function isJobFailureCode(code: unknown): code is JobFailureCode {
  return (JOB_FAILURE_CODES as readonly unknown[]).includes(code);
}

/** The page's words for why a job failed; the general ones for a code it does not know. */
export function jobFailureText(code: string | null): string {
  return isJobFailureCode(code) ? t(`jobs.failures.${code}`) : t("jobs.failedUnknown");
}
