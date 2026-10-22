import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { scanned, sourceFiles } from "./sources";

/**
 * Text extracted from uploaded documents is attacker-influenced content: whoever
 * uploads a PDF controls what ends up in a curriculum, quotes and all. It is safe
 * because nothing renders it as markup. This pins that: a renderer that needs raw
 * HTML has to be one that escapes it, and this test is where that decision surfaces.
 */
const FORBIDDEN = [/\bv-html\b/, /\.innerHTML\s*=/, /\bdangerouslySetInnerHTML\b/];

describe("raw HTML rendering", () => {
  it("is used nowhere in the SPA", () => {
    const files = sourceFiles();
    scanned(files, "App.vue", "main.ts");

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
