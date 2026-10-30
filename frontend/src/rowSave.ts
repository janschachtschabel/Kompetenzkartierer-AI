// Saving a change to a row of a document's tree (plan M1 9.8, Paket 9c2 K4-K7). A change names only the fields
// changed (rowDraft.changedFields) and the revision its form was filled from; the answer is the row as stored.
// Where another stored a change meanwhile (409 stale_revision, details.current), what only the other changed
// is taken in and what both changed is put before the user (rowConflict.rebase), the change then laid on the
// stored row. Where the tree closed meanwhile (a job, frozen, X4 not done, no form) the reason is kept with the
// draft. A field's problem stands at the field - a required field emptied before anything is asked - any other
// failure above the form, the draft kept to try again. While a field both changed is undecided nothing is
// saved; what the user typed while a change was saved is laid on the row as stored. A statement's anchors are a
// field of its draft beside the form's (anchorDraft.ts, Paket 9c2b L2), sent - all of them - once they changed.
import { computed, ref, shallowRef, watch, type Ref } from "vue";

import {
  ApiError,
  editNode,
  editStatement,
  type EditFields,
  type FieldValue,
  type Form,
  type FormField,
  type NodeRow,
  type TreeAnchor,
  type TreeStatement,
} from "@/api";
import { ANCHOR_FIELD, ANCHORS, anchorRequest, anchorsOf, withAnchor, withoutAnchor } from "@/anchorDraft";
import type { Row } from "@/documentTree";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { rebase, type Clash } from "@/rowConflict";
import { changedFields, draftOf, type Draft } from "@/rowDraft";
import { applyRefusal, emptiedRequired, refusalOf } from "@/rowRefusals";

/** How a save went: the editor says each in its own way. */
export type SaveOutcome = "saved" | "unchanged" | "undecided" | "conflict" | "invalid" | "closed" | "gone" | "failed";

export interface RowConflict {
  clashes: Clash[];
  taken: string[];
  stored: Draft;
}

interface Stored {
  fields: Record<string, FieldValue>;
  anchors?: TreeAnchor[];
}

function storedOf(row: Row): Stored {
  return row.kind === "node" ? row.node : row.statement;
}

// by the keys of the draft - the anchors as their codes, which a node's draft does not hold
function valuesOf(stored: Stored): Record<string, FieldValue> {
  return { ...stored.fields, [ANCHORS]: anchorsOf(stored.anchors ?? []) };
}

function revisionOf(row: Row): number {
  return row.kind === "node" ? row.node.revision : row.statement.revision;
}

export function useRowSave(row: Ref<Row>, form: Ref<Form>) {
  const fields = computed<FormField[]>(() => (row.value.kind === "node" ? form.value.node : form.value.statement));
  // the draft's: the form's, and a statement's anchors
  const drafted = computed<FormField[]>(() => (row.value.kind === "node" ? fields.value : [...fields.value, ANCHOR_FIELD]));
  const before = shallowRef<Draft>(draftOf(drafted.value, valuesOf(storedOf(row.value))));
  const draft = shallowRef<Draft>({ ...before.value });
  const revision = ref(revisionOf(row.value));
  const saving = ref(false);
  const errors = ref<Record<string, string>>({});
  const problem = shallowRef<Notice | null>(null);
  const conflict = shallowRef<RowConflict | null>(null);
  const closed = ref<string | null>(null);
  const changes = computed(() => changedFields(drafted.value, before.value, draft.value));
  const dirty = computed(() => Object.keys(changes.value).length > 0);

  function stand(stored: Stored, at: number): void {
    before.value = draftOf(drafted.value, valuesOf(stored));
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
      stand(storedOf(now), revisionOf(now));
    } else if (!dirty.value) stand(storedOf(now), revisionOf(now));
  });

  function refused(error: unknown): SaveOutcome {
    const code = error instanceof ApiError ? error.code : undefined;
    const details = error instanceof ApiError ? error.details : {};
    if (code === "stale_revision") {
      const current = details.current as Partial<Stored> & { revision?: number } | null;
      if (!current?.fields || typeof current.revision !== "number") return "gone";
      const now = { fields: current.fields, anchors: current.anchors };
      const stored = draftOf(drafted.value, valuesOf(now));
      const laid = rebase(drafted.value, before.value, draft.value, stored);
      // the other stored what the user asked: saved, by whoever
      if (!Object.keys(changedFields(drafted.value, stored, laid.draft)).length) {
        stand(now, current.revision);
        conflict.value = null;
        return "saved";
      }
      before.value = stored;
      draft.value = laid.draft;
      revision.value = current.revision;
      conflict.value = { clashes: laid.clashes, taken: laid.taken, stored };
      return "conflict";
    }
    const refusal = refusalOf(error, drafted.value, t("documents.tree.form.saveFailed"));
    return applyRefusal(refusal, { closed, errors, problem });
  }

  // A statement's anchors go apart from its fields, and only where they changed: left out, they stay
  function send(current: Row, changed: EditFields): Promise<NodeRow | TreeStatement> {
    if (current.kind === "node") return editNode(current.node.id, revision.value, changed);
    const { [ANCHORS]: anchors, ...named } = changed;
    return Array.isArray(anchors)
      ? editStatement(current.statement.id, revision.value, named, anchorRequest(anchors))
      : editStatement(current.statement.id, revision.value, named);
  }

  async function save(): Promise<SaveOutcome> {
    if (conflict.value?.clashes.length) return "undecided";
    const changed = changedFields(drafted.value, before.value, draft.value);
    errors.value = emptiedRequired(drafted.value, changed);
    problem.value = null;
    if (Object.keys(errors.value).length) return "invalid";
    if (!Object.keys(changed).length) {
      conflict.value = null;
      return "unchanged";
    }
    const current = row.value;
    const sent = draft.value;
    saving.value = true;
    try {
      const answer = await send(current, changed);
      // another row chosen meanwhile (its draft given up): the tree read anew shows what was saved
      if (row.value.key !== current.key) return "saved";
      const typed = draft.value;
      stand(answer, answer.revision);
      // typed on while it was saved: that stays, laid on the row as stored
      if (typed !== sent) draft.value = rebase(drafted.value, sent, typed, before.value).draft;
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
    /** The row as the draft began from it, or as stored where a change met another. */
    before,
    draft,
    revision,
    saving,
    errors,
    problem,
    conflict,
    closed,
    /** What the draft changes, as a change sends it - a statement's anchors as their codes. */
    changes,
    dirty,
    save,
    /** Keep the user's value of a field both changed. */
    keep: (key: string) => settle(key),
    /** Take the stored value of a field both changed. */
    take: (key: string) => settle(key, conflict.value?.stored[key]),
    /** Take an anchor (its code, anchorDraft.ts) into a statement's draft, once; whether the draft changed. */
    addAnchor: (code: string): boolean => {
      const now = withAnchor(draft.value, code);
      if (now === draft.value) return false;
      draft.value = now;
      return true;
    },
    /** Take an anchor out of a statement's draft. */
    removeAnchor: (code: string) => (draft.value = withoutAnchor(draft.value, code)),
  };
}
