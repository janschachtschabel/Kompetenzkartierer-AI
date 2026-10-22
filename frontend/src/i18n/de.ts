// All user-facing strings live here behind semantic keys. A single-locale
// catalogue with its own t() keeps the strings external, so a second locale is
// mechanical work; tests/i18n-catalogue.test.ts keeps every key in use.
// simplify: one locale and two plural slots (one/other); a locale with more
// plural categories - Polish has four - needs vue-i18n or a third slot.
export const messages = {
  app: {
    title: "Kompetenzkartierer",
  },
} as const;

type Messages = typeof messages;

/** The locale the UI formats its numbers, plural forms and dates in. */
export const LOCALE = "de-DE";

/**
 * `{count|Abschnitt|Abschnitte}` - the noun in the form that agrees with
 * `count`. Per placeholder rather than per message, because one sentence can
 * hold two counts whose nouns agree with different ones.
 */
const PLURAL = /\{(\w+)\|([^|{}]*)\|([^|{}]*)\}/g;

const pluralRules = new Intl.PluralRules(LOCALE);
const numberFormat = new Intl.NumberFormat(LOCALE);

/** What a wording is filled with: counts, codes, names. */
export type MessageParams = Record<string, string | number | boolean>;

/** A wording, or a group of them, as the catalogue nests them. */
export interface Catalogue {
  readonly [name: string]: string | Catalogue;
}

/**
 * A parameter as the sentence shows it. A number of five digits and more is
 * grouped the German way ("125.000"), a fraction takes the decimal comma; four
 * digits stay as they are - how German prints them, and how a year reads.
 */
function display(value: string | number | boolean): string {
  if (typeof value !== "number") return String(value);
  return !Number.isInteger(value) || Math.abs(value) >= 10000 ? numberFormat.format(value) : String(value);
}

function applyPlurals(text: string, params: MessageParams): string {
  return text.replace(PLURAL, (match, name: string, one: string, other: string) => {
    const given = params[name];
    // A missing, blank or non-numeric count leaves the placeholder in plain
    // sight; picking a form would render confident nonsense. `Number("")` is 0,
    // not NaN, so a blank is ruled out by hand.
    if (given === undefined || given === "") return match;
    const count = Number(given);
    if (Number.isNaN(count)) return match;
    // Intl decides the category, so the rule stays the locale's.
    return pluralRules.select(count) === "one" ? one : other;
  });
}

/**
 * The wording at the dotted `key` in `catalogue`, filled with `params`; the key
 * itself where the catalogue holds no wording there, so a gap shows on screen.
 * Named placeholders keep sentences whole for translation instead of gluing
 * fragments together.
 */
export function translate(catalogue: Catalogue, key: string, params?: MessageParams): string {
  const value = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], catalogue);
  if (typeof value !== "string") return key;
  if (!params) return value;
  return applyPlurals(value, params).replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? display(params[name]) : match,
  );
}

/** The app's wording at `key`, e.g. t("login.errors.empty"). */
export function t(key: string, params?: MessageParams): string {
  return translate(messages, key, params);
}

export type { Messages };
