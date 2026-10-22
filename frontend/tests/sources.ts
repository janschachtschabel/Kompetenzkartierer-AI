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

/** The style rules for the classes a file puts on an `<input>`, `<select>` or `<textarea>`, read from its template. */
export function formControlRules(source: string): string[] {
  const classes = new Set<string>();
  for (const [, attributes] of source.matchAll(/<(?:input|select|textarea)\s([^>]*)>/g)) {
    for (const name of /class="([^"]*)"/.exec(attributes)?.[1].split(/\s+/) ?? []) if (name) classes.add(name);
  }
  if (classes.size === 0) return [];
  const rule = new RegExp(`^[ \\t]*\\.(?:${[...classes].join("|")})[^{]*\\{([^}]*)\\}`, "gm");
  return [...source.matchAll(rule)].map((match) => match[1]);
}

/**
 * The walk found real files, the anchors among them: a scan that walked nothing
 * would pass every "no offenders" check below it.
 */
export function scanned(files: string[], ...anchors: string[]): void {
  const names = files.map((path) => basename(path));
  for (const anchor of anchors) expect(names, `the scan reached ${anchor}`).toContain(anchor);
}
