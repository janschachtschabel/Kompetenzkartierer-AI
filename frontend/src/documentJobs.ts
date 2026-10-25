// A document's latest job by its kind (backend app/api/documents.py, extraction.kind): an extraction,
// or a repair (X6, then X5 again), which share the document's one job at a time.
import { REPAIR_KIND, type JobStatus } from "@/api";
import { t } from "@/i18n/de";

/** What the job is called where it is followed and cancelled. */
export function jobLabel(kind: string): string {
  return kind === REPAIR_KIND ? t("documents.page.repairLabel") : t("documents.page.jobLabel");
}

/** How the latest job of the document stands, by its kind. */
export function lastStatus(latest: { kind: string; status: JobStatus }): string {
  const status = t(`jobs.status.${latest.status}`);
  return latest.kind === REPAIR_KIND
    ? t("documents.page.lastRepairStatus", { status })
    : t("documents.page.lastStatus", { status });
}
