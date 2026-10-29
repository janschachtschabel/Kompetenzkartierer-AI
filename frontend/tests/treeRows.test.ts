import { describe, expect, it } from "vitest";

import { rowsOf, type RowKey } from "@/documentTree";
import { ancestors, keptBy, matchesOf, visibleRows } from "@/treeRows";

import { CV, node_, statement_ } from "./treeFixtures";

// a: its statements s1, s2 (s2 confirmed) and its child a1 (with s3); b, with nothing under it
const ROWS = rowsOf([
  node_("a", {
    statements: [statement_("s1"), statement_("s2", { position: 2, review_status: CV + "rev_confirmed" })],
    children: [node_("a1", { statements: [statement_("s3")] })],
  }),
  node_("b", { position: 2, review_status: CV + "rev_rejected" }),
]);

function shown(expanded: RowKey[], kept: ReadonlySet<RowKey> | null = null): unknown[] {
  return visibleRows(ROWS, new Set(expanded), kept).map((row) => [
    row.row.key,
    row.level,
    row.expandable,
    row.expanded,
    row.posinset,
    row.setsize,
  ]);
}

describe("the rows a tree shows", () => {
  it("are its top nodes while none is open, those with rows under them openable", () => {
    expect(shown([])).toEqual([
      ["node:a", 1, true, false, 1, 2],
      ["node:b", 1, false, false, 2, 2],
    ]);
  });

  it("are an open node's statements and then its children, a level deeper", () => {
    expect(shown(["node:a", "node:a1"])).toEqual([
      ["node:a", 1, true, true, 1, 2],
      ["statement:s1", 2, false, false, 1, 3],
      ["statement:s2", 2, false, false, 2, 3],
      ["node:a1", 2, true, true, 3, 3],
      ["statement:s3", 3, false, false, 1, 1],
      ["node:b", 1, false, false, 2, 2],
    ]);
  });

  it("keep, filtered by review status, the rows of those statuses and the nodes above them", () => {
    const kept = keptBy(ROWS, new Set([CV + "rev_confirmed"]));

    expect([...kept].sort()).toEqual(["node:a", "statement:s2"]);
    expect(matchesOf(ROWS, new Set([CV + "rev_confirmed", CV + "rev_rejected"]))).toEqual(["statement:s2", "node:b"]);
    expect(shown(["node:a"], kept)).toEqual([
      ["node:a", 1, true, true, 1, 1],
      ["statement:s2", 2, false, false, 1, 1],
    ]);
  });

  it("open no node whose rows the filter all left out", () => {
    const rows = rowsOf([node_("c", { review_status: CV + "rev_confirmed", statements: [statement_("s4")] })]);
    const kept = keptBy(rows, new Set([CV + "rev_confirmed"]));

    expect(visibleRows(rows, new Set<RowKey>(["node:c"]), kept).map((row) => [row.row.key, row.expandable])).toEqual([
      ["node:c", false],
    ]);
  });

  it("name a row's ancestors from the top", () => {
    expect(ancestors(ROWS, "statement:s3")).toEqual(["node:a", "node:a1"]);
    expect(ancestors(ROWS, "node:b")).toEqual([]);
  });
});
