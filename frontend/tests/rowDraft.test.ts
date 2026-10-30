import { describe, expect, it } from "vitest";

import { changedFields, draftOf, offeredValues, parentField, sameValue } from "@/rowDraft";

import { CV, SCHOOL, form_, value_ } from "./treeFixtures";

const NODE = form_().node;
const STATEMENT = form_().statement;

function field(key: string) {
  const found = [...NODE, ...STATEMENT].find((item) => item.key === key);
  if (!found) throw new Error(key);
  return found;
}

describe("a row's draft", () => {
  it("holds each field of the form: a text or a value's IRI as a string, a list as an array, none as empty", () => {
    const draft = draftOf(STATEMENT, { verbatim: "Sie messen.", statement_kind: null, addressees: [CV + "addr_learner"] });

    expect(draft).toEqual({
      verbatim: "Sie messen.",
      statement_kind: "",
      addressees: [CV + "addr_learner"],
      levelText: "",
    });
  });

  it("takes a blank text, an empty list and none for the same, and lists in any order", () => {
    expect(sameValue("", null)).toBe(true);
    expect(sameValue("  ", "")).toBe(true);
    expect(sameValue(" Optik ", "Optik")).toBe(true);
    expect(sameValue([], null)).toBe(true);
    expect(sameValue(["b", "a"], ["a", "b"])).toBe(true);
    expect(sameValue(["a"], ["a", "b"])).toBe(false);
    expect(sameValue("Optik", "Licht")).toBe(false);
  });

  it("names only the fields changed: a blank as none, a list in the form's order", () => {
    const before = draftOf(STATEMENT, { verbatim: "Sie messen.", statement_kind: CV + "kind_learningOutcome", addressees: [] });
    const draft = {
      ...before,
      verbatim: "Sie messen. ",
      levelText: "  ",
      addressees: [CV + "addr_educator", CV + "addr_learner"],
    };

    expect(changedFields(STATEMENT, before, draft)).toEqual({
      addressees: [CV + "addr_learner", CV + "addr_educator"], // in the order the form lists them
    });
    expect(changedFields(STATEMENT, before, { ...before, verbatim: "", levelText: "Stufe 1" })).toEqual({
      verbatim: null,
      levelText: "Stufe 1",
    });
  });

  it("keeps a value of a list the form does not know, after those it knows", () => {
    const before = draftOf(STATEMENT, { addressees: [] });

    expect(changedFields(STATEMENT, before, { ...before, addressees: ["urn:x", CV + "addr_learner"] })).toEqual({
      addressees: [CV + "addr_learner", "urn:x"],
    });
  });
});

describe("a field whose values hang under another's", () => {
  it("hangs under the field whose values its values name as broader, and a field without such under none", () => {
    expect(parentField(NODE, field("node_type"))?.key).toBe("function");
    expect(parentField(NODE, field("function"))).toBeNull();
    expect(parentField(NODE, field("original_title"))).toBeNull();
    // values that refine values of their own field (a narrower type): no field above them
    const types = { ...field("node_type"), values: [value_("urn:a", "A"), value_("urn:b", "B", { broader: ["urn:a"] })] };
    expect(parentField([...NODE, types], types)).toBeNull();
  });

  it("offers the values under the parent's value chosen, every value while none is chosen", () => {
    const fields = [
      ...NODE.filter((item) => item.key !== "node_type"),
      {
        ...field("node_type"),
        values: [
          value_(SCHOOL + "Inhaltsbereich", "Inhaltsbereich", { broader: [CV + "fn_area"] }),
          value_(SCHOOL + "Lernsequenz", "Lernsequenz", { broader: [CV + "fn_unit"] }),
        ],
      },
    ];
    const type = fields.find((item) => item.key === "node_type");
    if (!type) throw new Error("node_type");

    const offered = (draft: Record<string, string>) =>
      offeredValues(fields, type, { ...draftOf(fields, {}), ...draft }).map((value) => value.label);

    expect(offered({ function: CV + "fn_unit" })).toEqual(["Lernsequenz"]);
    expect(offered({ function: "" })).toEqual(["Inhaltsbereich", "Lernsequenz"]);
    // the value held, though no longer under the parent's: still shown, the server says why it is refused
    expect(offered({ function: CV + "fn_unit", node_type: SCHOOL + "Inhaltsbereich" })).toEqual([
      "Inhaltsbereich",
      "Lernsequenz",
    ]);
    expect(offeredValues(fields, field("function"), draftOf(fields, {})).map((value) => value.label)).toEqual([
      "Bereich",
      "Einheit",
    ]);
  });
});
