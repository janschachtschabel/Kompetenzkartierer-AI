import { readFileSync } from "node:fs";

import { expect, it } from "vitest";

import { TESTS, scanned, sourceFiles } from "./sources";

// Put together so that this file does not match itself.
const SLEEP = new RegExp(["new Promise\\(\\(\\w+\\) => ", "setTimeout\\("].join(""));

/**
 * A test waits on the work, not on the clock. In the old app real sleeps of 20 to
 * 60 ms stood in for `flushPromises` in fifteen files: slow, and a race with a
 * loaded machine. A test that needs a slow answer holds it back with a promise of
 * its own and lets it go.
 */
it("waits on the work, not on the clock", () => {
  // The guard sees the pattern it guards against, in both spellings in use.
  expect(SLEEP.test("await new Promise((r) => " + "setTimeout(r, 50));")).toBe(true);
  expect(SLEEP.test("await new Promise((resolve) => " + "setTimeout(resolve, 20));")).toBe(true);

  const files = sourceFiles(TESTS, /\.ts$/);
  scanned(files, "no-clock-waits.test.ts", "contrast.test.ts");

  expect(files.filter((path) => SLEEP.test(readFileSync(path, "utf8")))).toEqual([]);
});
