/**
 * Every link that opens a new tab hands the opener to the page it opens unless it
 * says rel="noopener". In the old app three components had forgotten it and one
 * remembered: a rule that holds in one place is a rule that drifts.
 */
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { SRC, VUE_ANCHORS, scanned, sourceFiles } from "./sources";

/** The `<a target="_blank">` tags in `template` that lack rel="noopener noreferrer". */
function unguarded(template: string): string[] {
  return (template.match(/<a\b[^>]*>/gs) ?? [])
    .filter((tag) => tag.includes('target="_blank"') && !tag.includes('rel="noopener noreferrer"'))
    .map((tag) => tag.replace(/\s+/g, " "));
}

describe("links that open a new tab", () => {
  it("recognises one without the guard", () => {
    expect(unguarded('<a href="https://example.org" target="_blank">x</a>')).toHaveLength(1);
    expect(unguarded('<a href="https://example.org" target="_blank" rel="noopener noreferrer">x</a>')).toEqual([]);
  });

  it("all carry rel=noopener noreferrer", () => {
    const files = sourceFiles(SRC, /\.vue$/);
    scanned(files, ...VUE_ANCHORS);

    const offenders = files.flatMap((file) => unguarded(readFileSync(file, "utf8")).map((tag) => `${file}: ${tag}`));

    expect(offenders).toEqual([]);
  });
});
