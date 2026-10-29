/**
 * A document's tree as its view reads it (plan M1 9.7, Paket 9c J6): the document, its nodes and statements
 * (GET …/tree) and the form of its sector, read together; each row by its key, in the tree's order - a node,
 * its statements, then its children, a level deeper each. The latest reading counts: an answer a later one
 * overtook is dropped. A reading that fails keeps what was shown of the same document and says so; a
 * document the caller may not read is missing, as the document page says (404 or an id that is no UUID, 422).
 */
import { computed, ref, shallowRef, type Ref } from "vue";

import {
  ApiError,
  getDocument,
  getForm,
  getTree,
  type CurriculumDocument,
  type Form,
  type Tree,
  type TreeNode,
  type TreeStatement,
} from "@/api";
import { t } from "@/i18n/de";
import { failureNotice, type Notice } from "@/notice";

export type RowKey = `node:${string}` | `statement:${string}`;

/** The query parameter of the row chosen in the tree's page (DocumentTreeView): "node:<id>", "statement:<id>". */
export const ROW_PARAM = "zeile";

interface RowPlace {
  key: RowKey;
  /** The node it stands under; none for one of the document's top. */
  parent: RowKey | null;
  /** From 0 at the top. */
  depth: number;
}

export type Row =
  | (RowPlace & { kind: "node"; node: TreeNode })
  | (RowPlace & { kind: "statement"; statement: TreeStatement; parent: RowKey });

export function nodeKey(id: string): RowKey {
  return `node:${id}`;
}

export function statementKey(id: string): RowKey {
  return `statement:${id}`;
}

function byPosition<T extends { position: number }>(rows: T[]): T[] {
  return [...rows].sort((one, other) => one.position - other.position);
}

/** Every row of the tree by its key, in the tree's order. */
export function rowsOf(nodes: TreeNode[]): Map<RowKey, Row> {
  const rows = new Map<RowKey, Row>();
  const visit = (node: TreeNode, parent: RowKey | null, depth: number): void => {
    const key = nodeKey(node.id);
    rows.set(key, { kind: "node", key, node, parent, depth });
    for (const said of byPosition(node.statements)) {
      rows.set(statementKey(said.id), {
        kind: "statement",
        key: statementKey(said.id),
        statement: said,
        parent: key,
        depth: depth + 1,
      });
    }
    for (const child of byPosition(node.children)) visit(child, key, depth + 1);
  };
  for (const node of byPosition(nodes)) visit(node, null, 0);
  return rows;
}

export function useDocumentTree(documentId: Ref<string>) {
  const document_ = shallowRef<CurriculumDocument | null>(null);
  const tree = shallowRef<Tree | null>(null);
  const form = shallowRef<Form | null>(null);
  const loading = ref(true);
  const missing = ref(false);
  const failure = ref<Notice | null>(null);
  const rows = computed(() => rowsOf(tree.value?.nodes ?? []));
  let generation = 0;
  // the id of the document shown, as it was asked for: the server's may be written otherwise
  let shownId: string | null = null;

  /** The document and its tree; a 404 or 422 of either is a document missing. */
  async function documentAndTree(id: string): Promise<[CurriculumDocument, Tree] | "missing"> {
    try {
      return await Promise.all([getDocument(id), getTree(id)]);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return "missing";
      throw error;
    }
  }

  async function load(): Promise<void> {
    const mine = ++generation;
    const id = documentId.value;
    if (shownId !== id) {
      // another document: what was shown is not its
      document_.value = null;
      tree.value = null;
    }
    loading.value = true;
    failure.value = null;
    missing.value = false;
    try {
      const read = await documentAndTree(id);
      if (mine !== generation) return;
      if (read === "missing") {
        missing.value = true;
        document_.value = null;
        tree.value = null;
        shownId = null;
        return;
      }
      const [found, nodes] = read;
      // the sector's form, read once; it failing says so, the document is not missing for it
      const known = form.value;
      const fields = known?.sector === found.sector ? known : await getForm(found.sector);
      if (mine !== generation) return;
      document_.value = found;
      tree.value = nodes;
      form.value = fields;
      shownId = id;
    } catch (error) {
      if (mine !== generation) return;
      failure.value = failureNotice(error, t("documents.tree.loadFailed"));
    } finally {
      if (mine === generation) loading.value = false;
    }
  }

  return { document: document_, tree, form, rows, loading, missing, failure, load };
}
