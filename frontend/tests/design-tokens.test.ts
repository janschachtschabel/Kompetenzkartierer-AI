import { readFileSync } from "node:fs";
import { basename, join } from "node:path";

import { describe, expect, it } from "vitest";

import { ANCHORS, COLOUR_VALUE, SRC, inCatalogue, scanned, sourceFiles, tokenBlocks, withoutComments } from "./sources";

/**
 * The layer below `shared-styles.test.ts`: that one keeps a shared *rule* from
 * being restated in a component, this one keeps a shared *value* from being
 * spelled out as a number.
 *
 * Taken over from the old app, where the numbers had drifted where nobody looks
 * for drift: five page widths at once, so the navigation and the page under it
 * sat 32px apart and moving between two menu entries shifted the page sideways.
 * None of that is visible in a diff; all of it is visible on screen.
 */
const STYLESHEET = readFileSync(join(SRC, "style.css"), "utf8");

it("scans the component sources", () => {
  scanned(sourceFiles(), ...ANCHORS);
});

// A declaration's value: up to `;`, `{` or `}`, over as many lines as do not begin a
// declaration of their own - a gradient or a shadow is often written over three.
const VALUE = String.raw`([^;{}\n]*(?:\n(?![ \t]*[\w-]+[ \t]*:)[^;{}\n]*)*)`;

