// Adding a row to a document's tree (plan M1 9.8, Paket 9c2b L4, L6): a node at the top or under its parent,
// a statement after a node's others. Its draft begins empty, the form's fields and - for a statement - its
// anchors (anchorDraft.ts), and is open once anything is entered (the leave guard, L10). A required field
// left empty is said at it, a statement without an anchor at its list, before anything is asked; the request
// names the fields filled in. Refused, it says why as a save does (rowRefusals.ts), the draft kept.
import { computed, ref, shallowRef } from "vue";

import { addNode, addStatement, type EditFields, type Form, type FormField } from "@/api";
import { ANCHOR_FIELD, ANCHORS, anchorRequest, withAnchor, withoutAnchor } from "@/anchorDraft";
import { nodeKey, statementKey, type RowKey } from "@/documentTree";
import { t } from "@/i18n/de";
import type { Notice } from "@/notice";
import { changedFields, draftOf, type Draft } from "@/rowDraft";
import { applyRefusal, emptiedRequired, refusalOf, type Refusal } from "@/rowRefusals";

/** Where the row goes: a node into a document, at its top or under a parent; a statement under a node. */
export type CreateTarget = { kind: "node"; document: string; parent: string | null } | { kind: "statement"; node: string };

export type CreateOutcome = { outcome: "created"; key: RowKey } | { outcome: Refusal["outcome"] };

export function useRowCreate(target: CreateTarget, form: Form) {
  const fields: FormField[] = target.kind === "node" ? form.node : form.statement;
  // the draft's: the form's, and a statement's anchors
  const drafted = target.kind === "node" ? fields : [...fields, ANCHOR_FIELD];
  const empty = draftOf(drafted, {});
  const draft = shallowRef<Draft>({ ...empty });
  const saving = ref(false);
  const errors = ref<Record<string, string>>({});
  const problem = shallowRef<Notice | null>(null);
  const closed = ref<string | null>(null);
  const changes = computed(() => changedFields(drafted, empty, draft.value));
  const dirty = computed(() => Object.keys(changes.value).length > 0);

  function add(named: EditFields, anchors: unknown): Promise<RowKey> {
    if (target.kind === "node") return addNode(target.document, target.parent, named).then((row) => nodeKey(row.id));
    const codes = Array.isArray(anchors) ? anchors : [];
    return addStatement(target.node, named, anchorRequest(codes)).then((row) => statementKey(row.id));
  }

  async function save(): Promise<CreateOutcome> {
    // every field of the draft named: one left empty is one missing
    errors.value = emptiedRequired(drafted, { ...draft.value });
    problem.value = null;
    if (Object.keys(errors.value).length) return { outcome: "invalid" };
    const { [ANCHORS]: anchors, ...named } = changes.value;
    saving.value = true;
    try {
      return { outcome: "created", key: await add(named, anchors) };
    } catch (error) {
      const refusal = refusalOf(error, drafted, t("documents.tree.create.failed"));
      return { outcome: applyRefusal(refusal, { closed, errors, problem }) };
    } finally {
      saving.value = false;
    }
  }

  return {
    fields,
    draft,
    saving,
    errors,
    problem,
    closed,
    /** What the draft holds, as the request names it - a statement's anchors as their codes. */
    changes,
    dirty,
    save,
    /** Take an anchor (its code, anchorDraft.ts) into a statement's draft, once. */
    addAnchor: (code: string) => (draft.value = withAnchor(draft.value, code)),
    /** Take an anchor out of a statement's draft. */
    removeAnchor: (code: string) => (draft.value = withoutAnchor(draft.value, code)),
  };
}
