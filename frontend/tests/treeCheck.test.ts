import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, CHECK_KIND, type Job } from "@/api";
import { t } from "@/i18n/de";
import { startTreeCheck } from "@/treeCheck";

function job(id: string): Job {
  return {
    id,
    kind: CHECK_KIND,
    status: "queued",
    progress: null,
    error_code: null,
    cancel_requested: false,
    attempts: 0,
    max_attempts: 3,
    created_at: "2026-10-30T10:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("checking a document's tree again", () => {
  it("starts the check, or meets the one waiting, and gives its job", async () => {
    const sent = vi.spyOn(api, "startDocumentCheck").mockResolvedValue(job("j1"));

    expect(await startTreeCheck("d1")).toEqual({ outcome: "started", jobId: "j1" });
    expect(sent).toHaveBeenCalledWith("d1");
  });

  it.each(["not_checked", "frozen", "job_open", "file_hidden"])("is refused for %s, the code given", async (code) => {
    vi.spyOn(api, "startDocumentCheck").mockRejectedValue(new ApiError("server", 409, code));

    expect(await startTreeCheck("d1")).toEqual({ outcome: "refused", code });
  });

  it("says another failure as one", async () => {
    vi.spyOn(api, "startDocumentCheck").mockRejectedValue(new ApiError("network", 0));

    expect(await startTreeCheck("d1")).toMatchObject({ outcome: "failed", problem: { text: t("documents.tree.check.failed") } });
  });
});
