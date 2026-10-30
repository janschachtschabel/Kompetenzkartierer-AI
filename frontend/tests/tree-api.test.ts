import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  addNode,
  addStatement,
  dropNode,
  dropStatement,
  editNode,
  editStatement,
  getDocumentBlocks,
  getForm,
  getTree,
} from "@/api";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function call(index = 0): [string, RequestInit] {
  return vi.mocked(fetch).mock.calls[index] as [string, RequestInit];
}

beforeEach(() => {
  // a body is read once: one answer per request
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(answer(200, {}))));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the tree's requests", () => {
  it("read a document's tree, the form of its sector and a page of its own conversion", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(200, { editable: true, reviewable: false, counts: {}, nodes: [] }));

    const tree = await getTree("d1");
    await getForm("school");
    await getDocumentBlocks("d1", 2);

    expect(call(0)[0]).toBe("/api/v1/documents/d1/tree");
    expect(call(0)[1].method).toBeUndefined();
    expect(call(1)[0]).toBe("/api/v1/profiles/school/form");
    expect(call(2)[0]).toBe("/api/v1/documents/d1/blocks?page=2");
    expect(tree.editable).toBe(true);
  });

  it("put a document's id and a sector into the path as one segment each", async () => {
    await getTree("a/../b");
    await getForm("a b");
    await getDocumentBlocks("a/b", 1);

    expect(call(0)[0]).toBe("/api/v1/documents/a%2F..%2Fb/tree");
    expect(call(1)[0]).toBe("/api/v1/profiles/a%20b/form");
    expect(call(2)[0]).toBe("/api/v1/documents/a%2Fb/blocks?page=1");
  });

  it("give a refusal back with its code", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      answer(403, { code: "file_hidden", message: "The content of this entry is no longer yours to read." }),
    );

    await expect(getDocumentBlocks("d1", 1)).rejects.toMatchObject({ kind: "forbidden", code: "file_hidden" });
  });

  it("change a node and a statement by the fields changed and the revision they were read at", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(200, { id: "n1", revision: 4 }));

    const row = await editNode("n1", 3, { original_title: "Optik", addressees: ["a", "b"], code: null });
    await editStatement("s/1", 7, { verbatim: "Sie messen." });

    expect([call(0)[0], call(0)[1].method]).toEqual(["/api/v1/nodes/n1", "PATCH"]);
    expect(JSON.parse(call(0)[1].body as string)).toEqual({
      expected_revision: 3,
      fields: { original_title: "Optik", addressees: ["a", "b"], code: null },
    });
    expect([call(1)[0], call(1)[1].method]).toEqual(["/api/v1/statements/s%2F1", "PATCH"]);
    // no anchors: a statement's stay as they are
    expect(JSON.parse(call(1)[1].body as string)).toEqual({ expected_revision: 7, fields: { verbatim: "Sie messen." } });
    expect(row.revision).toBe(4);
  });

  it("set a statement's anchors, all of them, where a change names them", async () => {
    await editStatement("s1", 2, {}, [{ blocks: ["p5-b2", "p5-b3"] }, { page: 6 }]);
    await editStatement("s1", 3, {}, []);

    expect(JSON.parse(call(0)[1].body as string)).toEqual({
      expected_revision: 2,
      fields: {},
      anchors: [{ blocks: ["p5-b2", "p5-b3"] }, { page: 6 }],
    });
    // an empty list is a change too, not left out
    expect(JSON.parse(call(1)[1].body as string)).toEqual({ expected_revision: 3, fields: {}, anchors: [] });
  });

  it("add a node at the top or under a parent, which goes in the body", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(201, { id: "n9", revision: 1 }));

    const made = await addNode("d/1", null, { original_title: "Optik" });
    await addNode("d1", "n/1", { original_title: "Linsen" });

    expect([call(0)[0], call(0)[1].method]).toEqual(["/api/v1/documents/d%2F1/nodes", "POST"]);
    expect(JSON.parse(call(0)[1].body as string)).toEqual({ parent_id: null, fields: { original_title: "Optik" } });
    expect(call(1)[0]).toBe("/api/v1/documents/d1/nodes");
    expect(JSON.parse(call(1)[1].body as string)).toEqual({ parent_id: "n/1", fields: { original_title: "Linsen" } });
    expect(made).toMatchObject({ id: "n9", revision: 1 });
  });

  it("add a statement to a node with its fields and anchors", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(201, { id: "s9", revision: 1 }));

    const made = await addStatement("n/1", { verbatim: "Sie messen." }, [{ page: 5 }]);

    expect([call(0)[0], call(0)[1].method]).toEqual(["/api/v1/nodes/n%2F1/statements", "POST"]);
    expect(JSON.parse(call(0)[1].body as string)).toEqual({
      fields: { verbatim: "Sie messen." },
      anchors: [{ page: 5 }],
    });
    expect(made).toMatchObject({ id: "s9" });
  });

  it("take a node or a statement away at the revision it was read at, without a body", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(answer(200, { nodes: 3, statements: 4 }))
      .mockResolvedValueOnce(answer(200, { outcome: "rejected", revision: 8 }));

    const dropped = await dropNode("n/1", 3);
    const taken = await dropStatement("s/1", 7);

    expect([call(0)[0], call(0)[1].method]).toEqual(["/api/v1/nodes/n%2F1?expected_revision=3", "DELETE"]);
    expect(call(0)[1].body).toBeUndefined();
    expect([call(1)[0], call(1)[1].method]).toEqual(["/api/v1/statements/s%2F1?expected_revision=7", "DELETE"]);
    expect(call(1)[1].body).toBeUndefined();
    expect(dropped).toEqual({ nodes: 3, statements: 4 });
    expect(taken).toEqual({ outcome: "rejected", revision: 8 });
  });

  it("give a change of a row changed meanwhile back with the row as stored", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      answer(409, { code: "stale_revision", message: "Changed meanwhile.", details: { current: { id: "n1", revision: 5 } } }),
    );

    await expect(editNode("n1", 3, {})).rejects.toMatchObject({
      code: "stale_revision",
      details: { current: { id: "n1", revision: 5 } },
    });
  });
});
