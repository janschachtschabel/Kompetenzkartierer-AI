import { readFileSync } from "node:fs";

import { expect, it } from "vitest";

import { TESTS, scanned, sourceFiles } from "./sources";

// Put together so that this file does not match itself: the promise's type or none,
// any parameters in brackets or one bare, an arrow or a function, a body or a block -
// up to the timer, before the statement ends.
const SLEEP = new RegExp(
  [
    "new Promise\\s*(?:<[^>]*>)?\\(\\s*(?:async\\s+)?(?:\\([^)]*\\)|\\w+|function\\s*\\([^)]*\\))",
    "\\s*(?:=>)?\\s*\\{?[^;}]*?\\b(?:\\w+\\.)?",
    "setTimeout\\(",
  ].join(""),
);
/** Node's promised timers: a sleep in one word. */
const PROMISED_TIMERS = new RegExp(["timers", "\\/promises"].join(""));

/** The timer the cases below write; split, so that this file holds none. */
const TIMER = ["set", "Timeout("].join("");
const spelt = (source: string) => source.replaceAll("WAIT(", TIMER);

/**
 * A test waits on the work, not on the clock. In the old app real sleeps of 20 to
 * 60 ms stood in for `flushPromises` in fifteen files: slow, and a race with a
 * loaded machine. A test that needs a slow answer holds it back with a promise of
 * its own and lets it go.
 */
it("waits on the work, not on the clock", () => {
  // The guard sees the pattern it guards against, in both spellings in use.
  expect(SLEEP.test(spelt("await new Promise((r) => WAIT(r, 50));"))).toBe(true);
  expect(SLEEP.test(spelt("await new Promise((resolve) => WAIT(resolve, 20));"))).toBe(true);

  const files = sourceFiles(TESTS, /\.ts$/);
  scanned(files, "no-clock-waits.test.ts", "contrast.test.ts");

  expect(files.filter((path) => SLEEP.test(readFileSync(path, "utf8")))).toEqual([]);
  expect(files.filter((path) => PROMISED_TIMERS.test(readFileSync(path, "utf8")))).toEqual([]);
});

it("recognises the promised timers imported", () => {
  const imported = 'import { setTimeout as sleep } from "node:' + ["timers", "promises"].join("/") + '";';

  expect(PROMISED_TIMERS.test(imported)).toBe(true);
});


it.each([
  "await new Promise(r => WAIT(r, 50));",
  "await new Promise((resolve) => {\n  WAIT(resolve, 20);\n});",
  "await new Promise( ( done ) =>\n  WAIT(done, 5));",
  // TypeScript's usual spelling, with the promise's type
  "await new Promise<void>((r) => WAIT(r, 50));",
  "await new Promise((resolve, reject) => WAIT(resolve, 50));",
  "await new Promise((r: () => void) => WAIT(r, 50));",
  "await new Promise((r) => window.WAIT(r, 50));",
  "await new Promise((r) => void WAIT(r, 50));",
  "await new Promise(function (r) { WAIT(r, 50); });",
])("recognises a sleep however it is spelt: %s", (source) => {
  expect(SLEEP.test(spelt(source))).toBe(true);
});

it.each([
  // a held-back answer, the way this suite waits
  "vi.mocked(api.getMe).mockReturnValue(new Promise((resolve) => (answer = resolve)));",
  "const never = new Promise(() => undefined);",
])("leaves a promise that is no sleep alone: %s", (source) => {
  expect(SLEEP.test(spelt(source))).toBe(false);
});
