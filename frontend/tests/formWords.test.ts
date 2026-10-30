import { describe, expect, it } from "vitest";

import type { FormField, FormValue } from "@/api";
import { shownValue, valueLabel, valueText } from "@/formWords";

import { CV } from "./treeFixtures";

function value(iri: string, label: string): FormValue {
  return { iri, notation: null, label, alt_labels: [], definition: null, note: null, delimitation: null, examples: [], broader: [] };
}

const FIELDS: FormField[] = [
  { key: "original_title", kind: "text", required: true, many: false, most: 2000, values: null },
  { key: "function", kind: "concept", required: true, many: false, most: null, values: [value(CV + "fn_area", "Bereich")] },
  {
    key: "addressees",
    kind: "concepts",
    required: true,
    many: true,
    most: null,
    values: [value(CV + "addr_learner", "Lernende"), value(CV + "addr_educator", "Lehrkräfte")],
  },
];

describe("a form's words", () => {
  it("name a list's value by its label, one the form does not offer by itself", () => {
    expect(valueLabel(FIELDS, "function", CV + "fn_area")).toBe("Bereich");
    expect(valueLabel(FIELDS, "function", CV + "fn_gone")).toBe(CV + "fn_gone");
    expect(valueLabel(FIELDS, "no_such_field", CV + "fn_area")).toBe(CV + "fn_area");
  });

  it("say a field's value as text: a text itself, a list's values by their labels, none as nothing", () => {
    expect(valueText(FIELDS, "original_title", "Optik")).toBe("Optik");
    expect(valueText(FIELDS, "function", CV + "fn_area")).toBe("Bereich");
    expect(valueText(FIELDS, "addressees", [CV + "addr_learner", CV + "addr_educator"])).toBe("Lernende, Lehrkräfte");
    expect(valueText(FIELDS, "original_title", null)).toBe("");
    expect(valueText(FIELDS, "addressees", [])).toBe("");
  });

  it("show a value to be read beside another: an empty one as such, a list's by its labels", () => {
    expect(shownValue(FIELDS, "addressees", [])).toBe("leer");
    expect(shownValue(FIELDS, "original_title", "  ")).toBe("leer");
    expect(shownValue(FIELDS, "original_title", null)).toBe("leer");
    expect(shownValue(FIELDS, "addressees", [CV + "addr_learner"])).toBe("Lernende");
  });

  it("say a statement's anchors in a draft by their pages, each apart", () => {
    expect(valueText(FIELDS, "anchors", ["blocks:p5-b2,p5-b3", "page:7"])).toBe("Seite 5: 2 Blöcke; Auf Seite 7 nicht gefunden");
    expect(shownValue(FIELDS, "anchors", [])).toBe("leer");
  });
});
