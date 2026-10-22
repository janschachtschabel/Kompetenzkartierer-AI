import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { SRC, scanned, sourceFiles } from "./sources";

/**
 * Shared rules live once, in style.css. In the old app every one of them had
 * drifted as per-component copies: three `.visually-hidden` with different
 * clipping, four card paddings, a button weight of 400 in one component and 500
 * in another, and a `.field` copy whose own label column put no two controls on
 * one edge. Each check below reads the signature, not only the name: copies
 * came back under other names.
 */
const STYLESHEET = readFileSync(join(SRC, "style.css"), "utf8");

it("scans the component sources", () => {
  scanned(sourceFiles(), "App.vue", "main.ts");
});

describe("visually-hidden", () => {
  it("is defined once, in the global stylesheet", () => {
    expect(STYLESHEET).toContain(".visually-hidden");
    // Both clipping mechanisms: `clip` for older engines, `clip-path` for current ones.
    expect(STYLESHEET).toContain("clip-path: inset(50%)");
    expect(STYLESHEET).toContain("white-space: nowrap");
  });

  it("is not redefined inside a component", () => {
    const offenders = sourceFiles().filter((path) => /^\s*\.visually-hidden\s*\{/m.test(readFileSync(path, "utf8")));

    expect(offenders).toEqual([]);
  });

  it("is not re-invented under another name", () => {
    // The clip rectangle is the signature of screen-reader-only text, whatever
    // the rule is called. style.css is no .vue or .ts file and never enters the scan.
    const offenders = sourceFiles().filter((path) => readFileSync(path, "utf8").includes("clip: rect("));

    expect(offenders).toEqual([]);
  });
});

const SHARED_BASE = [".card", ".btn", ".field"];

/** What `input, select, textarea` in style.css already applies to every control. */
const CONTROL_SHELL = ["border: 1px solid var(--control-border)", "background: var(--surface)", "color: var(--text)"];

/** The style rules for the classes a file puts on an `<input>`, `<select>` or `<textarea>`, read from its template. */
function formControlRules(source: string): string[] {
  const classes = new Set<string>();
  for (const [, attributes] of source.matchAll(/<(?:input|select|textarea)\s([^>]*)>/g)) {
    for (const name of /class="([^"]*)"/.exec(attributes)?.[1].split(/\s+/) ?? []) if (name) classes.add(name);
  }
  if (classes.size === 0) return [];
  const rule = new RegExp(`^[ \\t]*\\.(?:${[...classes].join("|")})[^{]*\\{([^}]*)\\}`, "gm");
  return [...source.matchAll(rule)].map((match) => match[1]);
}

function declarationsOf(body: string): string[] {
  return body
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split(";")
    .map((declaration) => declaration.trim())
    .filter(Boolean);
}

/** Every declaration the shared rules for `selector` make, read out of style.css. */
function sharedDeclarations(selector: string): Set<string> {
  const rule = new RegExp(`^\\${selector}(?![\\w-])[^{]*\\{([^}]*)\\}`, "gm");
  return new Set([...STYLESHEET.matchAll(rule)].flatMap((match) => declarationsOf(match[1])));
}

/** `rule` restated with declarations from `shared`, in any file. */
function restating(pattern: RegExp, shared: Set<string>): string[] {
  return sourceFiles().flatMap((path) =>
    [...readFileSync(path, "utf8").matchAll(pattern)].flatMap(([, selector, body]) =>
      declarationsOf(body)
        .filter((declaration) => shared.has(declaration))
        .map((declaration) => `${path}: ${selector} { ${declaration} }`),
    ),
  );
}

describe("shared component classes", () => {
  it("declares the card, button and field base rules in the global stylesheet", () => {
    for (const selector of SHARED_BASE) expect(STYLESHEET).toMatch(new RegExp(`^\\${selector} \\{`, "m"));
  });

  /**
   * A rule that opens its own grid and sizes a label column is a `.field` under
   * another name. `.checkbox-field` sets only the columns: a variant, not a copy.
   */
  it("does not re-invent the field layout under another name", () => {
    const offenders = sourceFiles().flatMap((path) =>
      [...readFileSync(path, "utf8").matchAll(/([^{}]*)\{([^{}]*)\}/g)]
        .filter(([, , body]) => /display:\s*grid/.test(body) && /grid-template-columns:\s*auto 1fr/.test(body))
        .map(([, selector]) => `${path}: ${selector.trim()}`),
    );

    expect(offenders).toEqual([]);
  });

  it.each(SHARED_BASE)("does not redeclare the %s base rule in a component", (selector) => {
    const pattern = new RegExp(`^[ \\t]*\\${selector}\\s*\\{`, "m");

    expect(sourceFiles().filter((path) => pattern.test(readFileSync(path, "utf8")))).toEqual([]);
  });

  it("keeps the form-control shell on the element rule every control matches", () => {
    const rule = /^input, select, textarea \{([^}]*)\}/m.exec(STYLESHEET);

    expect(rule).not.toBeNull();
    for (const declaration of CONTROL_SHELL) expect(rule?.[1]).toContain(declaration);
  });

  it("does not restate a shared button declaration in a component", () => {
    const shared = sharedDeclarations(".btn");
    expect(shared.size, "the shared .btn rules were found").toBeGreaterThan(5);

    expect(restating(/^[ \t]*(\.btn(?![\w-])[^{]*?)\s*\{([^}]*)\}/gm, shared)).toEqual([]);
  });

  /**
   * A scoped `.status-badge.x` is (0,2,0) and beats the global rule: which colour
   * a meaning gets is decided in style.css and nowhere else.
   */
  it("does not colour a status pill inside a component", () => {
    const offenders = sourceFiles().flatMap((path) =>
      [...readFileSync(path, "utf8").matchAll(/^[ \t]*([\w.]*\.status-badge\.[\w-]+)/gm)].map(
        ([, selector]) => `${path}: ${selector}`,
      ),
    );

    expect(offenders).toEqual([]);
  });

  it("does not restate a shared pill declaration in a component", () => {
    const shared = sharedDeclarations(".status-badge");
    expect(shared.size, "the shared .status-badge rules were found").toBeGreaterThan(4);

    expect(restating(/^[ \t]*(\.status-badge)\s*\{([^}]*)\}/gm, shared)).toEqual([]);
  });

  it("does not restate a shared select declaration in a component", () => {
    const shared = sharedDeclarations(".form-select");
    expect(shared.size, "the shared .form-select rule was found").toBeGreaterThan(1);

    expect(restating(/^[ \t]*(\.form-select)[^{]*\{([^}]*)\}/gm, shared)).toEqual([]);
  });

  it("reads the rules of a form control's classes out of its template", () => {
    // The guard on the extractor: few controls exist yet, so it is checked on a
    // sample rather than on a count of real ones.
    const sample = '<input class="token-input" />\n<style>\n.token-input {\n  color: var(--text);\n}\n</style>';
    expect(formControlRules(sample)).toEqual(["\n  color: var(--text);\n"]);
  });

  it("does not restate that shell on a form control", () => {
    const offenders = sourceFiles().filter((path) =>
      formControlRules(readFileSync(path, "utf8")).some((body) =>
        CONTROL_SHELL.some((declaration) => body.includes(declaration)),
      ),
    );

    expect(offenders).toEqual([]);
  });
});
