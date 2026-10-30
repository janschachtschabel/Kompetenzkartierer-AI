// Setting a row's review status (plan M1 9.8, Paket 9c2c M2, M3): the editors' alone, for the row chosen at the
// revision the tree shows - or the one a status just set left, until the tree is read again -, a node's or a
// statement's. Set, the revision it left is given. A row changed meanwhile is not set but said, the tree to be read
// again, as a row the document no longer holds; a tree closed meanwhile (a job, frozen, X4 not done) is said too,
// as a caller who is no editor; another failure is said where it was asked.
import { ApiError, setReview, type ReviewItem } from "@/api";
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { refusalText } from "@/refusals";
import { statusIri, statusOf, statusWord, type ReviewStatus } from "@/reviewStatus";

export type ReviewOutcome =
  | { outcome: "set"; status: ReviewStatus; revision: number }
  | { outcome: "stale" }
  /** The document holds the row no more. */
  | { outcome: "gone" }
  /** The tree closed to change: read it again. */
  | { outcome: "closed"; code: string }
  | { outcome: "refused"; code: string }
  | { outcome: "failed"; problem: Notice };

const CLOSING: ReadonlySet<string> = new Set(["job_open", "frozen", "not_extracted"]);

/** The status the row stands at; none for one the vocabulary does not hold. */
export function rowStatus(row: Row): ReviewStatus | null {
  return statusOf(row.kind === "node" ? row.node.review_status : row.statement.review_status);
}

function itemOf(row: Row, revision?: number): ReviewItem {
  return row.kind === "node"
    ? { kind: "node", id: row.node.id, revision: revision ?? row.node.revision }
    : { kind: "statement", id: row.statement.id, revision: revision ?? row.statement.revision };
}

// the row as stored none (backend app/api/review.py: `details.stale`, its `current` null)
function goneIn(details: Record<string, unknown>, id: string): boolean {
  const stale = details.stale;
  return (
    Array.isArray(stale) &&
    stale.some((one: unknown) => {
      const entry = one as { id?: unknown; current?: unknown } | null;
      return entry?.id === id && entry.current === null;
    })
  );
}

export async function reviewRow(
  documentId: string,
  row: Row,
  status: ReviewStatus,
  revision?: number,
): Promise<ReviewOutcome> {
  const item = itemOf(row, revision);
  try {
    const { revisions } = await setReview(documentId, status, [item]);
    return { outcome: "set", status, revision: revisions.find((one) => one.id === item.id)?.revision ?? item.revision };
  } catch (error) {
    if (error instanceof ApiError && error.code === "stale_revision") {
      return goneIn(error.details, item.id) ? { outcome: "gone" } : { outcome: "stale" };
    }
    const code = error instanceof ApiError ? error.code : undefined;
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
    case "gone":
      return t("documents.tree.gone");
    default:
      return refusalText(done.code) ?? t("documents.tree.review.failed");
  }
}
