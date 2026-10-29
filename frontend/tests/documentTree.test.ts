import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import * as api from "@/api";
import type { CurriculumDocument, Tree } from "@/api";
import { rowsOf, useDocumentTree } from "@/documentTree";

import { form_, node_, statement_, tree_ } from "./treeFixtures";

function document_(changes: Partial<CurriculumDocument> = {}): CurriculumDocument {
  return {
    id: "d1",
    source_id: "s1",
    conversion_id: "c1",
    own: true,
    title: "Lehrplan Physik",
    document_type_iri: null,
    sector: "school",
    regions: ["DE-NW"],
    created_at: "2026-10-29T10:00:00Z",
    extraction: null,
    ...changes,
  };
}


beforeEach(() => {
  vi.restoreAllMocks();
});

describe("the rows of a tree", () => {
  it("stand in the tree's order: a node, its statements, then its children, each a level deeper", () => {
    const tree = [
      node_("b", { position: 2 }),
      node_("a", {
        position: 1,
        statements: [statement_("s2", { position: 2 }), statement_("s1", { position: 1 })],
        children: [node_("a1")],
      }),
    ];

    const rows = [...rowsOf(tree).values()];

    expect(rows.map((row) => [row.key, row.depth, row.parent])).toEqual([
      ["node:a", 0, null],
      ["statement:s1", 1, "node:a"],
      ["statement:s2", 1, "node:a"],
      ["node:a1", 1, "node:a"],
      ["node:b", 0, null],
    ]);
  });
});

describe("a document's tree", () => {
  it("is read with the document and the form of its sector", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getTree").mockResolvedValue(tree_([node_("a")]));
    const forms = vi.spyOn(api, "getForm").mockResolvedValue(form_());
    const read = useDocumentTree(ref("d1"));

    await read.load();
    await read.load();

    expect(read.document.value?.title).toBe("Lehrplan Physik");
    expect([...read.rows.value.keys()]).toEqual(["node:a"]);
    expect(read.form.value?.profile).toBe("schule");
    expect([read.loading.value, read.missing.value, read.failure.value]).toEqual([false, false, null]);
    expect(forms).toHaveBeenCalledTimes(1); // the sector's form is read once
    expect(forms).toHaveBeenCalledWith("school");
  });

  it("is missing where the document is none the caller may read", async () => {
    vi.spyOn(api, "getDocument").mockRejectedValue(new api.ApiError("server", 404, "no_document"));
    vi.spyOn(api, "getTree").mockRejectedValue(new api.ApiError("server", 404, "no_document"));
    vi.spyOn(api, "getForm").mockResolvedValue(form_());
    const read = useDocumentTree(ref("d1"));

    await read.load();

    expect([read.missing.value, read.tree.value, read.failure.value]).toEqual([true, null, null]);
  });

  it("keeps what it showed when reading it again fails, and says so", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    const trees = vi.spyOn(api, "getTree").mockResolvedValue(tree_([node_("a")]));
    vi.spyOn(api, "getForm").mockResolvedValue(form_());
    const read = useDocumentTree(ref("d1"));
    await read.load();
    trees.mockRejectedValue(new api.ApiError("network", 0));

    await read.load();

    expect([...read.rows.value.keys()]).toEqual(["node:a"]);
    expect(read.failure.value?.text).toBeTruthy();
    expect(read.missing.value).toBe(false);
  });

  it("shows nothing of one document while another's is read, though its reading fails", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    const trees = vi.spyOn(api, "getTree").mockResolvedValue(tree_([node_("a")]));
    vi.spyOn(api, "getForm").mockResolvedValue(form_());
    const id = ref("d1");
    const read = useDocumentTree(id);
    await read.load();
    trees.mockRejectedValue(new api.ApiError("network", 0));

    id.value = "d2";
    await read.load();

    expect([read.document.value, read.tree.value, read.rows.value.size]).toEqual([null, null, 0]);
    expect(read.failure.value?.text).toBeTruthy();
  });

  it("drops an answer a later reading overtook", async () => {
    vi.spyOn(api, "getDocument").mockResolvedValue(document_());
    vi.spyOn(api, "getForm").mockResolvedValue(form_());
    let first: (tree: Tree) => void = () => undefined;
    vi.spyOn(api, "getTree")
      .mockReturnValueOnce(new Promise((resolve) => (first = resolve)))
      .mockResolvedValueOnce(tree_([node_("new")]));
    const read = useDocumentTree(ref("d1"));

    const early = read.load();
    await read.load();
    first(tree_([node_("old")]));
    await early;

    expect([...read.rows.value.keys()]).toEqual(["node:new"]);
  });
});
