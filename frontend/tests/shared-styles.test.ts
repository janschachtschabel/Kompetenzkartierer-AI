import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { ANCHORS, SRC, formControlRules, scanned, sourceFiles } from "./sources";

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
  scanned(sourceFiles(), ...ANCHORS);
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

function declarationsOf(body: string): string[] {
  return body
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split(";")
    .map((declaration) => declaration.trim())
    .filter(Boolean);
}

/** Every declaration the shared rules for `selector` make, read out of style.css. */
function sharedDeclarations(selector: string): Set<string> {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rule = new RegExp(`^${escaped}(?![\\w-])[^{]*\\{([^}]*)\\}`, "gm");
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

  it("reads the static classes however the tag is written, and nothing it should not", () => {
    const rules = (tag: string, css: string) => formControlRules(`${tag}\n<style>\n${css} {\n  color: red;\n}\n</style>`);

    // a bound class before the static one, its expression no class names
    expect(rules('<input :class="{ wide: open }" class="token-field" />', ".token-field")).toHaveLength(1);
    // a ternary in a bound class is no pattern to build a regex from
    expect(rules(`<input :class="error ? 'token-field' : ''" class="x" />`, ".x")).toHaveLength(1);
    // an arrow function in a handler does not end the tag
    expect(rules('<input @input="(e) => (typed = e)" class="token-field" />', ".token-field")).toHaveLength(1);
    // the class anywhere in a selector
    expect(rules('<input class="token-field" />', ".login .token-field")).toHaveLength(1);
    // a class is a whole name: `token` is not `.token-list`
    expect(rules('<input class="token" />', ".token-list")).toEqual([]);
    // single quotes are quotes too
    expect(rules("<input class='token-field' />", ".token-field")).toHaveLength(1);
    // a component named like a control is none
    expect(rules('<select-field class="token-field" />', ".token-field")).toEqual([]);
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

describe("a link drawn as a button", () => {
  /**
   * `.btn` sits on links too (the way to the sign-in): with the browser's
   * underline and without the height the element rule gives a `button`, the
   * same class looked different on two elements.
   */
  it("is drawn as one: no underline, the height of a button", () => {
    const shared = sharedDeclarations(".btn");

    expect(shared).toContain("text-decoration: none");
    expect(shared).toContain("min-height: 40px");
  });

  it("and a button drawn as a link keeps the link's underline and the line's height (WCAG 1.4.1)", () => {
    // in running text, a link-styled control without them is told apart by colour alone, in a box of its own
    const shared = sharedDeclarations(".btn.link");

    expect(shared).toContain("text-decoration: underline");
    expect(shared).toContain("min-height: auto");
    // and in the size and weight of the text around it, not a button's
    expect(shared).toContain("font-size: inherit");
    expect(shared).toContain("font-weight: inherit");
  });
});
