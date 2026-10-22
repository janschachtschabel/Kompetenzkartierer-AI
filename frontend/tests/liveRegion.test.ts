/**
 * What a live region is to hold next so that it is read out: a message the
 * same as the one it holds would leave the region unchanged, and a screen
 * reader would say nothing (recheck R3-1). Emptying it first in the same task
 * did not help either -- the browser updates what it reports between tasks.
 */
import { describe, expect, it } from "vitest";

import { sayAnew } from "@/liveRegion";

const NBSP = " ";

describe("sayAnew", () => {
  it("says a new message as it is", () => {
    expect(sayAnew("", "Gespeichert.")).toBe("Gespeichert.");
    expect(sayAnew("Gespeichert.", "Verschoben.")).toBe("Verschoben.");
  });

  it("says the same message again with a space the eye does not see, and without it the third time", () => {
    const second = sayAnew("Entfernt.", "Entfernt.");
    expect(second).toBe(`Entfernt.${NBSP}`);
    expect(second.trim()).toBe("Entfernt.");
    expect(sayAnew(second, "Entfernt.")).toBe("Entfernt.");
  });

  it("empties the region on an empty message", () => {
    expect(sayAnew(`Entfernt.${NBSP}`, "")).toBe("");
  });
});
