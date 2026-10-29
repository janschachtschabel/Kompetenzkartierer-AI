import { describe, expect, it } from "vitest";

import { rowsOf, type RowKey } from "@/documentTree";
import { keyMove } from "@/treeKeys";
import { visibleRows } from "@/treeRows";

import { node_, statement_ } from "./treeFixtures";

// a (open): s1, then a1 (closed, with s2); b, a leaf
const ROWS = rowsOf([
  node_("a", { statements: [statement_("s1")], children: [node_("a1", { statements: [statement_("s2")] })] }),
  node_("b", { position: 2 }),
]);
const VISIBLE = visibleRows(ROWS, new Set<RowKey>(["node:a"]), null);

function move(from: RowKey, key: string): unknown {
  return keyMove(VISIBLE, from, key);
}

describe("the keys of a tree (WAI-ARIA tree view)", () => {
  it("move down and up through the rows it shows, and stay at either end", () => {
    expect(move("node:a", "ArrowDown")).toEqual({ focus: "statement:s1" });
    expect(move("statement:s1", "ArrowDown")).toEqual({ focus: "node:a1" });
    expect(move("node:a1", "ArrowUp")).toEqual({ focus: "statement:s1" });
    expect(move("node:b", "ArrowDown")).toBeNull();
    expect(move("node:a", "ArrowUp")).toBeNull();
  });

  it("open a closed node to the right, then go to its first row; a leaf stays", () => {
    expect(move("node:a1", "ArrowRight")).toEqual({ toggle: "node:a1", open: true });
    expect(move("node:a", "ArrowRight")).toEqual({ focus: "statement:s1" });
    expect(move("statement:s1", "ArrowRight")).toBeNull();
    expect(move("node:b", "ArrowRight")).toBeNull();
  });

  it("close an open node to the left, else go to the node above; at the top a closed one stays", () => {
    expect(move("node:a", "ArrowLeft")).toEqual({ toggle: "node:a", open: false });
    expect(move("statement:s1", "ArrowLeft")).toEqual({ focus: "node:a" });
    expect(move("node:a1", "ArrowLeft")).toEqual({ focus: "node:a" });
    expect(move("node:b", "ArrowLeft")).toBeNull();
  });

  it("go to the first and the last row, and choose a row with Enter or Space", () => {
    expect(move("node:a1", "Home")).toEqual({ focus: "node:a" });
    expect(move("node:a", "End")).toEqual({ focus: "node:b" });
    expect(move("node:a", "Home")).toBeNull();
    expect(move("node:b", "End")).toBeNull();
    expect(move("statement:s1", "Enter")).toEqual({ select: "statement:s1" });
    expect(move("statement:s1", " ")).toEqual({ select: "statement:s1" });
    expect(move("statement:s1", "a")).toBeNull();
  });
});
