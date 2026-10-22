import { readFileSync } from "node:fs";
import { basename, join } from "node:path";

import { describe, expect, it } from "vitest";

import { SRC, scanned, sourceFiles } from "./sources";

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
  scanned(sourceFiles(), "App.vue", "main.ts");
});

// A colour written as a literal in a declaration: a hex value or rgb()/rgba().
const COLOUR_LITERAL =
  /^[ \t]*(?:background|color|border[\w-]*|fill|stroke|box-shadow)[^;:]*:[^;]*?(#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\))/gm;

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
      [...readFileSync(path, "utf8").matchAll(/max-width:\s*([\d.]+)rem/g)]
        .filter(([, value]) => Number(value) >= 40)
        .map(([match]) => `${path}: ${match}`),
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
    const found = (css: string) => [...css.matchAll(COLOUR_LITERAL)].map(([, value]) => value);
    expect(found("  color: #fff;")).toEqual(["#fff"]);
    expect(found("  border-color: #1a2b3c;")).toEqual(["#1a2b3c"]);
    expect(found("  color: var(--danger, #f08080);")).toEqual(["#f08080"]);
    expect(found("  background: rgba(0, 0, 0, 0.5);")).toEqual(["rgba(0, 0, 0, 0.5)"]);
    expect(found("  color: var(--text);")).toEqual([]);
  });

  it("is never written as a literal in a component", () => {
    // A colour named in style.css can be checked, changed and themed; one typed
    // into a component can be none of those.
    const offenders = sourceFiles().flatMap((path) =>
      [...readFileSync(path, "utf8").matchAll(COLOUR_LITERAL)].map(([, value]) => `${path}: ${value}`),
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
    const light = /^:root \{([\s\S]*?)\n\}/m.exec(STYLESHEET)?.[1] ?? "";
    const dark = /@media \(prefers-color-scheme: dark\) \{\s*:root \{([\s\S]*?)\n {2}\}/.exec(STYLESHEET)?.[1] ?? "";
    const head = readFileSync(join(process.cwd(), "index.html"), "utf8");

    expect(light).toMatch(/color-scheme:\s*light;/);
    expect(dark).toMatch(/color-scheme:\s*dark;/);
    expect(head).toMatch(/<meta name="color-scheme" content="light dark"/);
  });
});
