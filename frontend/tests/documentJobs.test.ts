import { describe, expect, it } from "vitest";

import { CHECK_KIND, REPAIR_KIND } from "@/api";
import { jobLabel, lastStatus } from "@/documentJobs";
import { t } from "@/i18n/de";

describe("a document's job in words", () => {
  it("is named by its kind: an extraction, a repair, a check", () => {
    expect(jobLabel("extract.document")).toBe(t("documents.page.jobLabel"));
    expect(jobLabel(REPAIR_KIND)).toBe(t("documents.page.repairLabel"));
    expect(jobLabel(CHECK_KIND)).toBe("Prüfung");
  });

  it("says how the latest stands, by its kind", () => {
    const done = t("jobs.status.done");

    expect(lastStatus({ kind: "extract.document", status: "done" })).toBe(t("documents.page.lastStatus", { status: done }));
    expect(lastStatus({ kind: REPAIR_KIND, status: "done" })).toBe(t("documents.page.lastRepairStatus", { status: done }));
    expect(lastStatus({ kind: CHECK_KIND, status: "done" })).toBe(`Letzte Prüfung: ${done}`);
  });
});
