import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { COLOUR_VALUE, SRC, VUE_ANCHORS, formControlRules, scanned, sourceFiles, tokenBlocks } from "./sources";

/**
 * WCAG 2.2 AA contrast, checked against the design tokens rather than against a
 * screenshot: the tokens are plain hex, and the ratio is arithmetic.
 *
 * Taken over from the old app, where it found what review did not: the dark-mode
 * primary button put white on its blue at 3.68:1, the filled destructive button
 * white on red at 3.76:1 in both themes.
 *
 * `--border` itself is not checked, deliberately. SC 1.4.11 governs the boundary
 * of a *control*; card outlines and dividers are decoration and exempt. Controls
 * use `--control-border`, which the outline pairs below hold to 3:1.
 */
const STYLESHEET = readFileSync(join(SRC, "style.css"), "utf8");

/** Relative luminance per WCAG 2.x. */
function luminance(hex: string): number {
  const channels = (hex.replace("#", "").match(/../g) ?? []).map((pair) => {
    const value = parseInt(pair, 16) / 255;
    return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(a: string, b: string): number {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

function declarations(block: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const [, name, value] of block.matchAll(/(--[\w-]+):\s*([^;]+);/g)) found[name] = value.trim();
  return found;
}

function themes(): { light: Record<string, string>; dark: Record<string, string> } {
  const blocks = tokenBlocks(STYLESHEET);
  expect(blocks.light, "style.css has a :root token block").not.toBe("");
  expect(blocks.dark, "style.css has a dark-mode :root block").not.toBe("");

  const light = declarations(blocks.light);
  // Dark mode overrides a subset, so it inherits whatever it does not restate -
  // which is why its completeness has a test of its own ("gives every colour a dark value").
  return { light, dark: { ...light, ...declarations(blocks.dark) } };
}

/** [what it is, foreground token, background token, ratio SC 1.4.3/1.4.11 wants] */
const PAIRS: [string, string, string, number][] = [
  ["body text on a card", "--text", "--surface", 4.5],
  ["body text on the page", "--text", "--bg", 4.5],
  ["muted text on a card", "--text-muted", "--surface", 4.5],
  ["muted text on the page", "--text-muted", "--bg", 4.5],
  ["primary button label", "--accent-contrast", "--accent", 4.5],
  ["primary button against the page", "--accent", "--bg", 3],
  ["link text on a card", "--accent", "--surface", 4.5],
  ["destructive text on a card", "--danger", "--surface", 4.5],
  ["affirmative text on a card", "--success", "--surface", 4.5],
  ["affirmative text on the page", "--success", "--bg", 4.5],
  ["filled destructive button label", "--danger-contrast", "--danger-solid", 4.5],
  ["filled destructive button against the page", "--danger-solid", "--bg", 3],
  ["focus ring against the page", "--focus", "--bg", 3],
  ["focus ring on a card", "--focus", "--surface", 3],
  ["control outline on a card", "--control-border", "--surface", 3],
  ["control outline on the page", "--control-border", "--bg", 3],
  ["selected text", "--text", "--accent-wash", 4.5],
  ["error text on the page", "--danger", "--bg", 4.5],
  ["text on a hovered quiet button", "--text", "--surface-subtle", 4.5],
  ["destructive text on a hovered quiet button", "--danger", "--surface-subtle", 4.5],
  ["warning text on a card", "--warning", "--surface", 4.5],
  ["warning text on the page", "--warning", "--bg", 4.5],
  // A status pill brings its own background, so what matters is its label
  // against that. The pill is no control and its meaning is in the word
  // (SC 1.4.1), so 1.4.11 does not apply to its edge.
  ["info pill label", "--status-info-ink", "--status-info-bg", 4.5],
  ["success pill label", "--status-success-ink", "--status-success-bg", 4.5],
  ["error pill label", "--status-error-ink", "--status-error-bg", 4.5],
  ["warning pill label", "--status-warning-ink", "--status-warning-bg", 4.5],
  ["neutral pill label", "--text-muted", "--surface-subtle", 4.5],
  // A page notice wears the info tint and may hold a link, a button and a failure.
  ["link text in a notice", "--accent", "--status-info-bg", 4.5],
  ["primary button against a notice", "--accent", "--status-info-bg", 3],
  ["a failure in a notice", "--status-error-ink", "--status-info-bg", 4.5],
  ["a quiet button's outline in a notice", "--control-border", "--status-info-bg", 3],
  ["a focus ring in a notice", "--focus", "--status-info-bg", 3],
];

describe.each(["light", "dark"] as const)("%s theme contrast", (theme) => {
  const tokens = themes()[theme];

  it.each(PAIRS)("%s reaches its threshold", (_what, foreground, background, minimum) => {
    const front = tokens[foreground];
    const back = tokens[background];
    // A renamed or dropped token must fail loudly, not silently skip the check.
    expect(front, `${foreground} is defined`).toMatch(/^#[0-9a-f]{6}$/i);
    expect(back, `${background} is defined`).toMatch(/^#[0-9a-f]{6}$/i);

    expect(contrast(front, back)).toBeGreaterThanOrEqual(minimum);
  });
});

/**
 * The pairs hold `--control-border` to 3:1; this holds a component to using it.
 * In the old app the user administration drew its fields with the quiet
 * `--border` at 1.46:1, so the form that creates accounts had no visible edge.
 */
it("draws no form control's outline with the decorative border token", () => {
  const files = sourceFiles(SRC, /\.vue$/);
  scanned(files, ...VUE_ANCHORS);

  const decorative = /border[\w-]*\s*:[^;]*var\(--border\)/;
  const offenders = files.flatMap((path) => {
    const source = readFileSync(path, "utf8");
    const byElement = [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
      .filter(([, selector, body]) => /\b(input|select|textarea)\b/.test(selector) && decorative.test(body))
      .map(([, selector]) => `${path}: ${selector.trim()}`);
    // and by a class the template puts on the control
    const byClass = formControlRules(source)
      .filter((body) => decorative.test(body))
      .map(() => `${path}: a form control's class`);
    return [...byElement, ...byClass];
  });

  expect(offenders).toEqual([]);
  expect(
    formControlRules('<input class="token" />\n<style>\n.token {\n  border: 1px solid var(--border);\n}\n</style>').some(
      (body) => decorative.test(body),
    ),
    "the class reader sees an input's class",
  ).toBe(true);
});


/**
 * The dark theme inherits every token it does not restate, so a colour given
 * only a light value - or a dark block cut short by a `}` in a comment - would
 * be checked in the dark theme with its light value, and pass.
 */
/** The colour tokens of the light block, and those of them the dark block does not restate. */
function darkGaps(stylesheet: string): { colours: string[]; missing: string[] } {
  const blocks = tokenBlocks(stylesheet);
  const light = declarations(blocks.light);
  const dark = declarations(blocks.dark);
  // any colour: a hex of any length, a translucent rgb(), a shadow that holds one
  const colours = Object.keys(light).filter((name) => COLOUR_VALUE.test(light[name]));
  return { colours, missing: colours.filter((name) => !(name in dark)) };
}

it("gives every colour a dark value", () => {
  const { colours, missing } = darkGaps(STYLESHEET);
  expect(colours.length, "the colour tokens were read").toBeGreaterThan(15);
  expect(colours, "translucent colours count too").toEqual(expect.arrayContaining(["--scrim", "--shadow-1"]));

  expect(missing).toEqual([]);
});

it("tells a colour without a dark value, written any way, and is not cut short by a comment", () => {
  const sheet = (dark: string) =>
    `:root {\n  --text: #1c1a17;\n  --overlay: rgb(255 255 255 / 80%);\n  --edge: #ccc;\n  --space-1: 0.5rem;\n}\n` +
    `@media (prefers-color-scheme: dark) {\n  :root {\n${dark}\n  }\n}\n`;

  expect(darkGaps(sheet("    --text: #f2f1ee;")).missing).toEqual(["--overlay", "--edge"]);
  // round 1: a `}` in a comment at the head of the dark block hid everything after it
  const commented = "    /* tokens {like this} */\n    --text: #f2f1ee;\n    --overlay: rgb(0 0 0 / 60%);\n    --edge: #444;";
  expect(darkGaps(sheet(commented)).missing).toEqual([]);
});
