// A document frozen and copied (plan M1 9.10, Paket 9d1 N6, N7; backend app/api/freeze.py): frozen, it is given
// back with its IRI; its violations are taken only when asked about first, by their count; what is missing for its
// IRI is named; a check owed is said so the tree can be checked; a document closed meanwhile (frozen, a job) is to
// be read again. Copied, the draft is given back; a draft open already is named where the server names it.
import { ApiError, copyDocument, freezeDocument, type CurriculumDocument } from "@/api";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

export type FreezeOutcome =
  | { outcome: "frozen"; document: CurriculumDocument }
  | { outcome: "violations"; count: number }
  | { outcome: "incomplete"; missing: string[] }
  | { outcome: "owed" }
  /** The document closed meanwhile: read it again. */
  | { outcome: "closed"; code: string }
  | { outcome: "refused"; code: string }
  | { outcome: "failed"; problem: Notice };

export type CopyOutcome =
  | { outcome: "copied"; document: CurriculumDocument }
  /** A draft of it is open already, named where the server could. */
  | { outcome: "open"; documentId: string | null }
  /** Not frozen (any more): read it again. */
  | { outcome: "stale" }
  | { outcome: "refused"; code: string }
  | { outcome: "failed"; problem: Notice };

const CLOSING: ReadonlySet<string> = new Set(["frozen", "job_open"]);
const FREEZE_REFUSED: ReadonlySet<string> = new Set([
  "not_extracted",
  "no_iri_base",
  "iri_taken",
  "not_editor",
  "has_violations",
]);
const COPY_REFUSED: ReadonlySet<string> = new Set(["not_latest", "vocabulary_changed", "not_editor"]);

// each by its own key: the catalogue's guard reads the keys the code asks for
const MISSING: Readonly<Record<string, () => string>> = {
  work: () => t("documents.page.freeze.missing.work"),
  region: () => t("documents.page.freeze.missing.region"),
  short_title: () => t("documents.page.freeze.missing.short_title"),
  issuer: () => t("documents.page.freeze.missing.issuer"),
  edition: () => t("documents.page.freeze.missing.edition"),
};

/** What the server says is missing for the document's IRI, item by item; an item it may add later left out. */
export function missingWords(missing: readonly string[]): string[] {
  return missing.flatMap((item) => (Object.hasOwn(MISSING, item) ? [MISSING[item]()] : []));
}

export async function freeze(documentId: string, acceptViolations: boolean): Promise<FreezeOutcome> {
  try {
    return { outcome: "frozen", document: await freezeDocument(documentId, acceptViolations) };
  } catch (error) {
    if (!(error instanceof ApiError) || !error.code) {
      return { outcome: "failed", problem: failureNotice(error, t("documents.page.freeze.failed")) };
    }
    const { code, details } = error;
    if (code === "has_violations" && typeof details.violations === "number") {
      return { outcome: "violations", count: details.violations };
    }
    if (code === "incomplete") {
      const missing = Array.isArray(details.missing) ? details.missing : [];
      return { outcome: "incomplete", missing: missing.filter((item): item is string => typeof item === "string") };
    }
    if (code === "check_owed") return { outcome: "owed" };
    if (CLOSING.has(code)) return { outcome: "closed", code };
    if (FREEZE_REFUSED.has(code)) return { outcome: "refused", code };
    return { outcome: "failed", problem: failureNotice(error, t("documents.page.freeze.failed")) };
  }
}

export async function copy(documentId: string): Promise<CopyOutcome> {
  try {
    return { outcome: "copied", document: await copyDocument(documentId) };
  } catch (error) {
    const code = error instanceof ApiError ? error.code : undefined;
    if (code === "draft_open") {
      const open = (error as ApiError).details.document_id;
      return { outcome: "open", documentId: typeof open === "string" ? open : null };
    }
    if (code === "not_frozen") return { outcome: "stale" };
    if (code && COPY_REFUSED.has(code)) return { outcome: "refused", code };
    return { outcome: "failed", problem: failureNotice(error, t("documents.page.revision.copyFailed")) };
  }
}
