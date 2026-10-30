// Adding rows to a document's tree page (plan M1 9.8, Paket 9c2b L3, L4, L9, L10): the row being added - a node
// at the top or under the node chosen, a statement under it - which the panel shows in place of the row chosen,
// and the statement whose anchor the source offers to choose: one being added, else one chosen, in a tree the
// caller may change. Added, the tree is read again and the new row chosen; another row chosen lets it go (the
// view's leave guard asks first about entries).
import { computed, ref, watch, type Ref, type WritableComputedRef } from "vue";

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
}

export function useTreeAdding({ documentId, tree, selectedRow, selected, draftOpen, load }: TreeAddingOf) {
  const creating = ref<CreateTarget | null>(null);

  const picking = computed(() => {
    if (!tree.value?.editable) return null;
    if (creating.value) return creating.value.kind === "statement" ? `new:${creating.value.node}` : null;
    const row = selectedRow.value;
    return row?.kind === "statement" ? row.key : null;
  });

  /** A node at the tree's top. */
  function createAtTop(): void {
    creating.value = { kind: "node", document: documentId.value, parent: null };
  }

  /** Under the node chosen: a node, or a statement. */
  function create(kind: "node" | "statement"): void {
    const row = selectedRow.value;
    if (row?.kind !== "node") return;
    creating.value =
      kind === "statement" ? { kind, node: row.node.id } : { kind, document: documentId.value, parent: row.node.id };
  }

  /** Added: the tree read again, the new row chosen - no draft left to ask about. */
  async function created(key: RowKey): Promise<void> {
    creating.value = null;
    draftOpen.value = false;
    await load();
    selected.value = key;
  }

  function cancel(): void {
    creating.value = null;
  }

  watch(
    () => selectedRow.value?.key,
    () => cancel(),
  );

  return { creating, picking, createAtTop, create, created, cancel };
}
