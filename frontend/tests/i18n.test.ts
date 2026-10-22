// The wording layer: placeholders, plural forms per count, German number
// grouping. Checked on a sample catalogue, so the rules are tested apart from
// whatever wording the pages happen to hold today.
import { describe, expect, it } from "vitest";

import { messages, t, translate } from "@/i18n/de";

/** A placeholder that holds a number by its name: a word before a noun is an adjective there. */
const COUNTING = /^(?:count|total|n|\w+Count)$/;

/**
 * `{x} Noun` without a plural form for x: "in {count} Sekunden" reads wrong for
 * one. Any space between (`\s` takes a protected one too); for a count also up
 * to two adjectives - "{count} neue offene Fragen" - which after a name would be
 * a verb ("{name} hat"). An adjective before a noun ends in -e, -en, -er or -es
 * and is no article: "{count} pro Seite", "{count} der Lehrpläne" read right for
 * one. A noun has a small letter: ECTS and MB are units.
 */
const ADJECTIVE = String.raw`(?!(?:der|die|das|den|dem|des)\s)[a-zäöüß]{2,}(?:e|en|er|es)\s+`;
const COUNT_BEFORE_NOUN = new RegExp(
  String.raw`\{(\w+)\}\s+(?!\{\1\|)((?:${ADJECTIVE}){0,2})[A-ZÄÖÜ](?=[\wÄÖÜäöüß-]*[a-zäöüß])[\wÄÖÜäöüß-]*`,
  "g",
);

function countsWithoutPlural(text: string): string[] {
  return [...text.matchAll(COUNT_BEFORE_NOUN)]
    .filter(([, name, between]) => !between || COUNTING.test(name))
    .map(([match]) => match);
}

const SAMPLE = {
  found: "{total} {total|Abschnitt|Abschnitte} erkannt",
  summary: "{imported} {imported|Element|Elemente} übernommen, {linked} {linked|Zusatzkante|Zusatzkanten}",
  tokens: "{tokens} Token verbraucht",
  share: "Anteil {part}",
  nested: { greeting: "Hallo {name}" },
  inherited: "Wert {constructor}",
} as const;

describe("translate() with a count", () => {
  it("uses the singular for exactly one", () => {
    expect(translate(SAMPLE, "found", { total: 1 })).toBe("1 Abschnitt erkannt");
  });

  it("uses the plural for none and for many", () => {
    expect(translate(SAMPLE, "found", { total: 0 })).toBe("0 Abschnitte erkannt");
    expect(translate(SAMPLE, "found", { total: 7 })).toBe("7 Abschnitte erkannt");
  });

  it("decides each noun in a sentence by its own count", () => {
    // The case that rules out one plural form per message.
    expect(translate(SAMPLE, "summary", { imported: 1, linked: 2 })).toBe("1 Element übernommen, 2 Zusatzkanten");
    expect(translate(SAMPLE, "summary", { imported: 9, linked: 1 })).toBe("9 Elemente übernommen, 1 Zusatzkante");
  });

  it("reads a count the server sent as a string", () => {
    expect(translate(SAMPLE, "found", { total: "1" })).toBe("1 Abschnitt erkannt");
  });

  it("leaves the placeholder visible when there is no count to go on", () => {
    // Loud rather than silent: guessing a form would show confident nonsense.
    expect(translate(SAMPLE, "found", { other: 2 })).toContain("{total|Abschnitt|Abschnitte}");
    // A blank is the trap: `Number("")` is 0 and would quietly read as the plural.
    expect(translate(SAMPLE, "found", { total: "" })).toContain("{total|Abschnitt|Abschnitte}");
  });
});

describe("translate() with values", () => {
  it("fills named placeholders, in nested groups too", () => {
    expect(translate(SAMPLE, "nested.greeting", { name: "Jürgen" })).toBe("Hallo Jürgen");
  });

  it("leaves a placeholder it has no value for", () => {
    expect(translate(SAMPLE, "nested.greeting", {})).toBe("Hallo {name}");
  });

  it("groups a number of five digits and more the German way", () => {
    expect(translate(SAMPLE, "tokens", { tokens: 125000 })).toBe("125.000 Token verbraucht");
  });

  it("leaves a four-digit number as German prints it, and a year reads", () => {
    expect(translate(SAMPLE, "tokens", { tokens: 2026 })).toBe("2026 Token verbraucht");
  });

  it("writes a fraction with the decimal comma", () => {
    expect(translate(SAMPLE, "share", { part: 0.5 })).toBe("Anteil 0,5");
  });

  it("returns the key itself for a key the catalogue lacks, so the gap shows", () => {
    expect(translate(SAMPLE, "missing.key")).toBe("missing.key");
    expect(translate(SAMPLE, "nested")).toBe("nested");
  });
});

describe("t()", () => {
  it("reads the app's own catalogue", () => {
    expect(t("app.title")).toBe(messages.app.title);
  });
});

describe("the message catalogue", () => {
  it("has no parenthesised plural", () => {
    // "Runde(n)" is a placeholder for grammar rather than grammar; the plural
    // placeholder above is what replaces it.
    const source = JSON.stringify(messages);
    const offenders = [...source.matchAll(/[A-Za-zÄÖÜäöüß]+\((?:e|n|en|s)\)/g)].map((m) => m[0]);

    expect(offenders).toEqual([]);
  });
});


describe("a placeholder", () => {
  it("is filled from the values given, never from what every object inherits", () => {
    expect(translate(SAMPLE, "inherited", {})).toBe("Wert {constructor}");
  });
});

describe("a count before its noun", () => {
  it("is recognised without a plural form, and not with one", () => {
    expect(countsWithoutPlural("Versuch es in {count} Sekunden noch einmal.")).toEqual(["{count} Sekunden"]);
    expect(countsWithoutPlural("in {count} {count|Sekunde|Sekunden}")).toEqual([]);
  });

  it.each([
    ["Noch {count} offene Fragen.", "{count} offene Fragen"],
    ["{total} neue Lehrpläne erfasst.", "{total} neue Lehrpläne"],
    ["in {count} Sekunden", "{count} Sekunden"],
    ["{count} KMK-Standards", "{count} KMK-Standards"],
    ["{count} neue offene Fragen", "{count} neue offene Fragen"],
    ["{count} neuen Einträge", "{count} neuen Einträge"],
  ])("finds a count without its plural however it is written: %s", (text, found) => {
    expect(countsWithoutPlural(text)).toEqual([found]);
  });

  it.each([
    "{count} offene {count|Frage|Fragen}",
    "{name} hat Lehrpläne",
    "Anteil {part}",
    // a unit without a plural of its own
    "{credits} ECTS",
    "{size} MB",
    // words that read right for one as for many: no adjective before a noun
    "{count} pro Seite",
    "{count} je Seite",
    "{count} der Lehrpläne",
    "{count} in diesem Lehrplan",
    "{count} aus dem Katalog",
    "{count} von allen Ländern",
  ])(
    "leaves alone what is no count without a plural: %s",
    (text) => {
      expect(countsWithoutPlural(text)).toEqual([]);
    },
  );

  it("has a plural form throughout the catalogue", () => {
    expect(countsWithoutPlural(JSON.stringify(messages))).toEqual([]);
  });
});
