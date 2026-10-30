// Taking a row of a document's tree away (plan M1 9.8, Paket 9c2b L5, L6): a node with all under it and the
// findings on them, a statement deleted where it is an editor's own and rejected - kept, marked - where a run
// found it, as the server decides. Read at the revision the tree shows; one changed meanwhile is not taken but
// said, as a gone row, a closed tree and another failure are (rowRefusals.ts).
import { ApiError, dropNode, dropStatement, type Dropped, type TreeNode } from "@/api";
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { refusalOf } from "@/rowRefusals";

export type DropOutcome =
  | ({ outcome: "dropped" } & Dropped)
  | { outcome: "deleted" }
  | { outcome: "rejected" }
  | { outcome: "stale" }
  | { outcome: "gone" }
  | { outcome: "closed"; code: string }
  | { outcome: "failed"; problem: Notice };

/** What taking `node` away takes: it and those under it, and their statements - as the server counts them. */
export function dropCounts(node: TreeNode): Dropped {
  return node.children.map(dropCounts).reduce(
    (sum, under) => ({ nodes: sum.nodes + under.nodes, statements: sum.statements + under.statements }),
    { nodes: 1, statements: node.statements.length },
  );
}

export async function dropRow(row: Row): Promise<DropOutcome> {
  try {
    if (row.kind === "node") return { outcome: "dropped", ...(await dropNode(row.node.id, row.node.revision)) };
    const taken = await dropStatement(row.statement.id, row.statement.revision);
    return { outcome: taken.outcome };
  } catch (error) {
    if (error instanceof ApiError && error.code === "stale_revision") return { outcome: "stale" };
    // no fields: a field's problem cannot be one of taking a row away
    const refusal = refusalOf(error, [], t("documents.tree.drop.failed"));
    if (refusal.outcome === "gone" || refusal.outcome === "closed") return refusal;
    return { outcome: "failed", problem: refusal.problem ?? { text: t("documents.tree.drop.failed"), failed: true } };
  }
}

/** What the panel says of it; a failure is said where it was asked, a gone row as the panel says one. */
export function dropWords(done: Exclude<DropOutcome, { outcome: "failed" | "gone" }>): string {
  switch (done.outcome) {
    case "dropped":
      return t("documents.tree.drop.dropped", { nodes: done.nodes, statements: done.statements });
    case "closed":
      return refusalText(done.code) ?? t("documents.tree.drop.failed");
    default:
      return t(`documents.tree.drop.${done.outcome}`);
  }
}
