import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getJob, getSource, importSource, listSources, uploadSource } from "@/api";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function call(index = 0): [string, RequestInit] {
  return vi.mocked(fetch).mock.calls[index] as [string, RequestInit];
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the register's requests", () => {
  it("send an upload as a form with the file and its title", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(201, { id: "a" }));
    const file = new File(["%PDF-1.7"], "lehrplan.pdf", { type: "application/pdf" });

    await uploadSource(file, "Lehrplan Physik");

    const [path, init] = call();
    const form = init.body as FormData;
    expect(path).toBe("/api/v1/sources");
    expect(init.method).toBe("POST");
    expect((form.get("file") as File).name).toBe("lehrplan.pdf");
    expect(form.get("title")).toBe("Lehrplan Physik");
  });

  it("leave a blank title out, so the file's name names the entry", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(201, { id: "a" }));

    await uploadSource(new File(["x"], "a.pdf"), "  ");

    expect((call()[1].body as FormData).has("title")).toBe(false);
  });

  it("send an import as JSON and give back its job", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(202, { source: { id: "s" }, job_id: "j" }));

    const started = await importSource("https://example.org/a.pdf", "");

    const [path, init] = call();
    expect(path).toBe("/api/v1/sources/import");
    expect(JSON.parse(init.body as string)).toEqual({ url: "https://example.org/a.pdf" });
    expect(started.job_id).toBe("j");
  });

  it("ask for a page with only the filters given", async () => {
    vi.mocked(fetch).mockResolvedValue(answer(200, { entries: [], total: 0, limit: 50, offset: 0 }));

    await listSources({ status: "acquired", q: "Physik & Chemie" });

    expect(call()[0]).toBe("/api/v1/sources?status=acquired&q=Physik+%26+Chemie&limit=50&offset=0");
  });

  it("put an id into the path as one segment", async () => {
    // a body is read once: one answer per request
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(answer(200, {})));

    await getSource("a/../b");
    await getJob("j 1");

    expect(call(0)[0]).toBe("/api/v1/sources/a%2F..%2Fb");
    expect(call(1)[0]).toBe("/api/v1/jobs/j%201");
  });
});
