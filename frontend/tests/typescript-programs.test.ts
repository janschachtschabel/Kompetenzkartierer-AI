// @vitest-environment node
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The app and its tests are two TypeScript programs. With one, the tests' types
 * (node, vitest's globals) reached src too: `process.env`, `Buffer` or a stray
 * `describe` passed the type check and broke in the browser.
 */
interface TsConfig {
  compilerOptions?: { types?: string[] };
  files?: string[];
  include?: string[];
  references?: unknown[];
}

function config(name: string): TsConfig {
  return JSON.parse(readFileSync(join(process.cwd(), name), "utf8")) as TsConfig;
}

describe("the TypeScript programs", () => {
  it("are referenced from the root, which checks nothing itself", () => {
    const root = config("tsconfig.json");

    // without `files: []` the root would take in every file, with no types given
    expect(root.files).toEqual([]);
    expect(root.include).toBeUndefined();
    expect(root.references).toEqual([{ path: "./tsconfig.app.json" }, { path: "./tsconfig.node.json" }]);
  });

  it("give the app the browser's types and no node or test runner", () => {
    const app = config("tsconfig.app.json");

    expect(app.include).toEqual(["src/**/*.ts", "src/**/*.vue"]);
    expect(app.compilerOptions?.types).toEqual(["vite/client"]);
  });

  it("give the tests and the build their node and vitest types", () => {
    const node = config("tsconfig.node.json");

    expect(node.include).toEqual(expect.arrayContaining(["tests/**/*.ts", "vite.config.ts", "build/**/*.ts"]));
    expect(node.compilerOptions?.types).toEqual(["vitest/globals", "node"]);
  });

  it("are both checked by the build", () => {
    const manifest = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8")) as { scripts: Record<string, string> };

    expect(manifest.scripts.build).toMatch(/^vue-tsc -b && vite build$/);
  });
});
