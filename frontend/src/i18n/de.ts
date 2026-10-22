// All user-facing strings live here behind semantic keys. A single-locale
// catalogue with its own t() keeps the strings external, so a second locale is
// mechanical work; tests/i18n-catalogue.test.ts keeps every key in use.
// simplify: one locale and two plural slots (one/other); a locale with more
// plural categories - Polish has four - needs vue-i18n or a third slot.
export const messages = {
  app: {
    title: "Kompetenzkartierer",
    // The way past the header for someone arriving by keyboard.
    skipToContent: "Zum Inhalt springen",
    nav: {
      // Names the landmark, so a screen reader can list it and jump to it by name.
      label: "Hauptnavigation",
      start: "Start",
    },
    // What each page is called in the browser's title bar, its tabs and
    // bookmarks - and what a screen reader announces on arrival.
    titles: {
      start: "Start",
      login: "Anmeldung",
    },
    roles: {
      admin: "Administration",
      redaktion: "Redaktion",
      nutzer: "Nutzung",
    },
    roleList: "Rollen: {roles}",
    signedInAs: "Angemeldet als",
    signIn: "Anmelden",
    signOut: "Abmelden",
  },
  login: {
    heading: "Anmeldung",
    intro: "Gib das Zugangstoken ein, das dir die Administration gegeben hat.",
    tokenLabel: "Zugangstoken",
    submit: "Anmelden",
    checking: "Wird geprüft …",
    errors: {
      empty: "Gib ein Zugangstoken ein.",
      invalid: "Dieses Zugangstoken gilt nicht. Prüfe es, oder bitte die Administration um ein neues.",
      network: "Der Server ist nicht erreichbar. Versuch es gleich noch einmal.",
      server: "Der Server hat unerwartet geantwortet. Versuch es später noch einmal.",
      locked:
        "Zu viele fehlgeschlagene Anmeldungen von dieser Adresse. " +
        "Versuch es in {count} {count|Minute|Minuten} noch einmal.",
      lockedLater: "Zu viele fehlgeschlagene Anmeldungen von dieser Adresse. Versuch es später noch einmal.",
    },
  },
  start: {
    welcome: "Willkommen, {name}",
    intro:
      "Hier entsteht die Wissenslandkarte der Lehrpläne: erfassen, an Kompetenz- und " +
      "Niveauschemata andocken, vernetzen. Die ersten Werkzeuge folgen.",
    about: "Der Kompetenzkartierer erfasst Lehrpläne aller Bildungsbereiche und verbindet sie zu einer Wissenslandkarte.",
    // What PUBLIC_ACCESS opens to a visitor without an account.
    visitor: {
      off: "Ohne Konto ist noch nichts offen. Melde dich mit deinem Zugangstoken an.",
      lookup: "Nachschlagen ist auch ohne Konto offen. Für alles andere meldest du dich an.",
      search: "Nachschlagen und Suchen sind auch ohne Konto offen. Für alles andere meldest du dich an.",
    },
    signIn: "Zur Anmeldung",
    infoFailed: "Die Startseite konnte nicht geladen werden.",
  },
  dialog: {
    // The confirm dialog's default: it asks before something is removed.
    confirm: "Löschen",
    cancel: "Abbrechen",
  },
  states: {
    loading: "Wird geladen …",
    retry: "Erneut versuchen",
    // A sentence, with its full stop: a failure's reason may follow it.
    errorTitle: "Etwas ist schiefgelaufen.",
    offline: "Der Server ist nicht erreichbar. Prüfe die Verbindung und versuch es noch einmal.",
    tooManyRequests:
      "Zu viele Anfragen in kurzer Zeit. Versuch es in {count} {count|Sekunde|Sekunden} noch einmal.",
  },
  // The page's own words for the refusals the server names by a code
  // (REFUSAL_CODES in refusals.ts), each saying why and what to do next.
  refusals: {
    forbidden: "Dafür fehlt deinem Konto die nötige Rolle. Rollen vergibt die Administration.",
    service_unavailable: "Die Datenbank antwortet gerade nicht. Versuch es in ein paar Sekunden noch einmal.",
    validation_failed: "Die Eingabe ist so nicht gültig. Prüfe sie und versuch es noch einmal.",
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
