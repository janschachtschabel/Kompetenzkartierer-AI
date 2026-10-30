import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";
import { reviewRow, reviewWords, rowStatus, type ReviewOutcome } from "@/rowReview";

import { CV, node_, statement_ } from "./treeFixtures";

const ROWS = rowsOf([
  node_("a", { revision: 2, statements: [statement_("s1", { revision: 5, review_status: CV + "rev_confirmed" })] }),
]);
const row = (key: "node:a" | "statement:s1") => ROWS.get(key) as Row;

// the words of an outcome the panel says; a failure is said at the control
function said(done: ReviewOutcome): string {
  if (done.outcome === "failed") throw new Error("a failure is not said by reviewWords");
  return reviewWords(done);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("a row's review status", () => {
  it("is read off the row, a node's or a statement's", () => {
    expect(rowStatus(row("node:a"))).toBe("proposed");
    expect(rowStatus(row("statement:s1"))).toBe("confirmed");
  });

  it("is set for the row alone, at the revision it was read at, and said", async () => {
    const sent = vi.spyOn(api, "setReview").mockResolvedValue({ revisions: [{ id: "s1", revision: 6 }] });

    const done = await reviewRow("d1", row("statement:s1"), "rejected");
    await reviewRow("d1", row("node:a"), "confirmed");

    expect(sent).toHaveBeenNthCalledWith(1, "d1", "rejected", [{ kind: "statement", id: "s1", revision: 5 }]);
    expect(sent).toHaveBeenNthCalledWith(2, "d1", "confirmed", [{ kind: "node", id: "a", revision: 2 }]);
    expect(done).toEqual({ outcome: "set", status: "rejected" });
    expect(said(done)).toBe("Prüfstand: Verworfen.");
  });

  it("says a row changed meanwhile, a tree closed, a caller who is no editor, or another failure", async () => {
    vi.spyOn(api, "setReview")
      .mockRejectedValueOnce(new ApiError("server", 409, "stale_revision", "Changed.", { stale: [] }))
      .mockRejectedValueOnce(new ApiError("server", 409, "job_open"))
      .mockRejectedValueOnce(new ApiError("forbidden", 403, "not_editor"))
      .mockRejectedValueOnce(new ApiError("network", 0));

    const stale = await reviewRow("d1", row("node:a"), "confirmed");
    const closed = await reviewRow("d1", row("node:a"), "confirmed");
    const refused = await reviewRow("d1", row("node:a"), "confirmed");
    const failed = await reviewRow("d1", row("node:a"), "confirmed");

    expect([stale, closed, refused]).toEqual([
      { outcome: "stale" },
      { outcome: "closed", code: "job_open" },
      { outcome: "refused", code: "not_editor" },
    ]);
    expect(said(stale)).toBe(t("documents.tree.review.stale"));
    expect(said(closed)).toBe(t("refusals.job_open"));
    expect(said(refused)).toBe(t("refusals.not_editor"));
    expect(failed).toMatchObject({ outcome: "failed", problem: { text: t("documents.tree.review.failed") } });
  });

  it.each(["job_open", "frozen", "not_extracted"])("says the tree closed by %s, to be read again", async (code) => {
    vi.spyOn(api, "setReview").mockRejectedValue(new ApiError("server", 409, code));

    const done = await reviewRow("d1", row("node:a"), "confirmed");

    expect(done).toEqual({ outcome: "closed", code });
    expect(said(done)).toBe(t(`refusals.${code}`));
  });

  it("says a row the document no longer holds is gone, not changed", async () => {
    const stale = (current: number | null, id = "a") =>
      new ApiError("server", 409, "stale_revision", "Changed.", { stale: [{ kind: "node", id, current }] });
    vi.spyOn(api, "setReview")
      .mockRejectedValueOnce(stale(null))
      .mockRejectedValueOnce(stale(3))
      .mockRejectedValueOnce(stale(null, "other"));

    const gone = await reviewRow("d1", row("node:a"), "confirmed");
    const changed = await reviewRow("d1", row("node:a"), "confirmed");
    const another = await reviewRow("d1", row("node:a"), "confirmed");

    expect([gone, changed, another]).toEqual([{ outcome: "gone" }, { outcome: "stale" }, { outcome: "stale" }]);
    expect(said(gone)).toBe(t("documents.tree.gone"));
  });
});
