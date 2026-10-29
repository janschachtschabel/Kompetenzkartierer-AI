import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getDocumentBlocks, getForm, getTree } from "@/api";

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
});
