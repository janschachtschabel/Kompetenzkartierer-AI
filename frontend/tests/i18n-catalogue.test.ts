import { readFileSync } from "node:fs";
import { sep } from "node:path";

import { describe, expect, it } from "vitest";

import { messages, translate } from "@/i18n/de";

import { ANCHORS, scanned, sourceFiles } from "./sources";

/** Every source file except the catalogue itself. */
const files = sourceFiles().filter((path) => !path.endsWith(`i18n${sep}de.ts`));

function keysOf(node: object, path = ""): string[] {
  return Object.entries(node).flatMap(([name, value]) => {
    const key = path ? `${path}.${name}` : name;
    return value && typeof value === "object" ? keysOf(value as object, key) : [key];
  });
}

function textsOf(node: object): string[] {
  return Object.values(node).flatMap((value) =>
    value && typeof value === "object" ? textsOf(value as object) : [String(value)],
  );
}

const code = files.map((path) => readFileSync(path, "utf8")).join("\n");

/** The catalogue holds what the pages say, and says it one way. */
describe("the message catalogue", () => {
  const quoted = new Set([...code.matchAll(/["'`]([A-Za-z_][\w.]*)["'`]/g)].map((m) => m[1]));
  // A whole group is in use where the code builds its keys: t(`group.${x}`),
  // messages.group[x]. Only a path with a dot counts as a group - a group's bare
  // name is often also a route's.
  const groups = new Set([
    ...[...code.matchAll(/`([A-Za-z_][\w.]*)\.\$\{/g)].map((m) => m[1]),
    ...[...code.matchAll(/messages\.([A-Za-z_][\w.]*?)(?=\[|\s+as\b|[),;\s])/g)].map((m) => m[1]),
    ...[...quoted].filter((literal) => literal.includes(".")),
  ]);

  it("reads the components and a catalogue that holds something", () => {
    scanned(files, ...ANCHORS);
    expect(keysOf(messages).length).toBeGreaterThan(0);
  });

  it("has no message that nothing shows", () => {
    // Wording nobody reads, and a translation nobody would need. A key used only
    // by a test counts as unused: the test checks a page, not the catalogue.
    const unused = keysOf(messages).filter((key) => {
      if (quoted.has(key) || code.includes(`messages.${key}`)) return false;
      const parts = key.split(".");
      for (let i = parts.length - 1; i > 0; i -= 1) {
        if (groups.has(parts.slice(0, i).join("."))) return false;
      }
      return true;
    });

    expect(unused).toEqual([]);
  });

  it("addresses the reader as du throughout", () => {
    // A capital "Sie" that begins a sentence is "they" and stays; a word right
    // before it, or a formal possessive, is the formal address.
    const formal = textsOf(messages).filter((text) =>
      /[A-Za-zÄÖÜäöüß]+ Sie\b|\bIhr(?:e|en|em|er|es)?\b|\bIhnen\b/.test(text),
    );

    expect(formal).toEqual([]);
  });
});


/**
 * Every literal that reads as a key - one of the catalogue's groups, a dot, a
 * name - whether handed to t() or kept as data for it: a page's title in the
 * router, a destination's label in the navigation.
 */
function keysNamedIn(source: string): string[] {
  const groups = Object.keys(messages).join("|");
  const literal = new RegExp(`["'\`]((?:${groups})\\.[\\w.]+)["'\`]`, "g");
  return [...source.matchAll(literal)].map(([, key]) => key);
}

/** Every key the code asks for: what it hands to t(), whatever the group, and what it keeps as data. */
function keysAskedIn(source: string): string[] {
  const handed = [...source.matchAll(/\bt\(\s*["'`]([\w.]+)["'`]/g)].map(([, key]) => key);
  return [...new Set([...handed, ...keysNamedIn(source)])];
}

describe("a key the code asks for", () => {
  it("is found as data too, and only where it reads as a key", () => {
    expect(keysNamedIn('{ name: "start", meta: { title: "app.titles.missing" } }')).toEqual(["app.titles.missing"]);
    expect(keysNamedIn('label: "app.nav.start", icon: "map"')).toEqual(["app.nav.start"]);
    expect(keysNamedIn('const route = "start"; const file = "notes.start.md"')).toEqual([]);
  });

  it("is found in t() whatever its group, a new or a misspelt one too", () => {
    // the groups above are only those the catalogue has; t() names any
    expect(keysAskedIn('{{ t("curricula.title") }}')).toEqual(["curricula.title"]);
    expect(keysAskedIn('t("strat.heading") + t("start.welcome")')).toEqual(["strat.heading", "start.welcome"]);
    expect(keysAskedIn('{ label: "app.nav.start" }')).toEqual(["app.nav.start"]);
  });

  it("is in the catalogue: a typo shows the raw key on the one path nobody looked at", () => {
    const asked = keysAskedIn(code);
    expect(asked.length, "the code asks for keys").toBeGreaterThan(10);
    expect(asked, "the keys kept as data were read").toEqual(expect.arrayContaining(["app.nav.start", "app.titles.login"]));

    expect(asked.filter((key) => translate(messages, key) === key)).toEqual([]);
  });
});
