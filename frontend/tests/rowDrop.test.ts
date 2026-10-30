import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import { rowsOf, type Row } from "@/documentTree";
import { t } from "@/i18n/de";
import { dropCounts, dropRow, dropWords, type DropOutcome } from "@/rowDrop";

import { node_, statement_ } from "./treeFixtures";

const TREE = node_("a", {
  revision: 4,
  statements: [statement_("s1", { revision: 7 }), statement_("s2", { position: 2 })],
  children: [
    node_("b", { statements: [statement_("s3")], children: [node_("c")] }),
    node_("d", { position: 2 }),
  ],
});
const ROWS = rowsOf([TREE]);
const row = (key: "node:a" | "node:c" | "statement:s1") => ROWS.get(key) as Row;

// the words of an outcome the panel says itself; a failure or a gone row is said elsewhere
function said(done: DropOutcome): string {
  if (done.outcome === "failed" || done.outcome === "gone") throw new Error(`not said by dropWords: ${done.outcome}`);
  return dropWords(done);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("taking a row away", () => {
  it("counts a node with all under it, and their statements", () => {
    expect(dropCounts(TREE)).toEqual({ nodes: 4, statements: 3 });
    expect(dropCounts(node_("c"))).toEqual({ nodes: 1, statements: 0 });
  });

  it("takes a node away at its revision, and says what went with it", async () => {
    const sent = vi.spyOn(api, "dropNode").mockResolvedValue({ nodes: 4, statements: 3 });

    const done = await dropRow(row("node:a"));

    expect(sent).toHaveBeenCalledWith("a", 4);
    expect(done).toEqual({ outcome: "dropped", nodes: 4, statements: 3 });
    expect(said(done)).toBe("Gelöscht: der Knoten mit 3 Unterknoten und 3 Aussagen.");
    expect(dropWords({ outcome: "dropped", nodes: 1, statements: 1 })).toBe("Gelöscht: der Knoten mit 0 Unterknoten und 1 Aussage.");
  });

  it("deletes an editor's own statement and rejects a run's, as the server decides", async () => {
    const sent = vi
      .spyOn(api, "dropStatement")
      .mockResolvedValueOnce({ outcome: "deleted", revision: null })
      .mockResolvedValueOnce({ outcome: "rejected", revision: 8 });

    const deleted = await dropRow(row("statement:s1"));
    const rejected = await dropRow(row("statement:s1"));

    expect(sent).toHaveBeenCalledWith("s1", 7);
    expect([deleted, rejected]).toEqual([{ outcome: "deleted" }, { outcome: "rejected" }]);
    expect(said(deleted)).toBe(t("documents.tree.drop.deleted"));
    expect(said(rejected)).toBe(t("documents.tree.drop.rejected"));
  });

  it("says a row changed meanwhile, gone, a closed tree, or another failure", async () => {
    vi.spyOn(api, "dropNode")
      .mockRejectedValueOnce(new ApiError("server", 409, "stale_revision", "Changed.", { current: node_("c", { revision: 2 }) }))
      .mockRejectedValueOnce(new ApiError("server", 404, "no_node"))
      .mockRejectedValueOnce(new ApiError("server", 409, "frozen"))
      .mockRejectedValueOnce(new ApiError("network", 0));

    const stale = await dropRow(row("node:c"));
    const gone = await dropRow(row("node:c"));
    const closed = await dropRow(row("node:c"));
    const failed = await dropRow(row("node:c"));

    expect([stale, gone, closed]).toEqual([{ outcome: "stale" }, { outcome: "gone" }, { outcome: "closed", code: "frozen" }]);
    expect(said(stale)).toBe(t("documents.tree.drop.stale"));
    expect(said(closed)).toBe(t("refusals.frozen"));
    expect(failed).toMatchObject({ outcome: "failed", problem: { text: t("documents.tree.drop.failed") } });
  });

  it("takes a row changed meanwhile into none at all as gone", async () => {
    vi.spyOn(api, "dropNode").mockRejectedValue(
      new ApiError("server", 409, "stale_revision", "Changed.", { current: null }),
    );

    expect(await dropRow(row("node:c"))).toEqual({ outcome: "gone" });
  });
});
