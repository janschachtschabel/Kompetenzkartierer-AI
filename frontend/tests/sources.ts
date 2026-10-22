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

/**
 * The walk found real files, the anchors among them: a scan that walked nothing
 * would pass every "no offenders" check below it.
 */
export function scanned(files: string[], ...anchors: string[]): void {
  const names = files.map((path) => basename(path));
  for (const anchor of anchors) expect(names, `the scan reached ${anchor}`).toContain(anchor);
}
