import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copyDocument, editDocument, freezeDocument, setWork } from "@/api";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function call(index = 0): [string, RequestInit] {
  return vi.mocked(fetch).mock.calls[index] as [string, RequestInit];
}

beforeEach(() => {
  // a body is read once: one answer per request
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(answer(200, { id: "d1" }))));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a document's edition and freeze requests", () => {
  it("change the document's title, issuer or edition, sending only those given", async () => {
    const changed = await editDocument("d/1", { issuer: "Ministerium", edition: null });

    expect([call()[0], call()[1].method]).toEqual(["/api/v1/documents/d%2F1", "PATCH"]);
    expect(JSON.parse(call()[1].body as string)).toEqual({ issuer: "Ministerium", edition: null });
    expect(changed).toEqual({ id: "d1" });
  });

  it("set the document's work: a new one, or one there is", async () => {
    await setWork("d1", { title: "Kernlehrplan Physik", region: "DE-NW", short_title: "klp-physik" });
    await setWork("d1", { work_id: "w1" });

    expect([call(0)[0], call(0)[1].method]).toEqual(["/api/v1/documents/d1/work", "PATCH"]);
    expect(JSON.parse(call(0)[1].body as string)).toEqual({
      title: "Kernlehrplan Physik",
      region: "DE-NW",
      short_title: "klp-physik",
    });
    expect(JSON.parse(call(1)[1].body as string)).toEqual({ work_id: "w1" });
  });

  it("freeze the document, taking its violations only when told to", async () => {
    await freezeDocument("d1", false);
    await freezeDocument("d1", true);

    expect([call(0)[0], call(0)[1].method, call(0)[1].body]).toEqual(["/api/v1/documents/d1/freeze", "POST", undefined]);
    expect(JSON.parse(call(1)[1].body as string)).toEqual({ accept_violations: true });
  });

  it("copy a frozen document as a draft, answered with the copy", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(answer(201, { id: "d2", copy_of: "d1" }));

    const copy = await copyDocument("d1");

    expect([call()[0], call()[1].method, call()[1].body]).toEqual(["/api/v1/documents/d1/draft-copy", "POST", undefined]);
    expect(copy).toEqual({ id: "d2", copy_of: "d1" });
  });
});
