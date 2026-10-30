// Checking a document's tree again (plan M1 9.8, Paket 9c2c M6): X5 once more, no model asked, by its owner or an
// editor. The job made - or the one of the document waiting or running, where the caller may follow it, of whatever
// kind (an extraction, a repair: they share the check's key) - is given with its kind;
// a refusal (X5 not done yet, frozen, another's job open, the content no longer the caller's) by its code; another
// failure as one.
import { ApiError, startDocumentCheck } from "@/api";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

export type CheckStart =
  | { outcome: "started"; jobId: string; kind: string }
  | { outcome: "refused"; code: string }
  | { outcome: "failed"; problem: Notice };

const REFUSED: ReadonlySet<string> = new Set(["not_checked", "frozen", "job_open", "file_hidden"]);

export async function startTreeCheck(documentId: string): Promise<CheckStart> {
  try {
    const job = await startDocumentCheck(documentId);
    return { outcome: "started", jobId: job.id, kind: job.kind };
  } catch (error) {
    const code = error instanceof ApiError ? error.code : undefined;
    if (code && REFUSED.has(code)) return { outcome: "refused", code };
    return { outcome: "failed", problem: failureNotice(error, t("documents.tree.check.failed")) };
  }
}