// A declaration of a property that carries colour - or of a custom property, whose value a
// component would hand on - wherever it starts: a line, after `{` or `;`, and in a bound
// style after `,` or a quote. Shorthands that may hold a colour count too. The value runs
// over its lines until one begins another declaration (VALUE).
const COLOUR_DECLARATION = new RegExp(
  String.raw`(?:^|[{;,'"${"`"}])\s*((?:[\w-]*color|background[\w-]*|border[\w-]*|outline[\w-]*|fill|stroke|box-shadow|text-shadow|text-decoration[\w-]*|filter|column-rule[\w-]*|--[\w-]+)\s*:${VALUE})`,
  "gim",
);
// In a template: a style attribute, and SVG's fill and stroke - written out or bound, in either quotes.
const COLOUR_ATTRIBUTE = /\s(?::|v-bind:)?(?:style|fill|stroke)=(["'])([\s\S]*?)\1/g;

/** A value with its `url(...)` gone: a file's name - `icon-red.svg` - is no colour. */
const colourOf = (value: string) => COLOUR_VALUE.test(value.replace(/url\([^)]*\)/gi, ""));

/** The colour literals in `source`, CSS or template; what a comment says is not drawn. */
function colourLiterals(source: string): string[] {
  const code = withoutComments(source);
  const declared = [...code.matchAll(COLOUR_DECLARATION)]
    .filter(([, , value]) => colourOf(value))
    .map(([, declaration]) => declaration.trim());
  const attributed = [...code.matchAll(COLOUR_ATTRIBUTE)]
    .filter(([, , value]) => colourOf(value))
    .map(([attribute]) => attribute.trim());
  return [...declared, ...attributed];
}

/** Past these a width is a page's: 40rem, as many em, 640px, 80 characters - a dialog's sits on the line. */
const PAGE_WIDTH_ABOVE: Record<string, number> = { rem: 40, em: 40, px: 640, ch: 80 };

/** Widths of a page - fixed or a cap, the length anywhere in min(), clamp() or calc() - which is a token. */
function pageWidths(source: string): string[] {
  return [...source.matchAll(new RegExp(String.raw`(?:^|[\s{;])((?:max-)?(?:width|inline-size)\s*:${VALUE})`, "g"))]
    .filter(([, , value]) =>
      [...value.matchAll(/([\d.]+)(rem|em|px|ch)\b/g)].some(([, length, unit]) => Number(length) > PAGE_WIDTH_ABOVE[unit]),
    )
    .map(([, width]) => width.trim());
}

describe("page width", () => {
  it("is a token, and so is the narrower one prose reads at", () => {
    expect(STYLESHEET).toMatch(/--page-width:/);
    expect(STYLESHEET).toMatch(/--reading-width:/);
  });

  /**
   * 40rem is the line between "how wide is this page" and "how wide is this
   * dialog or this form column". Above it the value is a layout decision the
   * whole app shares; below it, a component's own business.
   */
  it("is never written as a number in a component", () => {
    const offenders = sourceFiles().flatMap((path) =>
      pageWidths(readFileSync(path, "utf8")).map((width) => `${path}: ${width}`),
    );

    expect(offenders).toEqual([]);
  });
});

describe("typeface", () => {
  it("names both families as tokens", () => {
    expect(STYLESHEET).toMatch(/--font:/);
    expect(STYLESHEET).toMatch(/--font-mono:/);
  });

  /** Bare `monospace` is whatever the browser falls back to: Courier New on Windows. */
  it("is never left to the browser's monospace default", () => {
    const offenders = sourceFiles().filter((path) => /font-family:\s*monospace/.test(readFileSync(path, "utf8")));

    expect(offenders).toEqual([]);
  });
});

describe("colour", () => {
  /**
   * A translucent fill layered over a token is a colour nobody verified:
   * `contrast.test.ts` cannot see it, because the colour it fails at is in no
   * token, and jsdom computes no layout for axe to find it either.
   */
  it("recognises the literals it is looking for", () => {
    expect(colourLiterals("  color: #fff;")).toEqual(["color: #fff"]);
    expect(colourLiterals("  border-color: #1a2b3c;")).toEqual(["border-color: #1a2b3c"]);
    expect(colourLiterals("  color: var(--danger, #f08080);")).toHaveLength(1);
    expect(colourLiterals("  background: rgba(0, 0, 0, 0.5);")).toHaveLength(1);
    expect(colourLiterals("  color: var(--text);")).toEqual([]);
  });

  it("is never written as a literal in a component", () => {
    // A colour named in style.css can be checked, changed and themed; one typed
    // into a component can be none of those. The catalogue holds words, not styles.
    const styled = sourceFiles().filter((path) => !inCatalogue(path));
    scanned(styled, ...ANCHORS);
    const offenders = styled.flatMap((path) =>
      colourLiterals(readFileSync(path, "utf8")).map((literal) => `${path}: ${literal}`),
    );

    expect(offenders).toEqual([]);
  });

  it("is never taken from a custom property the stylesheet does not define", () => {
    const defined = new Set([...STYLESHEET.matchAll(/^\s*(--[\w-]+):/gm)].map(([, name]) => name));
    expect(defined.size, "the token block was read").toBeGreaterThan(20);

    const offenders = sourceFiles().flatMap((path) => {
      const source = readFileSync(path, "utf8");
      // A component may define its own, so only names it neither defines nor
      // inherits count. Both forms: a CSS declaration, and the quoted key of a
      // `:style` binding, which is how a component hands a value to its stylesheet.
      const local = new Set([
        ...[...source.matchAll(/^\s*(--[\w-]+):/gm)].map(([, n]) => n),
        ...[...source.matchAll(/['"](--[\w-]+)['"]\s*:/g)].map(([, n]) => n),
      ]);
      return [...source.matchAll(/var\((--[\w-]+)/g)]
        .map(([, name]) => name)
        .filter((name) => !defined.has(name) && !local.has(name))
        .map((name) => `${path}: var(${name})`);
    });

    expect(offenders).toEqual([]);
  });
});

describe("motion", () => {
  it("is switched off globally for anyone who asked for that", () => {
    expect(STYLESHEET).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  /** `transition: all` animates whatever a later rule adds, layout properties too. */
  it("never transitions every property at once", () => {
    const offenders = [join(SRC, "style.css"), ...sourceFiles()].filter((path) =>
      /transition:\s*all\b/.test(readFileSync(path, "utf8")),
    );

    expect(offenders).toEqual([]);
  });
});

describe("reflow", () => {
  /**
   * `repeat(auto-fill, minmax(19rem, 1fr))` reads as "as many 19rem columns as
   * fit", but 19rem is a *minimum*: below one track the track keeps its width and
   * the page grows sideways. `min(19rem, 100%)` collapses to the container
   * instead - WCAG 2.2 SC 1.4.10, content usable at 320px.
   */
  const TRACK = /repeat\(\s*auto-(?:fill|fit)\s*,\s*minmax\(\s*([^,)]+)/g;

  it("caps every auto-fill track at the width of its container", () => {
    const offenders: string[] = [];
    for (const path of [join(SRC, "style.css"), ...sourceFiles()]) {
      for (const match of readFileSync(path, "utf8").matchAll(TRACK)) {
        const minimum = match[1].trim();
        // `min(...)`, a percentage and a plain 0 all collapse on their own.
        if (!/^min\s*\(|%$|^0$/.test(minimum)) offenders.push(`${basename(path)}: minmax(${minimum}, ...)`);
      }
    }

    expect(offenders).toEqual([]);
  });
});

describe("colour scheme", () => {
  /**
   * Without it the browser draws its own parts - the autofill of the token
   * field, a checkbox's inside, a select's popup - for light in the dark theme.
   */
  it("is said in both themes, and in the page's head", () => {
    const { light, dark } = tokenBlocks(STYLESHEET);
    const head = readFileSync(join(process.cwd(), "index.html"), "utf8");

    expect(light).toMatch(/color-scheme:\s*light;/);
    expect(dark).toMatch(/color-scheme:\s*dark;/);
    expect(head).toMatch(/<meta name="color-scheme" content="light dark"/);
  });
});


describe("a colour the token check must see", () => {
  it.each([
    "  color: white;",
    "  outline: 2px solid #fff;",
    "  text-decoration-color: #f00;",
    "  color: hsl(0 0% 100%);",
    "  background: oklch(70% 0.1 200);",
    ".x { color: #fff; }",
    '<p style="color:#fff">',
    '<path fill="#000" />',
    "  --ink: #123456;",
    // every named colour, not a short list of them
    "  color: darkred;",
    "  background-color: whitesmoke;",
    // a bound style is an object with keys after commas, or a string
    `<p :style="{ fontWeight: 600, color: '#c00' }">`,
    `<p :style="'color: #fff'">`,
    `<path :fill="'#000'" />`,
    `<p v-bind:style="{ backgroundColor: 'gold' }">`,
    "<p style='color:#fff'>",
    // shorthands that carry a colour
    "  text-decoration: underline red;",
    "  filter: drop-shadow(0 0 2px #000);",
    "  column-rule: 1px solid #ccc;",
    // a value over more than one line
    "  background:\n    linear-gradient(#fff, #000);",
    "  box-shadow:\n    0 1px 2px var(--shadow-1),\n    0 0 1px #000;",
    "  border:\n    1px solid #ccc;",
  ])("is found: %s", (source) => {
    expect(colourLiterals(source)).not.toEqual([]);
  });

  it.each([
    "  color: var(--text);",
    "  border: 1px solid transparent;",
    "  stroke: currentColor;",
    "  white-space: nowrap;",
    // a file's name is no colour
    "  background: url(icon-red.svg);",
    "  background-image: url(red-dot.png);",
    `<p :style="{ width: redWidth }">`,
    // a comment says what was, not what is
    "/*\n  background: red;\n*/",
    '<!--\n<p style="color: red">\n-->',
    // a value ends with its line: the next one is someone else's
    '  filter: "Filter",\n  medal: "Gold, Silber oder Bronze",',
  ])("is not invented: %s", (source) => {
    expect(colourLiterals(source)).toEqual([]);
  });
});

describe("a page width the width check must see", () => {
  it.each([
    "max-width: 60rem;",
    "max-inline-size: 48rem;",
    "max-width: 1200px;",
    // the usual page width that shrinks on a small screen
    "max-width: min(96rem, 100%);",
    // fixed, it is a page's width and a reflow failure besides
    "width: 60rem;",
    "max-width: 50em;",
    "max-width: 90ch;",
    // wherever the length stands in the value
    "max-width: min(100%, 60rem);",
    "width: clamp(20rem, 80vw, 60rem);",
    "max-width: calc(60rem - 2rem);",
    "max-width:\n  60rem;",
  ])("is found: %s", (source) => {
    expect(pageWidths(source)).not.toEqual([]);
  });

  it.each([
    "max-width: 36rem;",
    "max-inline-size: 26rem;",
    "max-width: 320px;",
    "width: 20rem;",
    "max-width: 65ch;",
    // a dialog's width sits on the line, not past it
    "width: min(40rem, 100%);",
    "width: 640px;",
  ])(
    "is a component's own: %s",
    (source) => {
      expect(pageWidths(source)).toEqual([]);
    },
  );
});
