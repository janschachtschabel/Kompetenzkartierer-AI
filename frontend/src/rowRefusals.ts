// What a refused change to a document's tree means to the editor (plan M1 9.8, Paket 9c2 K5-K7, L6): the row
// gone, the tree closed, a field's problem - at the field where the form holds it, above the form where not -,
// or another failure. Saving, adding and taking away say each the same way; a stale revision is the caller's,
// as each meets it differently.
import type { Ref } from "vue";

import { ApiError, type EditFields, type FormField } from "@/api";
import { ANCHORS } from "@/anchorDraft";
import { messages, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { sameValue } from "@/rowDraft";

/** The refusals that close the tree to change - whoever asks, or the reader whose content it no longer is. */
const CLOSING: ReadonlySet<string> = new Set(["job_open", "frozen", "not_extracted", "no_form", "file_hidden"]);
const GONE: ReadonlySet<string> = new Set(["no_node", "no_statement"]);

export type Refusal =
  | { outcome: "gone" }
  | { outcome: "closed"; code: string }
  /** By a field's key, the words of its problem; or the problem of a field the form does not hold. */
  | { outcome: "invalid"; errors: Record<string, string>; problem: Notice | null }
  | { outcome: "failed"; problem: Notice };

function problemText(problem: unknown): string {
  const words: Record<string, string> = messages.documents.tree.problems;
  return typeof problem === "string" && Object.hasOwn(words, problem) ? words[problem] : t("documents.tree.problems.other");
}

/** What `error` means for a change of the form's `fields`; `failed` heads a failure the user may try again. */
export function refusalOf(error: unknown, fields: readonly FormField[], failed: string): Refusal {
  const code = error instanceof ApiError ? error.code : undefined;
  const details = error instanceof ApiError ? error.details : {};
  if (code && GONE.has(code)) return { outcome: "gone" };
  if (code && CLOSING.has(code)) return { outcome: "closed", code };
  // a statement without an anchor: a problem of its anchors' list
  if (code === "anchor_missing") return invalidAt(fields, ANCHORS, t("refusals.anchor_missing"), failed);
  if (code === "invalid_field") return invalidAt(fields, details.field, problemText(details.problem), failed);
  return { outcome: "failed", problem: failureNotice(error, failed) };
}

function invalidAt(fields: readonly FormField[], field: unknown, words: string, failed: string): Refusal {
  if (typeof field === "string" && fields.some((one) => one.key === field)) {
    return { outcome: "invalid", errors: { [field]: words }, problem: null };
  }
  const notice = { text: failed, explanation: t("documents.tree.problems.elsewhere"), failed: true };
  return { outcome: "invalid", errors: {}, problem: notice };
}

/** Where a refusal's words go: why the tree closed, the fields' problems, a problem above the form. */
export interface RefusalState {
  closed: Ref<string | null>;
  errors: Ref<Record<string, string>>;
  problem: Ref<Notice | null>;
}

/** Lay `refusal` on `state`; what it said. */
export function applyRefusal(refusal: Refusal, state: RefusalState): Refusal["outcome"] {
  if (refusal.outcome === "closed") state.closed.value = refusal.code;
  if (refusal.outcome === "invalid") {
    state.errors.value = refusal.errors;
    state.problem.value = refusal.problem;
  }
  if (refusal.outcome === "failed") state.problem.value = refusal.problem;
  return refusal.outcome;
}

/** The required fields the change empties, each said at its field - before anything is asked. */
export function emptiedRequired(fields: readonly FormField[], changed: EditFields): Record<string, string> {
  const words = fields
    .filter((field) => field.required && field.key in changed && sameValue(changed[field.key], null))
    .map((field) => [field.key, t(field.key === ANCHORS ? "refusals.anchor_missing" : "documents.tree.problems.required")]);
  return Object.fromEntries(words);
}
