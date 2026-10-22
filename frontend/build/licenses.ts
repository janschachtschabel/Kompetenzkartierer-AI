// The licence of every package the bundle carries, written beside it as
// licenses.txt.
//
// Vue and vue-router are MIT, the Roboto fonts OFL: both ask that their notice
// travel with every copy, and the minified bundle keeps none of the banners
// (old app, audit 2026-09-26, E-65). The packages are read off the build itself -- every
// module under node_modules it loaded, the fonts' stylesheets among them -- so a
// new dependency is named without anyone listing it.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { Plugin } from "vite";

const NODE_MODULES = "/node_modules/";
const LICENCE_FILE = /^(licen[cs]e|copying)(\.|$)/i;

/** The directory of the package a module lies in; null outside node_modules. */
export function packageDir(id: string): string | null {
  const path = id.replace(/\\/g, "/").split("?")[0];
  const at = path.lastIndexOf(NODE_MODULES);
  if (at < 0) return null;
  const parts = path.slice(at + NODE_MODULES.length).split("/");
  const depth = parts[0].startsWith("@") ? 2 : 1;
  if (parts.length <= depth) return null;
  return path.slice(0, at + NODE_MODULES.length) + parts.slice(0, depth).join("/");
}

function section(dir: string): string {
  const manifest = JSON.parse(readFileSync(join(dir, "package.json"), "utf8")) as {
    name: string;
    version: string;
    license?: string;
  };
  const file = readdirSync(dir).find((name) => LICENCE_FILE.test(name));
  const text = file ? readFileSync(join(dir, file), "utf8").trim() : "(the package has no licence file)";
  return `${manifest.name} ${manifest.version} -- ${manifest.license ?? "no licence declared"}\n\n${text}`;
}

export function thirdPartyLicenses(fileName = "licenses.txt"): Plugin {
  return {
    name: "third-party-licenses",
    apply: "build",
    generateBundle() {
      const dirs = new Set<string>();
      for (const id of this.getModuleIds()) {
        const dir = packageDir(id);
        if (dir) dirs.add(dir);
      }
      const sections = [...dirs].sort().map(section);
      this.emitFile({ type: "asset", fileName, source: `${sections.join(`\n\n${"-".repeat(78)}\n\n`)}\n` });
    },
  };
}
