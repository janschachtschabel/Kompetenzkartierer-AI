// A document's title, issuer and edition and its work (plan M1 9.10, Paket 9d1 N5; backend app/api/document_meta.py):
// only the fields changed are sent, an emptied one as none; a work is one there is - the works of the documents the
// caller sees, there being no list of works - or a new one, its short title checked before it is sent. A field's
// problem goes to its field; a document closed to the change (frozen, or its IRI holding the issuer and the edition)
// is to be read again; another refusal is said by its code.
import {
  ApiError,
  editDocument,
  setWork,
  type CurriculumDocument,
  type DocumentWork,
  type MetaFields,
  type NewWork,
} from "@/api";
import { messages, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { word } from "@/registerWords";
import { problemText } from "@/rowRefusals";

/** The three fields as the form holds them, a text each. */
export interface MetaDraft {
  title: string;
  issuer: string;
  edition: string;
}

export type MetaOutcome =
  | { outcome: "saved"; document: CurriculumDocument }
  | { outcome: "invalid"; field: string; problem: string }
  /** Closed to the change meanwhile: read the document again. */
  | { outcome: "closed"; code: string }
  | { outcome: "refused"; code: string }
  | { outcome: "failed"; problem: Notice };

const CLOSING: ReadonlySet<string> = new Set(["frozen", "named"]);
const REFUSED: ReadonlySet<string> = new Set(["job_open", "not_extracted", "not_editor", "no_work"]);
const SHORT_TITLE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/**
 * The fields the draft changes, both sides trimmed - the server stores a text as sent, so a stored value may end on
 * a space -; one emptied as null. With an IRI the issuer and the edition stand as they are: never a change.
 */
export function metaChanges(document: CurriculumDocument, draft: MetaDraft): MetaFields {
  const changes: MetaFields = {};
  const keys = document.iri === null ? (["title", "issuer", "edition"] as const) : (["title"] as const);
  for (const key of keys) {
    const value = draft[key].trim() || null;
    if (value !== (document[key]?.trim() || null)) changes[key] = value;
  }
  return changes;
}

/** As the backend takes a work's short title, the last part of its IRI. */
export function shortTitleOk(text: string): boolean {
  return text.length <= 200 && SHORT_TITLE.test(text);
}

/** A work in words: its title, then its land and short title where it has them. */
export function workWords(work: DocumentWork): string {
  const land = work.region ? word(messages.sources.countries, work.region) : "";
  const facts = [land, work.short_title].filter(Boolean).join(", ");
  return facts ? `${work.title} (${facts})` : work.title;
}

/** The works of `documents`, each once, by title. */
export function knownWorks(documents: readonly CurriculumDocument[]): DocumentWork[] {
  const byId = new Map<string, DocumentWork>();
  for (const document of documents) if (document.work) byId.set(document.work.id, document.work);
  return [...byId.values()].sort((one, other) => one.title.localeCompare(other.title, "de"));
}

function refused(error: unknown, failed: string): MetaOutcome {
  const code = error instanceof ApiError ? error.code : undefined;
  if (code === "invalid_field") {
    const { field, problem } = (error as ApiError).details;
    if (typeof field === "string") return { outcome: "invalid", field, problem: problemText(problem) };
  }
  if (code && CLOSING.has(code)) return { outcome: "closed", code };
  if (code && REFUSED.has(code)) return { outcome: "refused", code };
  return { outcome: "failed", problem: failureNotice(error, failed) };
}

export async function saveMeta(documentId: string, fields: MetaFields): Promise<MetaOutcome> {
  try {
    return { outcome: "saved", document: await editDocument(documentId, fields) };
  } catch (error) {
    return refused(error, t("documents.page.edition.saveFailed"));
  }
}

export async function saveWork(documentId: string, work: NewWork | { work_id: string }): Promise<MetaOutcome> {
  try {
    return { outcome: "saved", document: await setWork(documentId, work) };
  } catch (error) {
    return refused(error, t("documents.page.edition.workFailed"));
  }
}
