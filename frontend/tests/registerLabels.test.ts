import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/de";

/** The values of a `Literal[...]` the backend names `name` in app/sources/register.py. */
function backendValues(name: string): string[] {
  const source = readFileSync(join(process.cwd(), "..", "backend", "app", "sources", "register.py"), "utf8");
  const literal = new RegExp(`^${name} = Literal\\[([^\\]]*)\\]`, "m").exec(source)?.[1] ?? "";
  return [...literal.matchAll(/"([^"]+)"/g)].map(([, value]) => value).sort();
}

describe("the register's words", () => {
  it("read the backend's lists", () => {
    expect(backendValues("RegisterStatus")).toContain("acquired");
    expect(backendValues("Provenance")).toContain("upload");
  });

  it.each([
    ["Provenance", messages.sources.provenance],
    ["RegisterStatus", messages.sources.status],
    ["RightsStatus", messages.sources.rights],
    ["SourceType", messages.entryPage.sourceType],
    ["CheckOutcome", messages.entryPage.outcome],
    ["DetectedKind", messages.entryPage.kind],
    ["Evidence", messages.entryPage.evidence],
  ])("name every value of %s, and no other", (name, words) => {
    // a value without words showed an empty cell; words for no value are read by nobody
    expect(Object.keys(words).sort()).toEqual(backendValues(name));
  });

  it("name the federation and the sixteen Länder, by the codes of ISO 3166-2:DE the seeds give", () => {
    // the backend checks only a code's form (source_register.py, Country): the list is the standard's
    const codes = ["BB", "BE", "BW", "BY", "HB", "HE", "HH", "MV", "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH"];

    expect(Object.keys(messages.sources.countries).sort()).toEqual(["DE", ...codes.map((code) => `DE-${code}`)]);
  });
});
