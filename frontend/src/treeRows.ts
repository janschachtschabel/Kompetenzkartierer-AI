/**
 * The rows a document's tree shows (plan M1 9.7, Paket 9c J7): the top nodes, and under each open node its
 * statements and then its children, a level deeper - flat, in the order they show, each with its level and
 * place among its siblings (aria-level, aria-posinset, aria-setsize), so the tree is one list to the keys
 * (treeKeys.ts) and to the view. A filter by review status keeps the rows of those statuses and the nodes
 * above them.
 */
import type { Row, RowKey } from "@/documentTree";

export interface VisibleRow {
  row: Row;
  /** From 1 at the top. */
  level: number;
  /** A node with rows kept under it. */
  expandable: boolean;
  expanded: boolean;
  /** Its place among the siblings shown, from 1, and their number. */
  posinset: number;
  setsize: number;
}

/** The rows under each row (none for the top), in the tree's order. */
function childrenOf(rows: ReadonlyMap<RowKey, Row>): Map<RowKey | null, RowKey[]> {
  const under = new Map<RowKey | null, RowKey[]>();
  for (const row of rows.values()) {
    const siblings = under.get(row.parent);
    if (siblings) siblings.push(row.key);
    else under.set(row.parent, [row.key]);
  }
  return under;
}

/** What shows: every row whose nodes above are open, of those ``kept`` (none: all). */
export function visibleRows(
  rows: ReadonlyMap<RowKey, Row>,
  expanded: ReadonlySet<RowKey>,
  kept: ReadonlySet<RowKey> | null,
): VisibleRow[] {
  const under = childrenOf(rows);
  const keeps = (key: RowKey): boolean => kept === null || kept.has(key);
  const shown: VisibleRow[] = [];
  const visit = (parent: RowKey | null, level: number): void => {
    const siblings = (under.get(parent) ?? []).filter(keeps);
    siblings.forEach((key, index) => {
      const row = rows.get(key) as Row;
      const expandable = row.kind === "node" && (under.get(key) ?? []).some(keeps);
      const open = expandable && expanded.has(key);
      shown.push({ row, level, expandable, expanded: open, posinset: index + 1, setsize: siblings.length });
      if (open) visit(key, level + 1);
    });
  };
  visit(null, 1);
  return shown;
}

/** The nodes above a row, from the top. */
export function ancestors(rows: ReadonlyMap<RowKey, Row>, key: RowKey): RowKey[] {
  const above: RowKey[] = [];
  for (let parent = rows.get(key)?.parent ?? null; parent !== null; parent = rows.get(parent)?.parent ?? null) {
    above.unshift(parent);
  }
  return above;
}

/** The rows of the review statuses ``statuses`` (IRIs), in the tree's order. */
export function matchesOf(rows: ReadonlyMap<RowKey, Row>, statuses: ReadonlySet<string>): RowKey[] {
  return [...rows.values()]
    .filter((row) => statuses.has((row.kind === "node" ? row.node : row.statement).review_status))
    .map((row) => row.key);
}

/** The rows of the review statuses ``statuses`` (IRIs) and the nodes above them. */
export function keptBy(rows: ReadonlyMap<RowKey, Row>, statuses: ReadonlySet<string>): Set<RowKey> {
  const kept = new Set<RowKey>();
  for (const key of matchesOf(rows, statuses)) {
    kept.add(key);
    for (const above of ancestors(rows, key)) kept.add(above);
  }
  return kept;
}
