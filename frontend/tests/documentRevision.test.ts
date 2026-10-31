import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api";
import { ApiError } from "@/api";
import { copy, freeze, missingWords } from "@/documentRevision";
import { t } from "@/i18n/de";

import { documentOf } from "./documentFixtures";

const refusal = (code: string, details: Record<string, unknown> = {}) =>
  new ApiError("server", 409, code, "Refused.", details);

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("freezing a document", () => {
  it("freezes it, its violations taken only when told, and gives it frozen", async () => {
    const frozen = documentOf({ iri: "https://example.org/kk/doc/de-nw/msb/klp/2019", frozen_at: "2026-10-31T10:00:00Z" });
    const sent = vi.spyOn(api, "freezeDocument").mockResolvedValue(frozen);

    expect(await freeze("d1", true)).toEqual({ outcome: "frozen", document: frozen });
    expect(sent).toHaveBeenCalledWith("d1", true);
  });

  it("gives the count of violations to ask about, and a refusal where it names none", async () => {
    vi.spyOn(api, "freezeDocument")
      .mockRejectedValueOnce(refusal("has_violations", { violations: 3 }))
      .mockRejectedValueOnce(refusal("has_violations"));

    expect(await freeze("d1", false)).toEqual({ outcome: "violations", count: 3 });
    expect(await freeze("d1", false)).toEqual({ outcome: "refused", code: "has_violations" });
  });

  it("names what is missing, as the server lists it", async () => {
    vi.spyOn(api, "freezeDocument")
      .mockRejectedValueOnce(refusal("incomplete", { missing: ["work", "issuer"] }))
      .mockRejectedValueOnce(refusal("incomplete", { missing: "work" }))
      .mockRejectedValueOnce(refusal("incomplete", { missing: ["work", 3] }));

    expect(await freeze("d1", false)).toEqual({ outcome: "incomplete", missing: ["work", "issuer"] });
    expect(await freeze("d1", false)).toEqual({ outcome: "incomplete", missing: [] });
    expect(await freeze("d1", false)).toEqual({ outcome: "incomplete", missing: ["work"] });
  });

  it("says a check is owed", async () => {
    vi.spyOn(api, "freezeDocument").mockRejectedValue(refusal("check_owed", { unchecked: 2 }));

    expect(await freeze("d1", false)).toEqual({ outcome: "owed" });
  });

  it.each(["frozen", "job_open"])("says the document closed by %s, to be read again", async (code) => {
    vi.spyOn(api, "freezeDocument").mockRejectedValue(refusal(code));

    expect(await freeze("d1", false)).toEqual({ outcome: "closed", code });
  });

  it.each(["not_extracted", "no_iri_base", "iri_taken", "not_editor"])("is refused for %s", async (code) => {
    vi.spyOn(api, "freezeDocument").mockRejectedValue(refusal(code));

    expect(await freeze("d1", false)).toEqual({ outcome: "refused", code });
  });

  it("says another failure as one", async () => {
    vi.spyOn(api, "freezeDocument")
      .mockRejectedValueOnce(new ApiError("server", 404, "no_document"))
      .mockRejectedValueOnce(new ApiError("network", 0));

    expect(await freeze("d1", false)).toMatchObject({ outcome: "failed" });
    expect(await freeze("d1", false)).toMatchObject({
      outcome: "failed",
      problem: { text: t("documents.page.freeze.failed") },
    });
  });
});

describe("what is missing to freeze", () => {
  it("is named item by item, an item it does not know left out", () => {
    expect(missingWords(["work", "region", "short_title", "issuer", "edition", "colour"])).toEqual([
      t("documents.page.freeze.missing.work"),
      t("documents.page.freeze.missing.region"),
      t("documents.page.freeze.missing.short_title"),
      t("documents.page.freeze.missing.issuer"),
      t("documents.page.freeze.missing.edition"),
    ]);
  });
});

describe("copying a frozen document as a draft", () => {
  it("gives the copy", async () => {
    const draft = documentOf({ id: "d2", copy_of: "d1", revision: 2 });
    const sent = vi.spyOn(api, "copyDocument").mockResolvedValue(draft);

    expect(await copy("d1")).toEqual({ outcome: "copied", document: draft });
    expect(sent).toHaveBeenCalledWith("d1");
  });

  it("names the draft open already, where the server does", async () => {
    vi.spyOn(api, "copyDocument")
      .mockRejectedValueOnce(refusal("draft_open", { document_id: "d9" }))
      .mockRejectedValueOnce(refusal("draft_open"))
      .mockRejectedValueOnce(refusal("draft_open", { document_id: 42 }));

    expect(await copy("d1")).toEqual({ outcome: "open", documentId: "d9" });
    expect(await copy("d1")).toEqual({ outcome: "open", documentId: null });
    expect(await copy("d1")).toEqual({ outcome: "open", documentId: null });
  });

  it("says a document no longer frozen as stale, to be read again", async () => {
    vi.spyOn(api, "copyDocument").mockRejectedValue(refusal("not_frozen"));

    expect(await copy("d1")).toEqual({ outcome: "stale" });
  });

  it.each(["not_latest", "vocabulary_changed", "not_editor"])("is refused for %s", async (code) => {
    vi.spyOn(api, "copyDocument").mockRejectedValue(refusal(code));

    expect(await copy("d1")).toEqual({ outcome: "refused", code });
  });

  it("says another failure as one", async () => {
    vi.spyOn(api, "copyDocument")
      .mockRejectedValueOnce(new ApiError("server", 404, "no_document"))
      .mockRejectedValueOnce(new ApiError("network", 0));

    expect(await copy("d1")).toMatchObject({ outcome: "failed" });
    expect(await copy("d1")).toMatchObject({
      outcome: "failed",
      problem: { text: t("documents.page.revision.copyFailed") },
    });
  });
});
