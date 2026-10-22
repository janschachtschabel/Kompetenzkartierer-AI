// @vitest-environment node
// (the Vite config reads import.meta.url as a file URL, which jsdom's is not)
//
// The licence of every package the bundle carries goes out with it: Vue and
// vue-router are MIT, the Roboto fonts OFL, and both ask that their notice
// travel with every copy -- which the minified bundle, stripped of its
// banners, did not (old app, audit 2026-09-26, E-65).
import { describe, expect, it } from "vitest";

import { packageDir, thirdPartyLicenses } from "../build/licenses.ts";
import config from "../vite.config.ts";

describe("packageDir", () => {
  it("finds the package a module lies in, scoped or not, with either slash", () => {
    expect(packageDir("/app/frontend/node_modules/vue/dist/vue.runtime.esm-bundler.js")).toBe(
      "/app/frontend/node_modules/vue",
    );
    expect(packageDir("C:\\app\\node_modules\\@vue\\runtime-core\\dist\\runtime-core.esm-bundler.js")).toBe(
      "C:/app/node_modules/@vue/runtime-core",
    );
    expect(packageDir("/app/node_modules/@fontsource-variable/roboto/index.css?direct")).toBe(
      "/app/node_modules/@fontsource-variable/roboto",
    );
  });

  it("takes the innermost package of a nested one", () => {
    expect(packageDir("/app/node_modules/a/node_modules/b/index.js")).toBe("/app/node_modules/a/node_modules/b");
  });

  it("finds none for the app's own modules and virtual ones", () => {
    expect(packageDir("/app/frontend/src/main.ts")).toBeNull();
    expect(packageDir("\0plugin-vue:export-helper")).toBeNull();
  });
});

describe("the build", () => {
  it("writes the licences beside the bundle", () => {
    const names = (config.plugins ?? []).flat().map((plugin) => (plugin as { name?: string } | null)?.name);

    expect(names).toContain(thirdPartyLicenses().name);
  });
});
