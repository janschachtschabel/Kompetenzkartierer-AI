import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import type * as api from "@/api";
import { isolate } from "@/bidi";
import { conversionFailureText, findingText } from "@/conversionWords";
import { messages, t } from "@/i18n/de";

/** true where `A` and `B` name the same values; vue-tsc fails the list below where they do not. */
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;

// a text block says no kind: it is what most blocks are
const typesFollow: [
  Same<api.FindingCode, Exclude<keyof typeof messages.conversions.findings, "other">>,
  Same<Exclude<api.BlockKind, "text">, keyof typeof messages.conversionPage.kind>,
] = [true, true];

/** The values of the `Literal[...]` the backend names `name` in app/conversion/base.py. */
function backendValues(name: string): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "conversion", "base.py"), "utf8");
  const literal = new RegExp(`^${name} = Literal\\[([^\\]]*)\\]`, "m").exec(source)?.[1] ?? "";
  return [...literal.matchAll(/"([^"]+)"/g)].map(([, value]) => value).sort();
}

const symbol = (params: Record<string, unknown>): api.ConversionFinding => ({ code: "unmapped_symbol", params });

describe("what a conversion found, in words", () => {
  it("says how many signs of a symbol font were left as they are, and on which page", () => {
    const text = findingText(symbol({ codepoint: "U+F0B7", count: 3, pages: [1] }));

    expect(text).toBe(t("conversions.findings.unmapped_symbol", { count: 3, codepoint: "U+F0B7", pageCount: 1, pages: "1" }));
    expect(text).toContain("3 Zeichen");
    expect(text).toContain("U+F0B7");
    expect(text).toContain("Seite 1 ");
  });

  it("says one sign as one, and runs of pages as ranges", () => {
    const one = findingText(symbol({ codepoint: "U+F0A7", count: 1, pages: [2] }));
    const many = findingText(symbol({ codepoint: "U+F0A7", count: 40, pages: [1, 2, 3, 5, 7, 8] }));

    expect(one).toContain("1 Zeichen");
    expect(one).toContain("steht es");
    const ranges = [t("conversions.pageRange", { from: 1, to: 3 }), "5", t("conversions.pageRange", { from: 7, to: 8 })];
    expect(many).toContain(`Seiten ${new Intl.ListFormat("de-DE", { type: "conjunction" }).format(ranges)} `);
  });

  it("says that the text layer looks damaged, how much of it, and what it looks like", () => {
    const text = findingText({ code: "encoding_suspect", params: { share: 0.034, count: 41, examples: ["Ã¤", "(cid:3)"] } });

    expect(text).toContain("41 verdächtige Zeichen");
    expect(text).toContain("3,4");
    // the document's own signs, set apart from the sentence around them
    expect(text).toContain(`„${isolate("Ã¤")}“`);
    expect(text).toContain(`„${isolate("(cid:3)")}“`);
  });

  it("says a finding it has no words for, or whose numbers are missing, by its code rather than guess", () => {
    expect(findingText({ code: "something_new", params: {} })).toBe(t("conversions.findings.other", { code: "something_new" }));
    expect(findingText(symbol({ codepoint: "U+F0B7", count: "drei", pages: [1] }))).toBe(
      t("conversions.findings.other", { code: "unmapped_symbol" }),
    );
    expect(findingText({ code: "encoding_suspect", params: { share: 0.5, count: 30 } })).toBe(
      t("conversions.findings.other", { code: "encoding_suspect" }),
    );
  });

  it("has words for every finding the backend reports, and for no other", () => {
    expect(typesFollow.every(Boolean)).toBe(true);
    const worded = Object.keys(messages.conversions.findings).filter((code) => code !== "other");

    expect(worded.sort()).toEqual(backendValues("FindingCode"));
  });
});

describe("what a block is, in words", () => {
  it("names every kind the backend has but text, and no other", () => {
    expect(backendValues("BlockKind")).toContain("page_header");

    expect([...Object.keys(messages.conversionPage.kind), "text"].sort()).toEqual(backendValues("BlockKind"));
  });
});

describe("why a conversion failed, in words", () => {
  it("is its job's reason", () => {
    expect(conversionFailureText("needs_ocr")).toBe(t("jobs.failures.needs_ocr"));
    expect(conversionFailureText("lease_lost")).toBe(t("jobs.failures.lease_lost"));
  });

  it("is that it was stopped, where its job was cancelled", () => {
    expect(conversionFailureText("cancelled")).toBe(t("conversions.cancelled"));
  });

  it("is the service's failure, not a foreign server's, where its job failed again and again", () => {
    // a conversion asks no other server: the words of a fetch would point the wrong way
    expect(conversionFailureText("handler_error")).toBe(t("conversions.handlerError"));
    expect(conversionFailureText("handler_error")).not.toBe(t("jobs.failures.handler_error"));
  });

  it("is the general words for a code the page does not know, or for none", () => {
    expect(conversionFailureText("something_new")).toBe(t("jobs.failedUnknown"));
    expect(conversionFailureText(null)).toBe(t("jobs.failedUnknown"));
  });
});
