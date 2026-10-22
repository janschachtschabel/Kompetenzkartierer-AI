import { readFileSync } from "node:fs";
import { basename, join } from "node:path";

import { describe, expect, it } from "vitest";

import { SRC, VUE_ANCHORS, scanned, sourceFiles } from "./sources";

/**
 * Every page sits in the one frame, and every button is drawn by the shared
 * rules. In the old app both drifted: pages with widths of their own shifted the
 * layout between two menu entries, three sizes of `.btn-sm` lived in three
 * components, and element rules restyled every button in one.
 */
const components = sourceFiles(SRC, /\.vue$/);
/** The pages drawn in the frame; the sign-in is a centred card, not a framed page. */
const FRAMED = ["StartView.vue"];

function stylesOf(source: string): string {
  return [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(([, css]) => css).join("\n");
}

/** The classes on the root element of a component's template. */
function rootClasses(source: string): string[] {
  const template = source.split("<template>")[1] ?? "";
  const root = /<([a-zA-Z][\w-]*)\b([^>]*)>/.exec(template);
  return /\sclass="([^"]*)"/.exec(root?.[2] ?? "")?.[1].split(/\s+/).filter(Boolean) ?? [];
}

/** Rules that give one of `classes` - the root itself, not what is inside it - a width or margin of its own. */
function frameOverrides(source: string, classes: string[]): string[] {
  const own = classes.filter((name) => name !== "page");
  return [...stylesOf(source).matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => own.some((name) => new RegExp(`^\\s*\\.${name}\\s*$`).test(selector)))
    .filter(([, , body]) => /(?:^|;)\s*(?:max-|min-)?(?:width|inline-size)\s*:|(?:^|;)\s*margin(?:-inline)?\s*:/.test(body))
    .map(([, selector]) => selector.trim());
}

it("scans the components", () => {
  scanned(components, ...VUE_ANCHORS, ...FRAMED);
});

describe("a framed page", () => {
  it("recognises a page that narrows or moves its own frame", () => {
    const sample = '<template><div class="page start"></div></template>\n<style>\n.start {\n  max-width: 54rem;\n}\n</style>';
    expect(rootClasses(sample)).toEqual(["page", "start"]);
    expect(frameOverrides(sample, rootClasses(sample))).toEqual([".start"]);
    expect(frameOverrides("<style>\n.start p {\n  max-width: 54rem;\n}\n</style>", ["page", "start"])).toEqual([]);
  });

  it.each(FRAMED)("%s sits in the shared frame and keeps it", (name) => {
    const path = components.find((file) => basename(file) === name) ?? "";
    const source = readFileSync(path, "utf8");

    expect(rootClasses(source)).toContain("page");
    expect(frameOverrides(source, rootClasses(source))).toEqual([]);
  });
});

describe("buttons", () => {
  it("take their small size from style.css alone", () => {
    expect(readFileSync(join(SRC, "style.css"), "utf8")).toMatch(/^\.btn-sm \{/m);
    const offenders = components.filter((path) => /^\s*\.btn-sm\b[^{]*\{/m.test(stylesOf(readFileSync(path, "utf8"))));

    expect(offenders).toEqual([]);
  });

  it("drawn as a link keep the link's underline and the line's height (WCAG 1.4.1)", () => {
    // `.btn` takes the underline away and sets a button's height; a link-styled
    // one in running text would be told apart by colour alone, in a box of its own
    const rule = /^\.btn\.link \{([^}]*)\}/m.exec(readFileSync(join(SRC, "style.css"), "utf8"))?.[1] ?? "";

    expect(rule).toMatch(/text-decoration:\s*underline/);
    expect(rule).toMatch(/min-height:\s*auto/);
  });

  it("are not restyled all at once by a component", () => {
    // a component's own buttons get a class; an element rule reaches every button it renders
    expect(/^\s*button\s*\{/m.test(stylesOf("<style>\nbutton {\n  color: red;\n}\n</style>"))).toBe(true);
    const offenders = components.filter((path) => /^\s*button\s*\{/m.test(stylesOf(readFileSync(path, "utf8"))));

    expect(offenders).toEqual([]);
  });
});
