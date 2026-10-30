// A document's latest job by its kind (backend app/api/documents.py, extraction.kind): an extraction, a
// repair (X6, then X5 again) or a check (X5 again), which share the document's one job at a time.
import { CHECK_KIND, REPAIR_KIND, type JobStatus } from "@/api";
import { t } from "@/i18n/de";

/** What the job is called where it is followed and cancelled. */
export function jobLabel(kind: string): string {
  if (kind === REPAIR_KIND) return t("documents.page.repairLabel");
  return kind === CHECK_KIND ? t("documents.page.checkLabel") : t("documents.page.jobLabel");
}

/** How the latest job of the document stands, by its kind. */
export function lastStatus(latest: { kind: string; status: JobStatus }): string {
  const status = t(`jobs.status.${latest.status}`);
  if (latest.kind === REPAIR_KIND) return t("documents.page.lastRepairStatus", { status });
  return latest.kind === CHECK_KIND
    ? t("documents.page.lastCheckStatus", { status })
    : t("documents.page.lastStatus", { status });
}
