import { readFileSync } from "node:fs";

import { expect, it } from "vitest";

import { TESTS, scanned, sourceFiles } from "./sources";

// Put together so that this file does not match itself: the promise's type or none,
// any parameters in brackets or one bare, an arrow or a function, a body or a block -
// up to the timer, before the statement ends.
const SLEEP = new RegExp(
  [
    "new Promise\\s*(?:<(?:[^<>]|<[^<>]*>)*>)?\\(\\s*(?:async\\s+)?(?:\\([^)]*\\)|\\w+|function\\s*\\([^)]*\\))",
    "\\s*(?:=>)?\\s*(?:\\{[^}]*?|[^;}]*?)\\b(?:\\w+\\.)?",
    "setTimeout\\(",
  ].join(""),
);
/** The other ways to a sleep: Node's promised timers, the timer promisified. */
const OTHER_SLEEPS = [
  new RegExp(["timers", "\\/promises"].join("")),
  new RegExp(["promisify\\(\\s*(?:\\w+\\.)?", "setTimeout\\b"].join("")),
];

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
  expect(files.filter((path) => OTHER_SLEEPS.some((pattern) => pattern.test(readFileSync(path, "utf8"))))).toEqual([]);
});

it.each([
  'import { setTimeout as sleep } from "node:' + ["timers", "promises"].join("/") + '";',
  "const sleep = " + ["promisify(", "set", "Timeout);"].join(""),
])("recognises a sleep made of the timer otherwise: %s", (source) => {
  expect(OTHER_SLEEPS.some((pattern) => pattern.test(source))).toBe(true);
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
  // a block with a statement before the timer
  "await new Promise((resolve) => {\n  const later = 20;\n  WAIT(resolve, later);\n});",
  // a type with a type inside
  "await new Promise<Map<string, number>>((r) => WAIT(r, 5));",
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
