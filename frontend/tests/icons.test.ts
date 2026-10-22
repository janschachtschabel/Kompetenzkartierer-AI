import { readFileSync } from "node:fs";
import { join } from "node:path";

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import AppIcon from "@/components/AppIcon.vue";

import { SRC, scanned, sourceFiles } from "./sources";

/**
 * Icons are drawn, in one file, at one weight - not emoji, whose glyph, stroke
 * and spoken name belong to whoever made the operating system's font.
 */
const ICONS = readFileSync(join(SRC, "icons.ts"), "utf8");
/* The component, for the one attribute that decides every glyph's weight. */
const ICON = readFileSync(join(SRC, "components", "AppIcon.vue"), "utf8");
const components = sourceFiles(SRC, /\.vue$/);

/**
 * Every icon name the app asks for, and where. Three patterns: a literal on the
 * tag, a name chosen between two by a binding, and an `icon:` field of a table
 * (the rail's destinations). Not "any quoted string that matches a glyph name":
 * route names collide with icon names. A fourth pattern shows up here as an
 * unused glyph rather than as silence.
 */
function iconUses(): { path: string; name: string }[] {
  return sourceFiles(SRC).flatMap((path) => {
    const source = readFileSync(path, "utf8");
    const literal = [...source.matchAll(/<AppIcon\b[^>]*\sname="([\w-]+)"/g)].map(([, name]) => name);
    const bound = [...source.matchAll(/<AppIcon\b[^>]*\s:name="([^"]*)"/g)].flatMap(([, expr]) =>
      [...expr.matchAll(/'([\w-]+)'/g)].map(([, name]) => name),
    );
    const table = [...source.matchAll(/\bicon:\s*"([\w-]+)"/g)].map(([, name]) => name);
    return [...literal, ...bound, ...table].map((name) => ({ path, name }));
  });
}

function templateOf(source: string): string {
  return source.split("<template>")[1]?.split("</template>")[0] ?? "";
}

/** The names the app can actually draw, read out of the glyph table itself. */
function drawnNames(): string[] {
  const glyphs = /const GLYPHS[^{]*\{([\s\S]*?)\n\};/.exec(ICONS);
  expect(glyphs, "icons.ts declares its glyph table").not.toBeNull();
  // Quoted or not: a name with a hyphen has to be quoted to be a valid key.
  return [...(glyphs?.[1] ?? "").matchAll(/^ {2}"?([a-z][\w-]*)"?:/gm)].map(([, name]) => name);
}

it("scans the component sources", () => {
  scanned(components, "App.vue", "ErrorState.vue");
});

describe("iconography", () => {
  it("never lets a stand-in glyph do an icon's job", () => {
    // Not only emoji: arrows, the warning sign and the Geometric Shapes did icon
    // work in the old app, and an entity renders the same while hiding from a scan.
    const glyph = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{25A0}-\u{25FF}]/u;
    const entity = /&(?:[lr]arr|[lr]Arr|#8(?:59[0-3]|6[0-9]{2}));/;

    const offenders = components.filter((path) => {
      const template = templateOf(readFileSync(path, "utf8"));
      return glyph.test(template) || entity.test(template);
    });

    expect(offenders).toEqual([]);
  });

  it("reads the names the app asks for, in all three ways it asks", () => {
    const sample = [
      '<AppIcon name="warning" />',
      "<AppIcon :name=\"open ? 'close' : 'menu'\" />",
      '{ name: "start", icon: "map" }',
    ].join("\n");
    const found = [
      ...[...sample.matchAll(/<AppIcon\b[^>]*\sname="([\w-]+)"/g)].map(([, name]) => name),
      ...[...sample.matchAll(/<AppIcon\b[^>]*\s:name="([^"]*)"/g)].flatMap(([, expr]) =>
        [...expr.matchAll(/'([\w-]+)'/g)].map(([, name]) => name),
      ),
      ...[...sample.matchAll(/\bicon:\s*"([\w-]+)"/g)].map(([, name]) => name),
    ];
    expect(found).toEqual(["warning", "close", "menu", "map"]);
  });

  it("draws every name the app asks for", () => {
    const drawn = new Set(drawnNames());
    const asked = iconUses();
    expect(asked.length, "the app uses icons").toBeGreaterThan(0);

    expect(asked.filter(({ name }) => !drawn.has(name))).toEqual([]);
  });

  it("draws nothing it is never asked for", () => {
    // A glyph table is where dead shapes accumulate: nobody deletes an icon,
    // because nobody can tell whether it is still in use.
    const used = new Set(iconUses().map(({ name }) => name));

    expect(drawnNames().filter((name) => !used.has(name))).toEqual([]);
  });

  it("draws them all at one weight", () => {
    expect(ICON).toContain('stroke-width="1.5"');
    expect([...ICON.matchAll(/stroke-width="([^"]+)"/g)].map(([, w]) => w)).toEqual(["1.5"]);
  });
});

describe("an icon on its own", () => {
  it("is hidden from assistive technology, because the control it sits in is named", () => {
    const svg = mount(AppIcon, { props: { name: "warning" } }).get("svg");

    expect(svg.attributes("aria-hidden")).toBe("true");
    // Without this, some engines put the SVG in the tab order as a stop of its own.
    expect(svg.attributes("focusable")).toBe("false");
  });

  it("takes its colour and its size from the text around it", () => {
    const svg = mount(AppIcon, { props: { name: "warning" } }).get("svg");

    expect(svg.attributes("stroke")).toBe("currentColor");
    expect(svg.attributes("width")).toBe("1em");
  });
});
