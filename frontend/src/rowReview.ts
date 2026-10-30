// Setting a row's review status (plan M1 9.8, Paket 9c2c M2, M3): the editors' alone, for the row chosen at the
// revision the tree shows - a node's or a statement's. A row changed meanwhile is not set but said, the tree to
// be read again; a tree closed meanwhile (a job, frozen, X4 not done) is said too, as a caller who is no editor;
// another failure is said where it was asked.
import { ApiError, setReview, type ReviewItem } from "@/api";
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { statusIri, statusOf, statusWord, type ReviewStatus } from "@/reviewStatus";

export type ReviewOutcome =
  | { outcome: "set"; status: ReviewStatus }
  | { outcome: "stale" }
  /** The tree closed to change: read it again. */
  | { outcome: "closed"; code: string }
  | { outcome: "refused"; code: string }
  | { outcome: "failed"; problem: Notice };

const CLOSING: ReadonlySet<string> = new Set(["job_open", "frozen", "not_extracted"]);

/** The status the row stands at; none for one the vocabulary does not hold. */
export function rowStatus(row: Row): ReviewStatus | null {
  return statusOf(row.kind === "node" ? row.node.review_status : row.statement.review_status);
}

function itemOf(row: Row): ReviewItem {
  return row.kind === "node"
    ? { kind: "node", id: row.node.id, revision: row.node.revision }
    : { kind: "statement", id: row.statement.id, revision: row.statement.revision };
}

export async function reviewRow(documentId: string, row: Row, status: ReviewStatus): Promise<ReviewOutcome> {
  try {
    await setReview(documentId, status, [itemOf(row)]);
    return { outcome: "set", status };
  } catch (error) {
    const code = error instanceof ApiError ? error.code : undefined;
    if (code === "stale_revision") return { outcome: "stale" };
    if (code && CLOSING.has(code)) return { outcome: "closed", code };
    if (code === "not_editor") return { outcome: "refused", code };
    return { outcome: "failed", problem: failureNotice(error, t("documents.tree.review.failed")) };
  }
}

/** What the panel says of it; a failure is said where it was asked. */
export function reviewWords(done: Exclude<ReviewOutcome, { outcome: "failed" }>): string {
  switch (done.outcome) {
    case "set":
      return t("documents.tree.review.set", { status: statusWord(statusIri(done.status)) });
    case "stale":
      return t("documents.tree.review.stale");
    default:
      return refusalText(done.code) ?? t("documents.tree.review.failed");
  }
}
