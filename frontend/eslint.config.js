/**
 * Lint rules for the SPA.
 *
 * Type-aware (`recommendedTypeChecked`) rather than syntax-only: the rules that
 * earn a linter its place here need types. `no-floating-promises` is the one
 * that pays for the slower run -- almost everything this app does is an async
 * call, and a forgotten `await` shows up as a silently empty screen rather than
 * as an error.
 *
 * `vue-tsc` already owns type *errors*; this owns the patterns that type-check
 * fine and are still wrong.
 */
import { defineConfigWithVueTs, vueTsConfigs } from "@vue/eslint-config-typescript";
import pluginVue from "eslint-plugin-vue";

export default defineConfigWithVueTs(
  {
    name: "app/ignores",
    // Build output and the dependency tree are not ours to lint.
    ignores: ["dist/**", "coverage/**", "node_modules/**"],
  },
  {
    name: "app/files",
    files: ["**/*.ts", "**/*.vue"],
  },
  {
    // The api is one module to the app: tests replace its functions on `@/api`
    // (vi.spyOn), and a caller importing `@/api/<domain>` directly would get
    // past the stand-in and reach the network.
    name: "app/api-entry",
    files: ["src/**/*.ts", "src/**/*.vue"],
    ignores: ["src/api/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["@/api/*"], message: 'Import from "@/api"; tests replace its functions there.' }] },
      ],
    },
  },
  {
    // Build config lives outside tsconfig's program, so the type-aware rules
    // have no types for it. Linted for syntax rather than excluded: a mistake
    // in the build config breaks everything downstream of it.
    name: "app/build-config",
    files: ["vite.config.ts", "eslint.config.js"],
    extends: [vueTsConfigs.disableTypeChecked],
  },
  // `essential`, not `recommended`: the difference between them is almost
  // entirely template formatting (attributes per line, self-closing tags,
  // indentation), and that is a formatter's job -- this project has none. Left
  // on, those rules printed 446 of 495 findings on the first run, which is how
  // a linter earns being switched off. What stays is the error-prevention set.
  pluginVue.configs["flat/essential"],
  vueTsConfigs.recommendedTypeChecked,
);
