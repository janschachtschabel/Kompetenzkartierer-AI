import { readFileSync } from "node:fs";
import { basename, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { SRC, VUE_ANCHORS, cssRules, scanned, sourceFiles, stylesOf } from "./sources";

/**
 * Every page sits in the one frame, and every button is drawn by the shared
 * rules. In the old app both drifted: pages with widths of their own shifted the
 * layout between two menu entries, three sizes of `.btn-sm` lived in three
 * components, and element rules restyled every button in one.
 */
const components = sourceFiles(SRC, /\.vue$/);
/** The sign-in is a centred card, not a framed page; every other view is framed. */
const UNFRAMED = ["LoginView.vue"];
const framed = components.filter((path) => path.includes(`${sep}views${sep}`) && !UNFRAMED.includes(basename(path)));

/** The classes on the root element of a component's template. */
function rootClasses(source: string): string[] {
  const template = source.split("<template>")[1] ?? "";
  const root = /<([a-zA-Z][\w-]*)\b([^>]*)>/.exec(template);
  return /\sclass="([^"]*)"/.exec(root?.[2] ?? "")?.[1].split(/\s+/).filter(Boolean) ?? [];
}

/** A selector for one element itself - `.page.start`, `div.start:hover` - not for something inside it. */
const COMPOUND = /^[a-z]*(?:\.[\w-]+|:[\w-]+(?:\([^)]*\))?)+$/i;

/** Selectors that give the root itself - one of `classes`, the shared `page` too - a width or margin of its own. */
function frameOverrides(source: string, classes: string[]): string[] {
  return cssRules(stylesOf(source))
    .filter(({ body }) => /(?:^|;)\s*(?:max-|min-)?(?:width|inline-size)\s*:|(?:^|;)\s*margin(?:-inline)?\s*:/.test(body))
    .flatMap(({ selectors }) =>
      selectors.filter(
        (selector) =>
          COMPOUND.test(selector) && [...selector.matchAll(/\.([\w-]+)/g)].some(([, name]) => classes.includes(name)),
      ),
    );
}

/** Selectors that reach `pattern` anywhere in them: `.toolbar .btn-sm`, `button:hover`. */
function selectorsReaching(source: string, pattern: RegExp): string[] {
  return cssRules(stylesOf(source)).flatMap(({ selectors }) => selectors.filter((selector) => pattern.test(selector)));
}

/** `.btn-sm`, as a class anywhere in a selector. */
const SMALL_BUTTON = /\.btn-sm(?![\w-])/;
/** `button`, as an element anywhere in a selector - not `.button-row` or `[type=button]`. */
const BUTTON_ELEMENT = /(?:^|[\s>+~(])button(?![\w-])/;

it("scans the components and the framed pages", () => {
  scanned(components, ...VUE_ANCHORS);
  scanned(framed, "StartView.vue");
});

describe("a framed page", () => {
  it("recognises a page that narrows or moves its own frame, in every way it is written", () => {
    const page = '<template><div class="page start"></div></template>\n';
    const styled = (css: string) => `${page}<style>\n${css}\n</style>`;
    const classes = rootClasses(page);

    expect(classes).toEqual(["page", "start"]);
    expect(frameOverrides(styled(".start {\n  max-width: 54rem;\n}"), classes)).toEqual([".start"]);
    // the narrowing of round 1, word for word: a token passes the token guard
    expect(frameOverrides(styled(".page.start {\n  max-width: var(--reading-width);\n}"), classes)).toEqual([".page.start"]);
    // a comment before the rule is no part of its selector
    expect(frameOverrides(styled("/* the reading width */\n.start {\n  max-width: 54rem;\n}"), classes)).toEqual([".start"]);
    expect(frameOverrides(styled(".page {\n  margin: 0;\n}"), classes)).toEqual([".page"]);
    expect(frameOverrides(styled("div.start, .other {\n  width: 50%;\n}"), classes)).toEqual(["div.start"]);
    // what sits inside the page is its own business
    expect(frameOverrides(styled(".start p {\n  max-width: 54rem;\n}"), classes)).toEqual([]);
  });

  it.each(framed.map((path) => [basename(path), path]))("%s sits in the shared frame and keeps it", (_name, path) => {
    const source = readFileSync(path, "utf8");

    expect(rootClasses(source)).toContain("page");
    expect(frameOverrides(source, rootClasses(source))).toEqual([]);
  });
});

describe("buttons", () => {
  it("are recognised as restyled wherever a selector reaches them", () => {
    const styled = (css: string) => `<style>\n${css} {\n  color: red;\n}\n</style>`;
    for (const selector of [".btn-sm", ".btn.btn-sm", ".toolbar .btn-sm", "button.btn-sm"]) {
      expect(selectorsReaching(styled(selector), SMALL_BUTTON), selector).toHaveLength(1);
    }
    for (const selector of ["button", "button:hover", ".toolbar button", "button, a", "li > button"]) {
      expect(selectorsReaching(styled(selector), BUTTON_ELEMENT), selector).toHaveLength(1);
    }
    for (const selector of [".button-row", "[type=button]", ".btn-small"]) {
      const reached = [...selectorsReaching(styled(selector), SMALL_BUTTON), ...selectorsReaching(styled(selector), BUTTON_ELEMENT)];
      expect(reached, selector).toEqual([]);
    }
  });

  it("take their small size from style.css alone", () => {
    expect(cssRules(readFileSync(`${SRC}${sep}style.css`, "utf8")).some(({ selectors }) => selectors.includes(".btn-sm"))).toBe(true);
    const offenders = components.flatMap((path) =>
      selectorsReaching(readFileSync(path, "utf8"), SMALL_BUTTON).map((selector) => `${path}: ${selector}`),
    );

    expect(offenders).toEqual([]);
  });

  it("are not restyled all at once by a component", () => {
    // a component's own buttons get a class; an element rule reaches every button it renders
    const offenders = components.flatMap((path) =>
      selectorsReaching(readFileSync(path, "utf8"), BUTTON_ELEMENT).map((selector) => `${path}: ${selector}`),
    );

    expect(offenders).toEqual([]);
  });
});
