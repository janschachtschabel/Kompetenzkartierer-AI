import { describe, expect, it } from "vitest";

import { rebase } from "@/rowConflict";
import { draftOf } from "@/rowDraft";

import { CV, form_ } from "./treeFixtures";

const FIELDS = form_().statement; // verbatim, statement_kind, addressees, levelText
const LEARNER = CV + "addr_learner";
const EDUCATOR = CV + "addr_educator";

const BEFORE = draftOf(FIELDS, {
  verbatim: "Sie messen.",
  statement_kind: CV + "kind_learningOutcome",
  addressees: [LEARNER],
  levelText: null,
});

describe("a change laid beside the row as another stored it meanwhile", () => {
  it("takes in a field only the other changed, and names it", () => {
    const stored = { ...BEFORE, levelText: "Stufe 2" };

    const rebased = rebase(FIELDS, BEFORE, { ...BEFORE, verbatim: "Sie messen genau." }, stored);

    expect(rebased.draft).toEqual({ ...BEFORE, verbatim: "Sie messen genau.", levelText: "Stufe 2" });
    expect(rebased.taken).toEqual(["levelText"]);
    expect(rebased.clashes).toEqual([]);
  });

  it("puts a field both changed, to different values, before the user, the draft keeping theirs", () => {
    const rebased = rebase(FIELDS, BEFORE, { ...BEFORE, verbatim: "Mein Satz." }, { ...BEFORE, verbatim: "Ihr Satz." });

    expect(rebased.clashes).toEqual([{ key: "verbatim", yours: "Mein Satz.", stored: "Ihr Satz." }]);
    expect(rebased.draft.verbatim).toBe("Mein Satz.");
    expect(rebased.taken).toEqual([]);
  });

  it("lets a field both changed alike and a field only the user changed be", () => {
    const draft = { ...BEFORE, verbatim: "Gleich.", levelText: "Nur meins" };

    const rebased = rebase(FIELDS, BEFORE, draft, { ...BEFORE, verbatim: "Gleich." });

    expect(rebased).toEqual({ draft, clashes: [], taken: [] });
  });

  it("compares as the server stores: a list as a set, a blank text as none", () => {
    const before = { ...BEFORE, addressees: [LEARNER, EDUCATOR] };
    const stored = { ...before, addressees: [EDUCATOR, LEARNER], levelText: "  " };

    expect(rebase(FIELDS, before, { ...before, verbatim: "Neu." }, stored)).toMatchObject({ clashes: [], taken: [] });
  });

  it("puts a list both changed differently before the user, and takes in one only the other changed", () => {
    const mine = rebase(FIELDS, BEFORE, { ...BEFORE, addressees: [] }, { ...BEFORE, addressees: [LEARNER, EDUCATOR] });
    const theirs = rebase(FIELDS, BEFORE, BEFORE, { ...BEFORE, addressees: [EDUCATOR] });

    expect(mine.clashes).toEqual([{ key: "addressees", yours: [], stored: [LEARNER, EDUCATOR] }]);
    expect(theirs.draft.addressees).toEqual([EDUCATOR]);
    expect(theirs.taken).toEqual(["addressees"]);
  });

  it("names clashes and fields taken in the order of the form, and leaves the user's draft as it was", () => {
    const draft = { ...BEFORE, levelText: "Mein", verbatim: "Mein Satz." };
    const kept = structuredClone(draft);

    const rebased = rebase(FIELDS, BEFORE, draft, {
      ...BEFORE,
      levelText: "Ihr",
      verbatim: "Ihr Satz.",
      statement_kind: "",
    });

    expect(rebased.clashes.map((clash) => clash.key)).toEqual(["verbatim", "levelText"]);
    expect(rebased.taken).toEqual(["statement_kind"]);
    expect(draft).toEqual(kept);
  });
});
