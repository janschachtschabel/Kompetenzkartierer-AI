/**
 * What a key does in a document's tree (plan M1 9.7, Paket 9c J7), after the WAI-ARIA tree view pattern: up
 * and down through the rows shown, right opens a closed node or goes to its first row, left closes an open
 * node or goes to the node above, Home and End to the first and the last row, Enter and Space choose the
 * row. None where the key does nothing there - the view then lets it be.
 */
import type { RowKey } from "@/documentTree";
import type { VisibleRow } from "@/treeRows";

export type TreeMove = { focus: RowKey } | { toggle: RowKey; open: boolean } | { select: RowKey } | null;

export function keyMove(visible: readonly VisibleRow[], current: RowKey, key: string): TreeMove {
  const at = visible.findIndex((shown) => shown.row.key === current);
  if (at < 0) return null;
  const here = visible[at];
  const focus = (index: number): TreeMove => {
    const there = visible[index];
    return there && index !== at ? { focus: there.row.key } : null;
  };
  switch (key) {
    case "ArrowDown":
      return focus(at + 1);
    case "ArrowUp":
      return focus(at - 1);
    case "Home":
      return focus(0);
    case "End":
      return focus(visible.length - 1);
    case "ArrowRight":
      if (here.expandable && !here.expanded) return { toggle: current, open: true };
      return here.expanded ? focus(at + 1) : null;
    case "ArrowLeft":
      if (here.expanded) return { toggle: current, open: false };
      return here.row.parent === null ? null : { focus: here.row.parent };
    case "Enter":
    case " ":
      return { select: current };
    default:
      return null;
  }
}
