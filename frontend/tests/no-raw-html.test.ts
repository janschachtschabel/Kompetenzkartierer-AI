import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { ANCHORS, scanned, sourceFiles } from "./sources";

/**
 * Text extracted from uploaded documents is attacker-influenced content: whoever
 * uploads a PDF controls what ends up in a curriculum, quotes and all. It is safe
 * because nothing renders it as markup. This pins that: a renderer that needs raw
 * HTML has to be one that escapes it, and this test is where that decision surfaces.
 */
const FORBIDDEN = [
  /\bv-html\b/,
  // bound (:innerHTML, v-bind:innerHTML), set, or handed to a render function
  /\binnerHTML\b/,
  /\bouterHTML\b/,
  /\binsertAdjacentHTML\b/,
  /\bdocument\.write\b/,
  /\bdangerouslySetInnerHTML\b/,
];

describe("raw HTML rendering", () => {
  it("is used nowhere in the SPA", () => {
    const files = sourceFiles();
    scanned(files, ...ANCHORS);

    const offenders = files.filter((path) => {
      const source = readFileSync(path, "utf8");
      return FORBIDDEN.some((pattern) => pattern.test(source));
    });

    expect(offenders).toEqual([]);
  });

  it("recognises what it forbids", () => {
    expect(FORBIDDEN.some((pattern) => pattern.test('<div v-html="text" />'))).toBe(true);
    expect(FORBIDDEN.some((pattern) => pattern.test("node.innerHTML = text;"))).toBe(true);
  });
});


describe("raw HTML in its other forms", () => {
  it.each([
    '<div :innerHTML="text" />',
    '<div v-bind:innerHTML="text" />',
    'h("div", { innerHTML: text })',
    'node.insertAdjacentHTML("beforeend", text)',
    "node.outerHTML = text;",
    "document.write(text)",
  ])("is recognised: %s", (source) => {
    expect(FORBIDDEN.some((pattern) => pattern.test(source))).toBe(true);
  });
});
