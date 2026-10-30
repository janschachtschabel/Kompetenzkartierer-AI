// Saving a change to a row of a document's tree (plan M1 9.8, Paket 9c2 K4-K7). A change names only the fields
// changed (rowDraft.changedFields) and the revision its form was filled from; the answer is the row as stored.
// Where another stored a change meanwhile (409 stale_revision, details.current), what only the other changed
// is taken in and what both changed is put before the user (rowConflict.rebase), the change then laid on the
// stored row. Where the tree closed meanwhile (a job, frozen, X4 not done, no form) the reason is kept with the
// draft. A field's problem stands at the field; any other failure above the form, the draft kept to try again.
import { computed, ref, shallowRef, watch, type Ref } from "vue";

import { ApiError, editNode, editStatement, type FieldValue, type Form, type FormField } from "@/api";
import type { Row } from "@/documentTree";
import { messages, t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";
import { rebase, type Clash } from "@/rowConflict";
import { changedFields, draftOf, type Draft } from "@/rowDraft";

/** How a save went: the editor says each in its own way. */
export type SaveOutcome = "saved" | "unchanged" | "conflict" | "invalid" | "closed" | "gone" | "failed";

/** The refusals that close the tree to change, whoever asks. */
const CLOSING: ReadonlySet<string> = new Set(["job_open", "frozen", "not_extracted", "no_form"]);
const GONE: ReadonlySet<string> = new Set(["no_node", "no_statement"]);

export interface RowConflict {
  clashes: Clash[];
  taken: string[];
  stored: Draft;
}

function fieldsOf(row: Row): Record<string, FieldValue> {
  return row.kind === "node" ? row.node.fields : row.statement.fields;
}

function revisionOf(row: Row): number {
  return row.kind === "node" ? row.node.revision : row.statement.revision;
}

function problemText(problem: unknown): string {
  const words: Record<string, string> = messages.documents.tree.problems;
  return typeof problem === "string" && Object.hasOwn(words, problem) ? words[problem] : t("documents.tree.problems.other");
}

export function useRowSave(row: Ref<Row>, form: Ref<Form>) {
  const fields = computed<FormField[]>(() => (row.value.kind === "node" ? form.value.node : form.value.statement));
  const before = shallowRef<Draft>(draftOf(fields.value, fieldsOf(row.value)));
  const draft = shallowRef<Draft>({ ...before.value });
  const revision = ref(revisionOf(row.value));
  const saving = ref(false);
  const errors = ref<Record<string, string>>({});
  const problem = shallowRef<Notice | null>(null);
  const conflict = shallowRef<RowConflict | null>(null);
  const closed = ref<string | null>(null);
  const dirty = computed(() => Object.keys(changedFields(fields.value, before.value, draft.value)).length > 0);

  function stand(values: Record<string, FieldValue>, at: number): void {
    before.value = draftOf(fields.value, values);
    draft.value = { ...before.value };
    revision.value = at;
  }

  // Another row begins anew; the same row read again is taken unless the user changed it
  watch(row, (now, was) => {
    if (now.key !== was.key) {
      errors.value = {};
      problem.value = null;
      conflict.value = null;
      closed.value = null;
      stand(fieldsOf(now), revisionOf(now));
    } else if (!dirty.value) stand(fieldsOf(now), revisionOf(now));
  });

  function refused(error: unknown): SaveOutcome {
    const code = error instanceof ApiError ? error.code : undefined;
    const details = error instanceof ApiError ? error.details : {};
    if (code === "stale_revision") {
      const current = details.current as { fields?: Record<string, FieldValue>; revision?: number } | null;
      if (!current?.fields || typeof current.revision !== "number") return "gone";
      const stored = draftOf(fields.value, current.fields);
      const laid = rebase(fields.value, before.value, draft.value, stored);
      before.value = stored;
      draft.value = laid.draft;
      revision.value = current.revision;
      conflict.value = { clashes: laid.clashes, taken: laid.taken, stored };
      return "conflict";
    }
    if (code && GONE.has(code)) return "gone";
    if (code && CLOSING.has(code)) {
      closed.value = code;
      return "closed";
    }
    if (code === "invalid_field") {
      const field = details.field;
      if (typeof field === "string" && fields.value.some((one) => one.key === field)) {
        errors.value = { [field]: problemText(details.problem) };
      } else {
        problem.value = { text: t("documents.tree.form.saveFailed"), explanation: t("documents.tree.problems.elsewhere"), failed: true };
      }
      return "invalid";
    }
    problem.value = failureNotice(error, t("documents.tree.form.saveFailed"));
    return "failed";
  }

  async function save(): Promise<SaveOutcome> {
    const changed = changedFields(fields.value, before.value, draft.value);
    errors.value = {};
    problem.value = null;
    if (!Object.keys(changed).length) {
      conflict.value = null;
      return "unchanged";
    }
    const current = row.value;
    saving.value = true;
    try {
      const answer =
        current.kind === "node"
          ? await editNode(current.node.id, revision.value, changed)
          : await editStatement(current.statement.id, revision.value, changed);
      // another row chosen meanwhile (its draft given up): the tree read anew shows what was saved
      if (row.value.key !== current.key) return "saved";
      stand(answer.fields, answer.revision);
      conflict.value = null;
      return "saved";
    } catch (error) {
      return row.value.key === current.key ? refused(error) : "failed";
    } finally {
      saving.value = false;
    }
  }

  function settle(key: string, value?: string | string[]): void {
    const now = conflict.value;
    if (!now) return;
    if (value !== undefined) draft.value = { ...draft.value, [key]: Array.isArray(value) ? [...value] : value };
    conflict.value = { ...now, clashes: now.clashes.filter((clash) => clash.key !== key) };
  }

  return {
    fields,
    draft,
    revision,
    saving,
    errors,
    problem,
    conflict,
    closed,
    dirty,
    save,
    /** Keep the user's value of a field both changed. */
    keep: (key: string) => settle(key),
    /** Take the stored value of a field both changed. */
    take: (key: string) => settle(key, conflict.value?.stored[key]),
  };
}
