import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { askConversion, getBlocks, getConversion } from "@/api";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function call(index = 0): [string, RequestInit] {
  return vi.mocked(fetch).mock.calls[index] as [string, RequestInit];
}

beforeEach(() => {
  // a body is read once: one answer per request
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(answer(200, { id: "c1", status: "pending" }))));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the conversion's requests", () => {
  it("ask for the conversion of an entry's file with the default engine, and give it back", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(202, { id: "c1", status: "pending", job_id: "j1" }));

    const asked = await askConversion("s1");

    const [path, init] = call();
    expect(path).toBe("/api/v1/sources/s1/conversions");
    expect(init.method).toBe("POST");
    // no body: the server takes its one engine; an empty object would say the same at more length
    expect(init.body).toBeUndefined();
    expect(asked.job_id).toBe("j1");
  });

  it("read how far the conversion is, and the blocks of one page", async () => {
    await getConversion("s1");
    await getBlocks("s1", 3);

    expect(call(0)[0]).toBe("/api/v1/sources/s1/conversion");
    expect(call(0)[1].method).toBeUndefined();
    expect(call(1)[0]).toBe("/api/v1/sources/s1/conversion/blocks?page=3");
  });

  it("put the entry's id into the path as one segment", async () => {
    await askConversion("a/../b");
    await getConversion("a/../b");
    await getBlocks("a b", 1);

    expect(call(0)[0]).toBe("/api/v1/sources/a%2F..%2Fb/conversions");
    expect(call(1)[0]).toBe("/api/v1/sources/a%2F..%2Fb/conversion");
    expect(call(2)[0]).toBe("/api/v1/sources/a%20b/conversion/blocks?page=1");
  });
});
