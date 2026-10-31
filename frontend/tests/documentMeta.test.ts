import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError, type DocumentWork } from "@/api";
import { knownWorks, metaChanges, saveMeta, saveWork, shortTitleOk, workWords } from "@/documentMeta";
import { t } from "@/i18n/de";

import { documentOf } from "./documentFixtures";

const work = (id: string, title: string): DocumentWork => ({ id, title, region: "DE-NW", short_title: null, iri: null });

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("a document's title, issuer and edition to save", () => {
  it("are the ones changed, an emptied one as none and each trimmed", () => {
    const document = documentOf({ title: "Lehrplan Physik", issuer: "MSB", edition: null });

    expect(metaChanges(document, { title: "Lehrplan Physik", issuer: "MSB", edition: "" })).toEqual({});
    expect(metaChanges(document, { title: " Kernlehrplan Physik ", issuer: "  ", edition: "2019" })).toEqual({
      title: "Kernlehrplan Physik",
      issuer: null,
      edition: "2019",
    });
  });
});

describe("a work's short title", () => {
  it("is lower-case letters and digits in words joined by single hyphens, 200 at most", () => {
    expect(["klp", "klp-physik-2019", "a".repeat(200)].map(shortTitleOk)).toEqual([true, true, true]);
    expect(["", "KLP", "klp physik", "klp--physik", "-klp", "klp-", "kläp", "a".repeat(201)].map(shortTitleOk)).toEqual(
      [false, false, false, false, false, false, false, false],
    );
  });
});

describe("a work in words", () => {
  it("is its title, then its land and short title where it has them", () => {
    expect(workWords({ ...work("w1", "Kernlehrplan"), short_title: "klp" })).toBe("Kernlehrplan (Nordrhein-Westfalen, klp)");
    expect(workWords({ ...work("w1", "Kernlehrplan"), region: null })).toBe("Kernlehrplan");
  });
});

describe("the works there are", () => {
  it("are the works of the documents given, each once, by title", () => {
    const documents = [
      documentOf({ id: "d1", work: work("w2", "Rahmenlehrplan") }),
      documentOf({ id: "d2", work: null }),
      documentOf({ id: "d3", work: work("w1", "Kernlehrplan") }),
      documentOf({ id: "d4", work: work("w2", "Rahmenlehrplan") }),
    ];

    expect(knownWorks(documents).map((one) => one.id)).toEqual(["w1", "w2"]);
  });
});

describe("saving the title, issuer and edition", () => {
  it("gives the document saved", async () => {
    const saved = documentOf({ issuer: "MSB" });
    const sent = vi.spyOn(api, "editDocument").mockResolvedValue(saved);

    expect(await saveMeta("d1", { issuer: "MSB" })).toEqual({ outcome: "saved", document: saved });
    expect(sent).toHaveBeenCalledWith("d1", { issuer: "MSB" });
  });

  it("says a field's problem at its field", async () => {
    vi.spyOn(api, "editDocument").mockRejectedValue(
      new ApiError("server", 422, "invalid_field", "Bad.", { field: "issuer", problem: "too_long" }),
    );

    expect(await saveMeta("d1", { issuer: "x" })).toEqual({
      outcome: "invalid",
      field: "issuer",
      problem: t("documents.tree.problems.too_long"),
    });
  });

  it("says a field's problem with no field named as a failure, above the form", async () => {
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("server", 422, "invalid_field", "Bad."));

    expect(await saveMeta("d1", { issuer: "x" })).toMatchObject({ outcome: "failed" });
  });

  it.each(["frozen", "named"])("says a document closed to the change by %s, to be read again", async (code) => {
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("server", 409, code));

    expect(await saveMeta("d1", { issuer: "x" })).toEqual({ outcome: "closed", code });
  });

  it.each(["job_open", "not_extracted"])("is refused for %s", async (code) => {
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("server", 409, code));

    expect(await saveMeta("d1", { issuer: "x" })).toEqual({ outcome: "refused", code });
  });

  it("says another failure as one", async () => {
    vi.spyOn(api, "editDocument").mockRejectedValue(new ApiError("network", 0));

    expect(await saveMeta("d1", { issuer: "x" })).toMatchObject({
      outcome: "failed",
      problem: { text: t("documents.page.edition.saveFailed") },
    });
  });
});

describe("setting the work", () => {
  it("gives the document with its work", async () => {
    const saved = documentOf({ work: work("w1", "Kernlehrplan") });
    const sent = vi.spyOn(api, "setWork").mockResolvedValue(saved);

    expect(await saveWork("d1", { work_id: "w1" })).toEqual({ outcome: "saved", document: saved });
    expect(sent).toHaveBeenCalledWith("d1", { work_id: "w1" });
  });

  it("says a field's problem at its field, and a work gone or a caller who is no editor as refused", async () => {
    vi.spyOn(api, "setWork")
      .mockRejectedValueOnce(new ApiError("server", 422, "invalid_field", "Bad.", { field: "region", problem: "not_offered" }))
      .mockRejectedValueOnce(new ApiError("server", 404, "no_work"))
      .mockRejectedValueOnce(new ApiError("forbidden", 403, "not_editor"))
      .mockRejectedValueOnce(new ApiError("network", 0));
    const asked = { title: "Kernlehrplan", region: "DE-XX", short_title: "klp" };

    expect(await saveWork("d1", asked)).toEqual({
      outcome: "invalid",
      field: "region",
      problem: t("documents.tree.problems.not_offered"),
    });
    expect(await saveWork("d1", asked)).toEqual({ outcome: "refused", code: "no_work" });
    expect(await saveWork("d1", asked)).toEqual({ outcome: "refused", code: "not_editor" });
    expect(await saveWork("d1", asked)).toMatchObject({
      outcome: "failed",
      problem: { text: t("documents.page.edition.workFailed") },
    });
  });
});
