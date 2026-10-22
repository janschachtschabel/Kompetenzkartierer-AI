import { readFileSync } from "node:fs";
import { relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { SRC, scanned, sourceFiles } from "./sources";

/**
 * Guard against user-facing text that never reaches the catalogue.
 *
 * A missing key is loud - t() returns the key itself, and the screen shows
 * "login.submit". A string that never asked for a key is silent: it renders, in
 * whatever language it was typed in, and stays. This makes the silent case loud.
 *
 * The scan looks at the four places text escaped in the old app:
 *   1. bare text between tags
 *   2. a static placeholder / aria-label / title / alt
 *   3. string literals inside {{ }} and inside those same bound attributes
 *   4. string literals handed to alert() or confirm()
 *
 * What it cannot see, and a reviewer still has to: a literal a script assigns
 * to a ref that the template renders later. Telling those from the many strings
 * that are no text (ids, routes, classes) needs a language detector, and a guard
 * with false positives gets switched off.
 */
const WORD = /\p{L}{2,}/u; // two letters in a row: a word, not "×", "%" or ":"

/** The attributes whose value a user reads or a screen reader speaks. */
const TEXT_ATTR = "placeholder|aria-label|title|alt";

/** Blank a match out, keeping every offset and line break where it was. */
const blank = (text: string) => text.replace(/[^\n]/g, " ");

const at = (match: RegExpMatchArray) => match.index ?? 0;

interface Hit {
  index: number;
  text: string;
}

function scan(source: string, isComponent: boolean): Hit[] {
  const hits: Hit[] = [];

  const push = (index: number, text: string) => {
    const trimmed = text.trim();
    if (WORD.test(trimmed)) hits.push({ index, text: trimmed });
  };

  const pushLiterals = (fragment: string, base: number) => {
    for (const literal of fragment.matchAll(/(["'`])([\s\S]*?)\1/g)) push(base + at(literal), literal[2]);
  };

  // Comments, HTML entities and the i18n keys themselves carry no wording.
  const code = source
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/&[a-zA-Z]+;/g, blank)
    .replace(/\bt\(\s*(["'`])[^"'`]*\1/g, (match) => `t(${blank(match.slice(2))}`);

  // Rule 4 - the only rule that also applies to plain .ts modules.
  for (const call of code.matchAll(/\b(?:alert|confirm)\(([^)]*)\)/g)) {
    pushLiterals(call[1], at(call) + call[0].indexOf("(") + 1);
  }
  if (!isComponent) return hits;

  const template = code.replace(/<script[\s\S]*?<\/script>/g, blank).replace(/<style[\s\S]*?<\/style>/g, blank);

  // Rules 2 and 3 - the attributes a user reads, written out or bound.
  for (const attr of template.matchAll(new RegExp(`\\s(:?)(?:${TEXT_ATTR})="([^"]*)"`, "g"))) {
    const base = at(attr) + attr[0].indexOf('="') + 2;
    if (attr[1] === ":") pushLiterals(attr[2], base);
    else push(base, attr[2]);
  }

  // Rule 3 - literals inside an interpolation, where a fallback likes to hide.
  for (const curly of template.matchAll(/\{\{([\s\S]*?)\}\}/g)) pushLiterals(curly[1], at(curly) + 2);

  // Rule 1 - bare text between tags. Attribute values and interpolations are
  // blanked first, so a ">" inside one cannot pose as the end of a tag.
  const between = template.replace(/="[^"]*"/g, blank).replace(/\{\{[\s\S]*?\}\}/g, blank);
  for (const node of between.matchAll(/>([^<>]+)</g)) push(at(node) + 1, node[1]);

  return hits;
}

/** Every source file except the catalogue - which is where text belongs. */
const files = sourceFiles().filter((path) => !path.includes(`${sep}i18n${sep}`));

const lineAt = (source: string, index: number) => source.slice(0, index).split("\n").length;

describe("user-facing text", () => {
  it("has a scan that actually reads the source files", () => {
    scanned(files, "App.vue", "main.ts");
  });

  it("lives in the catalogue, not in a component", () => {
    const violations = files.flatMap((file) => {
      const source = readFileSync(file, "utf8");
      return scan(source, file.endsWith(".vue")).map(
        (hit) => `${relative(SRC, file)}:${lineAt(source, hit.index)} → ${hit.text}`,
      );
    });

    expect(violations).toEqual([]);
  });

  it("catches a hardcoded string in each of the four places it looks", () => {
    // Regexes over source text: one that matches nothing looks exactly like a
    // codebase that is clean.
    const cases = [
      "<template><p>Hallo Welt</p></template>",
      '<template><input placeholder="Suchbegriff" /></template>',
      "<template><p>{{ value || 'Wird geladen' }}</p></template>",
      '<script setup>alert("Etwas ist schiefgelaufen");</script>',
    ];

    expect(cases.map((source) => scan(source, true).length)).toEqual([1, 1, 1, 1]);
  });

  it("lets a key through, and a text beside it not", () => {
    expect(scan('<template><p>{{ t("login.heading") }}</p></template>', true)).toEqual([]);
    expect(scan('<template><p>{{ t("login.heading") }} Hallo</p></template>', true)).toHaveLength(1);
  });
});
