import { readdirSync, statSync } from "node:fs";
import { basename, join } from "node:path";

import { expect } from "vitest";

// vitest runs from the frontend root, and import.meta.url is not a file:// URL
// under its transform; `scanned` below fails loudly if this path is wrong.
export const SRC = join(process.cwd(), "src");
export const TESTS = join(process.cwd(), "tests");

/** Every `.vue` and `.ts` file under `dir`, recursively. */
export function sourceFiles(dir: string = SRC, pattern: RegExp = /\.(vue|ts)$/): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path, pattern);
    return pattern.test(entry) ? [path] : [];
  });
}

/** One file from each folder of src, so a walk that stopped at the top shows. */
export const ANCHORS = ["App.vue", "main.ts", "LoginView.vue", "ModalShell.vue", "http.ts"];
/** The same for a walk of the .vue files alone. */
export const VUE_ANCHORS = ["App.vue", "LoginView.vue", "ModalShell.vue"];

/** What a component's `<style>` blocks hold, joined. */
export function stylesOf(source: string): string {
  return [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(([, css]) => css).join("\n");
}

/** A style rule: its selectors, split at the commas, and its declarations. */
export interface CssRule {
  selectors: string[];
  body: string;
}

/**
 * The rules of a stylesheet, comments gone - a comment before a rule is no part
 * of its selector. A rule inside `@media` is read as a rule; the at-rule around
 * it is not.
 */
export function cssRules(css: string): CssRule[] {
  return [...css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
    selectors: selector
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean),
    body,
  }));
}

/** A class name as CSS writes it; anything else in a class attribute is no name. */
const CLASS_NAME = /^[A-Za-z_-][\w-]*$/;

/**
 * The style rules for the classes a file puts on an `<input>`, `<select>` or
 * `<textarea>`: the static classes of its template, wherever a selector names them.
 * A bound `:class` is an expression, not names.
 */
export function formControlRules(source: string): string[] {
  const classes = new Set<string>();
  // quoted values may hold a `>`, as an arrow function in a handler does
  for (const [, attributes] of source.matchAll(/<(?:input|select|textarea)\b((?:[^>"]|"[^"]*")*)>/g)) {
    for (const [, list] of attributes.matchAll(/(?<![:\w-])class="([^"]*)"/g)) {
      for (const name of list.split(/\s+/)) if (CLASS_NAME.test(name)) classes.add(name);
    }
  }
  if (classes.size === 0) return [];
  // the names hold letters, digits, `_` and `-` alone: nothing a pattern reads as syntax
  const named = new RegExp(`\\.(?:${[...classes].join("|")})(?![\\w-])`);
  return cssRules(stylesOf(source))
    .filter(({ selectors }) => selectors.some((selector) => named.test(selector)))
    .map(({ body }) => body);
}

/**
 * The walk found real files, the anchors among them: a scan that walked nothing
 * would pass every "no offenders" check below it.
 */
export function scanned(files: string[], ...anchors: string[]): void {
  const names = files.map((path) => basename(path));
  for (const anchor of anchors) expect(names, `the scan reached ${anchor}`).toContain(anchor);
}
