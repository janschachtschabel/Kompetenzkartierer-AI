import { describe, expect, it } from "vitest";

import { isolate } from "@/bidi";

// Written as code points: an editor turns the escapes into the invisible signs themselves.
const FIRST_STRONG_ISOLATE = String.fromCodePoint(0x2068);
const POP_DIRECTIONAL_ISOLATE = String.fromCodePoint(0x2069);

describe("a reader's text inside a sentence of the page", () => {
  it("is set apart, so its direction does not turn the sentence around it", () => {
    expect(isolate("منهج")).toBe(`${FIRST_STRONG_ISOLATE}منهج${POP_DIRECTIONAL_ISOLATE}`);
  });

  it("is set apart however it begins, a left-to-right title too", () => {
    expect(isolate("Lehrplan")).toBe(`${FIRST_STRONG_ISOLATE}Lehrplan${POP_DIRECTIONAL_ISOLATE}`);
  });
});
