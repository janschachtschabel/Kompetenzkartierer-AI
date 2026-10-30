// Adding rows to a document's tree page (plan M1 9.8, Paket 9c2b L3, L4, L9, L10): the row being added - a node
// at the top or under the node chosen, a statement under it - which the panel shows in place of the row chosen,
// and the statement whose anchor the source offers to choose: one being added, else one chosen, in a tree the
// caller may change. Where a draft is open, beginning one waits for the user's answer (`pending`): it would take
// the draft's place. Added, the tree is read again, and where the page and the row being added are still there
// the new row is chosen; another row chosen lets it go (the view's leave guard asks first about entries).
import { computed, shallowRef, watch, type Ref, type WritableComputedRef } from "vue";

import type { Tree } from "@/api";
import type { Row, RowKey } from "@/documentTree";
import type { CreateTarget } from "@/rowCreate";

export interface TreeAddingOf {
  documentId: Ref<string>;
  tree: Ref<Tree | null>;
  selectedRow: Ref<Row | null>;
  selected: WritableComputedRef<RowKey | null>;
  /** A draft open in the side: none once a row is added. */
  draftOpen: Ref<boolean>;
  load: () => Promise<void>;
  /** The page is still under its own route (treeAddress.ts). */
  atOwnRoute: () => boolean;
}

export function useTreeAdding({ documentId, tree, selectedRow, selected, draftOpen, load, atOwnRoute }: TreeAddingOf) {
  // shallow: the panel's form tells which it added by this very object
  const creating = shallowRef<CreateTarget | null>(null);
  /** A row to add that waits for the user's answer: a draft is open whose place it would take. */
  const pending = shallowRef<CreateTarget | null>(null);

  const picking = computed(() => {
    if (!tree.value?.editable) return null;
    if (creating.value) return creating.value.kind === "statement" ? `new:${creating.value.node}` : null;
    const row = selectedRow.value;
    return row?.kind === "statement" ? row.key : null;
  });

  function begin(target: CreateTarget): void {
    if (draftOpen.value) pending.value = target;
    else creating.value = target;
  }

  /** The user's answer to a row to add over an open draft: let the draft go, or keep it. */
  function answer(go: boolean): void {
    if (go) creating.value = pending.value;
    pending.value = null;
  }

  /** A node at the tree's top. */
  function createAtTop(): void {
    begin({ kind: "node", document: documentId.value, parent: null });
  }

  /** Under the node chosen: a node, or a statement. */
  function create(kind: "node" | "statement"): void {
    const row = selectedRow.value;
    if (row?.kind !== "node") return;
    begin(kind === "statement" ? { kind, node: row.node.id } : { kind, document: documentId.value, parent: row.node.id });
  }

  /**
   * `target` added as `key`: the tree read again, and - its form still shown, the page still this one - the new
   * row chosen, the form let go only then, with no draft left to ask about. Where the user went on meanwhile, the
   * tree read again shows it.
   */
  async function created(key: RowKey, target: CreateTarget): Promise<void> {
    await load();
    if (creating.value !== target || !atOwnRoute()) return;
    draftOpen.value = false;
    selected.value = key;
    creating.value = null;
  }

  function cancel(): void {
    creating.value = null;
  }

  watch(
    () => selectedRow.value?.key,
    () => cancel(),
  );

  return { creating, pending, picking, createAtTop, create, answer, created, cancel };
}
