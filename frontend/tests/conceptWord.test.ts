import { describe, expect, it } from "vitest";

import { conceptWord } from "@/registerWords";

const WORDS = { exact: "wörtlich gefunden" };
const PREFIX = "https://w3id.org/wlo/curriculum/vocab#match_";

describe("a concept in words", () => {
  it("is the word for its notation after the scheme's prefix, else its IRI as it is", () => {
    expect(conceptWord(WORDS, PREFIX, `${PREFIX}exact`)).toBe("wörtlich gefunden");
    expect(conceptWord(WORDS, PREFIX, `${PREFIX}other`)).toBe(`${PREFIX}other`);
    expect(conceptWord(WORDS, PREFIX, "https://example.org/exact")).toBe("https://example.org/exact");
    expect(conceptWord(WORDS, PREFIX, `${PREFIX}toString`)).toBe(`${PREFIX}toString`); // no inherited key
  });
});
