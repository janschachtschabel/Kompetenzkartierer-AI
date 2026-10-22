import { readdirSync, statSync } from "node:fs";
import { basename, join, relative, sep } from "node:path";

import { expect } from "vitest";

// vitest runs from the frontend root, and import.meta.url is not a file:// URL
// under its transform; `scanned` below fails loudly if this path is wrong.
export const SRC = join(process.cwd(), "src");
export const TESTS = join(process.cwd(), "tests");

/** The message catalogue's folder: words, which some scans leave out. */
export function inCatalogue(path: string): boolean {
  return relative(SRC, path).split(sep)[0] === "i18n";
}

/** Every `.vue` and `.ts` file under `dir`, recursively. */
export function sourceFiles(dir: string = SRC, pattern: RegExp = /\.(vue|ts)$/): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path, pattern);
    return pattern.test(entry) ? [path] : [];
  });
}

/**
 * A file from the top of src and from views, components and api, so a walk that
 * stopped at the top shows. Not from i18n: the catalogue scans leave it out.
 */
export const ANCHORS = ["App.vue", "main.ts", "LoginView.vue", "ModalShell.vue", "http.ts"];
/** The same for a walk of the .vue files alone. */
export const VUE_ANCHORS = ["App.vue", "LoginView.vue", "ModalShell.vue"];

/** What a component's `<style>` blocks hold, joined. */
export function stylesOf(source: string): string {
  return [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(([, css]) => css).join("\n");
}

/** `source` without its comments: HTML, block and line ones - not the "//" of an address. */
export function withoutComments(source: string): string {
  return (
    withoutCssComments(source)
      .replace(/<!--[\s\S]*?-->/g, "")
      // a line comment, not the "//" of a URL - after a scheme, a quote, `url(` or `=`
      .replace(/(^|[^:"'`(=])\/\/[^\n]*/g, "$1")
  );
}

/** CSS without its comments: a comment before a rule is no part of its selector, a `}` in one ends no block. */
function withoutCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** A style rule: its selectors, split at the commas, and its declarations. */
export interface CssRule {
  selectors: string[];
  body: string;
}

/**
 * Throws on a style rule nested in a style rule: the reader below would take the
 * inner one's selector and lose the outer one, and a guard would fall silent.
 * Inside an at-rule - `@media`, `@supports` - rules are where they belong.
 */
function refuseNesting(css: string): void {
  const atRule: boolean[] = [];
  let prelude = "";
  // a brace in a string - `content: "{"`, `[data-x="{"]` - opens nothing
  const unquoted = css.replace(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/g, '""');
  for (const sign of unquoted) {
    if (sign === "{") {
      if (atRule.length > 0 && !atRule[atRule.length - 1]) {
        throw new Error(`a nested CSS rule, which the guards cannot read: ${prelude.trim()}`);
      }
      atRule.push(prelude.trim().startsWith("@"));
      prelude = "";
    } else if (sign === "}") {
      atRule.pop();
      prelude = "";
    } else if (sign === ";") {
      prelude = "";
    } else {
      prelude += sign;
    }
  }
}

/**
 * The rules of a stylesheet, comments gone. A rule inside `@media` is read as a
 * rule; the at-rule around it is not. A nested style rule throws.
 */
export function cssRules(css: string): CssRule[] {
  const plain = withoutCssComments(css);
  refuseNesting(plain);
  return [...plain.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
    selectors: selector
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean),
    body,
  }));
}

/** The 148 named colours of CSS Color 4, as mdn-data lists them (`named-color`). */
const NAMED_COLOURS =
  "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown " +
  "burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan " +
  "darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred " +
  "darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink " +
  "deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold " +
  "goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush " +
  "lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey " +
  "lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime " +
  "limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen " +
  "mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin " +
  "navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise " +
  "palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue " +
  "saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow " +
  "springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen";

/** A colour written as a value: hex, a colour function, a colour's name. */
export const COLOUR_VALUE = new RegExp(
  "#[0-9a-f]{3,8}\\b|\\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix|color)\\(|" +
    `(?<![\\w-])(?:${NAMED_COLOURS.split(" ").join("|")})(?![\\w-])`,
  "i",
);

/**
 * The light and the dark token block of style.css, comments gone first: a `}`
 * in a comment would otherwise end a block early, and in the dark one hide
 * every token after it - checked against its light value, and passing.
 */
export function tokenBlocks(stylesheet: string): { light: string; dark: string } {
  const css = withoutCssComments(stylesheet);
  return {
    light: /^:root \{([\s\S]*?)\}/m.exec(css)?.[1] ?? "",
    dark: /@media \(prefers-color-scheme: dark\) \{\s*:root \{([\s\S]*?)\}/.exec(css)?.[1] ?? "",
  };
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
  // quoted values may hold a `>`, as an arrow function in a handler does; `<select-field>` is no control
  for (const [, attributes] of source.matchAll(/<(?:input|select|textarea)(?![\w-])((?:[^>"']|"[^"]*"|'[^']*')*)>/g)) {
    for (const [, , list] of attributes.matchAll(/(?<![:\w-])class=(["'])([\s\S]*?)\1/g)) {
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
