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
      sources: "Quellen",
    },
    // What each page is called in the browser's title bar, its tabs and
    // bookmarks - and what a screen reader announces on arrival.
    titles: {
      start: "Start",
      login: "Anmeldung",
      sources: "Quellen",
      source: "Registereintrag",
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
      malformed: "Das ist kein Zugangstoken: Es beginnt mit kka_ und hat danach 43 Zeichen.",
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
      "Niveauschemata andocken, vernetzen. Unter „Quellen“ legst du die Lehrplandokumente an; " +
      "weitere Werkzeuge folgen.",
    about: "Der Kompetenzkartierer erfasst Lehrpläne aller Bildungsbereiche und verbindet sie zu einer Wissenslandkarte.",
    // What PUBLIC_ACCESS opens to a visitor without an account.
    visitor: {
      off: "Ohne Konto ist noch nichts offen. Melde dich mit deinem Zugangstoken an.",
      lookup: "Nachschlagen ist auch ohne Konto offen. Für alles andere meldest du dich an.",
      search: "Nachschlagen und Suchen sind auch ohne Konto offen. Für alles andere meldest du dich an.",
    },
    signIn: "Zur Anmeldung",
    infoFailed: "Die Startseite konnte nicht geladen werden.",
    accountFailed: "Dein Konto konnte nicht geladen werden.",
    // A 429 on the account: only a refused token meets the address's lock.
    accountRejected:
      "Das gespeicherte Zugangstoken gilt nicht mehr. " +
      "Melde dich ab und mit einem gültigen Zugangstoken neu an.",
  },
  // The source register: the curriculum documents and what may be done with them.
  sources: {
    heading: "Quellen",
    intro:
      "Das Register der Lehrplandokumente: was hochgeladen oder von einer Adresse abgerufen " +
      "wurde, wie weit es ist und unter welchen Rechten es steht.",
    addHeading: "Dokument hinzufügen",
    upload: {
      heading: "Datei hochladen",
      fileLabel: "Datei",
      fileHint: "PDF, Word (DOCX), RTF, HTML, Markdown, Text (UTF-8) oder Turtle, bis {limit} MB.",
      // where the limit did not load: the server still says it on a refusal
      fileHintNoLimit: "PDF, Word (DOCX), RTF, HTML, Markdown, Text (UTF-8) oder Turtle.",
      titleLabel: "Titel (freiwillig)",
      titleHint: "Ohne Titel trägt der Eintrag den Namen der Datei.",
      submit: "Hochladen",
      busy: "Wird hochgeladen …",
      done: "„{title}“ steht jetzt im Register.",
      failed: "Die Datei wurde nicht hochgeladen.",
      errors: {
        missing: "Wähle eine Datei aus.",
        tooLarge: "Die Datei ist größer als {limit} MB. Verkleinere sie oder teile sie auf.",
      },
    },
    import: {
      heading: "Von einer Adresse abrufen",
      urlLabel: "Adresse (URL)",
      urlHint: "Der Server lädt das Dokument selbst herunter; das dauert meist nur einige Sekunden.",
      titleLabel: "Titel (freiwillig)",
      titleHint: "Ohne Titel trägt der Eintrag den Namen der Datei unter der Adresse.",
      submit: "Abrufen",
      busy: "Wird gestartet …",
      started: "Der Abruf von „{title}“ läuft.",
      failed: "Der Abruf wurde nicht gestartet.",
      errors: {
        missing: "Gib eine Adresse ein.",
        scheme: "Das ist keine Webadresse. Eine Webadresse beginnt mit https:// oder http://.",
        spaces: "Die Adresse enthält Leerzeichen. Kopiere sie noch einmal aus der Adresszeile des Browsers.",
        tooLong:
          "Die Adresse ist länger als {limit} {limit|Zeichen|Zeichen}. Nimm die Adresse des Dokuments selbst, oft ohne den Teil " +
          "nach dem Fragezeichen.",
        credentials:
          "Die Adresse enthält einen Namen oder ein Kennwort. Der Server ruft nur frei zugängliche Adressen ab: " +
          "Lade die Datei stattdessen hoch.",
      },
    },
    jobs: {
      // the fetches and checks started on the page
      heading: "Aufträge",
    },
    // The check of the seed, an admin's (CheckStart.vue)
    check: {
      heading: "Saat prüfen",
      intro:
        "Fragt die Adresse jedes Kandidaten einmal ab: ob sie erreichbar ist, was dort liegt und wie groß es ist. " +
        "Gespeichert wird nur das Ergebnis. Die Prüfung beachtet robots.txt, fragt jeden Server höchstens alle " +
        "paar Sekunden und umgeht keine Sperre; bei vielen Adressen dauert sie eine Stunde und länger.",
      start: "Prüfung starten",
      confirmTitle: "Prüfung der Saat starten?",
      confirmMessage:
        "Der Server fragt jetzt die Adressen aller Kandidaten bei fremden Servern ab. Die Prüfung läuft im " +
        "Hintergrund weiter, auch wenn du die Seite verlässt; eine spätere Prüfung fragt nur, was noch offen ist.",
      confirm: "Prüfung starten",
      // an event, not a state: the line stays once the check has ended
      started: "Die Prüfung wurde gestartet; wie weit sie ist, zeigt die Liste der Aufträge.",
      running: "Eine Prüfung lief schon; wie weit sie ist, zeigt die Liste der Aufträge.",
      failed: "Die Prüfung wurde nicht gestartet.",
      jobLabel: "Prüfung der Saat",
    },
    register: {
      heading: "Register",
      columns: {
        title: "Titel",
        provenance: "Herkunft",
        status: "Stand",
        rights: "Rechte",
        added: "Hinzugefügt",
      },
      // Names the box that scrolls the table on a narrow screen, for whoever reaches it by keyboard.
      scrollLabel: "Registertabelle",
      noFile: "noch keine Datei",
      mine: "von dir",
      emptyTitle: "Noch keine Quellen",
      emptyBody: "Lade oben eine Datei hoch oder gib eine Adresse an. Der Eintrag erscheint dann hier.",
      loadFailed: "Das Register wurde nicht geladen.",
      shown: "{shown} von {total} {total|Eintrag|Einträgen}",
      more: "Weitere laden",
      moreFailed: "Weitere Einträge wurden nicht geladen.",
      reloadFailed: "Das Register wurde nicht neu geladen; es zeigt den Stand von vorher.",
      // Beside the heading while what the register shows is read again (SourcesView.vue)
      reading: "Wird neu geladen …",
    },
    // What the register shows (RegisterFilter.vue)
    filter: {
      legend: "Anzeigen",
      candidates: "Nur Kandidaten",
      candidatesHint:
        "Einträge aus Vergleichsdatensatz und Länderrecherche, deren Datei noch fehlt – das, was die " +
        "Prüfung der Saat ansieht.",
      status: "Stand",
      anyStatus: "jeder Stand",
      none: "Kein Eintrag passt zu diesem Filter.",
      emptyTitle: "Kein Eintrag passt",
      // by what is set; {label} is the checkbox's own label, {any} the status list's first choice
      emptyBody: {
        candidates: "Nimm „{label}“ zurück, um alle Einträge zu sehen.",
        status: "Wähle einen anderen Stand oder „{any}“.",
        both: "Nimm „{label}“ zurück oder wähle einen anderen Stand.",
      },
    },
    // Where an entry comes from (backend app/sources/register.py, Provenance). Read
    // as messages.sources.provenance[value], not by t(): a value holds a dot.
    provenance: {
      upload: "Upload",
      url: "Adresse",
      "vergleichsdatensatz-v62.493": "Vergleichsdatensatz",
      laenderrecherche: "Länderrecherche",
      ttl: "Turtle-Import",
      recherche: "Recherche",
      redaktion: "Redaktion",
    },
    // How far the register has come with it (RegisterStatus)
    status: {
      unchecked: "ungeprüft",
      reachable: "erreichbar",
      unreachable: "nicht erreichbar",
      acquired: "Datei liegt vor",
    },
    // On what terms it may be used (RightsStatus)
    rights: {
      amtlich: "amtliches Werk",
      offen_lizenziert: "offen lizenziert",
      geschuetzt: "geschützt",
      unklar: "ungeklärt",
    },
    // Whose curriculum it is, by the code of ISO 3166-2:DE the seeds give. Read as
    // messages.sources.countries[value], not by t(): a code holds a hyphen.
    countries: {
      DE: "Bund",
      "DE-BB": "Brandenburg",
      "DE-BE": "Berlin",
      "DE-BW": "Baden-Württemberg",
      "DE-BY": "Bayern",
      "DE-HB": "Bremen",
      "DE-HE": "Hessen",
      "DE-HH": "Hamburg",
      "DE-MV": "Mecklenburg-Vorpommern",
      "DE-NI": "Niedersachsen",
      "DE-NW": "Nordrhein-Westfalen",
      "DE-RP": "Rheinland-Pfalz",
      "DE-SH": "Schleswig-Holstein",
      "DE-SL": "Saarland",
      "DE-SN": "Sachsen",
      "DE-ST": "Sachsen-Anhalt",
      "DE-TH": "Thüringen",
    },
  },
  // One register entry's page (SourceDetailView.vue)
  entryPage: {
    // the page's heading until the entry names it
    heading: "Registereintrag",
    back: "Zurück zum Register",
    loadFailed: "Der Eintrag wurde nicht geladen.",
    notFoundTitle: "Diesen Eintrag gibt es nicht",
    notFoundBody: "Oder dein Konto sieht ihn nicht. Das Register zeigt alle Einträge, die du sehen darfst.",
    facts: {
      heading: "Eintrag",
      provenance: "Herkunft",
      status: "Stand",
      rights: "Rechte",
      license: "Lizenz",
      rightsEvidence: "Rechtebeleg",
      sourceType: "Art der Quelle",
      country: "Land",
      address: "Adresse",
      file: "Datei",
    },
    // How the entry's file came into the register, each time it came (Acquisition)
    acquisitions: {
      heading: "Erwerb der Datei",
      method: "Art",
      acquiredAt: "Zeitpunkt",
      receivedName: "Angekommen als",
      // the address asked first, then each one it led on to
      chain: "Adressen des Abrufs",
    },
    acquisitionMethod: {
      upload: "hochgeladen",
      url: "von einer Adresse abgerufen",
    },
    // Who publishes the copy (SourceType)
    sourceType: {
      amtlich: "amtliche Stelle",
      archiv: "Archivkopie",
      spiegel: "Spiegel, gekennzeichnet",
      sekundaer: "Sekundärquelle",
    },
    seed: {
      heading: "Aus der Saat",
      dataset: "Datensatz",
      schoolForm: "Schulform",
      stage: "Bildungsstufe",
      subject: "Fach",
      grades: "Jahrgänge",
      gradeRange: "{from}–{to}",
      binding: "Verbindlichkeit",
      archive: "Archivkopie",
      archiveOpen: "Archivkopie öffnen",
      evidence: "Beleg",
    },
    // Where a land's research read the row (Evidence)
    evidence: {
      E: "im Dokument selbst gefunden",
      S: "aus einer zweiten Quelle",
    },
    check: {
      heading: "Prüfung der Adresse",
      none: "Die Adresse wurde noch nicht geprüft.",
      outcome: "Ergebnis",
      statusCode: "Antwort des Servers",
      kind: "Art der Datei",
      size: "Größe",
      checkedAt: "Geprüft",
    },
    // What the check found (CheckOutcome)
    outcome: {
      reachable: "erreichbar",
      too_large: "erreichbar, aber größer, als ein Upload sein darf",
      refused: "vom Server verweigert",
      throttled: "der Server bat um eine Pause; eine spätere Prüfung fragt noch einmal",
      server_error: "Fehler beim Server",
      unavailable: "gerade nicht erreichbar; eine spätere Prüfung fragt noch einmal",
      unreachable: "nicht erreichbar",
      robots: "laut robots.txt nicht abzurufen",
    },
    // What lies at the address (DetectedKind)
    kind: {
      pdf: "PDF",
      docx: "Word (DOCX)",
      rtf: "RTF",
      html: "Webseite (HTML)",
      other: "andere Datei",
    },
    notes: {
      heading: "Zugangsnotizen",
      intro: "Hinweise des Vergleichsdatensatzes zu Land, Schulform und Fach: gesperrte Portale und Umwege.",
      none: "Keine Zugangsnotiz für Land, Schulform und Fach dieses Eintrags.",
    },
  },
  // A job the page follows (jobWatch.ts), and why one failed (jobMessages.ts).
  jobs: {
    status: {
      queued: "Wartet",
      running: "Läuft",
      done: "Fertig",
      failed: "Fehlgeschlagen",
      cancelled: "Abgebrochen",
    },
    // what a screen reader hears on each change
    announce: "{label}: {status}",
    // how far a job has come, as it reports it (JobProgress.vue, PROGRESS)
    progress: {
      checking: "{done} von {total} {total|Adresse|Adressen} angesehen",
      converting: "Die Datei wird in Blöcke umgewandelt; bei einer großen Datei dauert das einige Minuten.",
    },
    trouble: "Der Server antwortet gerade nicht; der Stand wird weiter abgefragt.",
    // why there is nothing left to ask (jobWatch.ts, JobGone); for a fetch and the seed's check alike
    goneReasons: {
      unauthorized: "Deine Anmeldung ist abgelaufen. Melde dich neu an; was der Auftrag erreicht hat, zeigt danach das Register.",
      forbidden: "Diesen Auftrag darf dein Konto nicht verfolgen. Rollen vergibt die Administration.",
      not_found: "Dieser Auftrag ist nicht mehr zu finden. Was er erreicht hat, zeigt das Register unten.",
    },
    failedUnknown: "Der Auftrag ist fehlgeschlagen. Versuch es noch einmal; scheitert er wieder, melde es der Administration.",
    failures: {
      // also a host that does not resolve: an internal name and a misspelt one answer alike
      url_not_allowed:
        "Die Adresse ließ sich nicht auflösen oder führt in ein internes Netz; der Server ruft sie nicht ab. " +
        "Prüfe sie im Browser; stimmt sie, lade die Datei stattdessen hoch.",
      download_refused:
        "Der fremde Server hat die Datei verweigert, etwa weil es sie dort nicht gibt. Prüfe die Adresse im Browser.",
      unsupported_type:
        "Unter der Adresse liegt keine Datei, die der Kompetenzkartierer lesen kann. Oft ist es eine Webseite, " +
        "die erst zum Dokument verlinkt: Nimm dann die Adresse des Dokuments selbst.",
      archive_too_large:
        "Die Datei unter der Adresse ist ein Archiv, das ausgepackt zu groß wird. Prüfe, ob es wirklich ein " +
        "Word-Dokument ist.",
      source_missing: "Der Registereintrag hat keine Adresse, die abgerufen werden könnte. Lege ihn mit der Adresse neu an.",
      file_too_large:
        "Die Datei unter der Adresse ist größer, als ein Upload sein darf. Lade eine kleinere Fassung herunter " +
        "und lade sie hoch, oder teile sie auf.",
      too_many_redirects:
        "Die Adresse leitet immer weiter, ohne bei einer Datei anzukommen. Öffne sie im Browser und nimm die " +
        "Adresse, bei der das Dokument erscheint.",
      bad_answer:
        "Der fremde Server hat so geantwortet, dass sich keine Datei daraus lesen ließ. Lade das Dokument im " +
        "Browser herunter und lade es hoch.",
      download_throttled:
        "Der fremde Server bittet, ihn seltener anzufragen. Versuch es später noch einmal, oder lade das " +
        "Dokument im Browser herunter und lade es hoch.",
      // a conversion into blocks (source.convert)
      conversion_gone: "Diese Umwandlung steht nicht mehr im Register, etwa weil ihre Datei entfernt wurde.",
      unreadable:
        "Die Datei lässt sich nicht als PDF lesen; sie ist vielleicht beschädigt. Öffnet sie sich in einem " +
        "PDF-Programm, speichere sie dort neu und lade sie noch einmal hoch.",
      too_many_pages:
        "Die PDF-Datei hat mehr Seiten, als der Kompetenzkartierer umwandelt. Teile sie auf und lade die Teile " +
        "einzeln hoch.",
      needs_ocr:
        "Zu wenige Seiten der PDF-Datei tragen Text; sie ist wohl eingescannt. Eine Texterkennung (OCR) gibt es " +
        "hier noch nicht: Nimm eine Fassung mit Text, wo es eine gibt.",
      empty:
        "Die Umwandlung fand außer Kopf- und Fußzeilen keinen Text. Prüfe, ob die Datei das Dokument selbst ist " +
        "und nicht nur sein Deckblatt.",
      timed_out:
        "Die Umwandlung hat länger gedauert, als sie darf. Versuch es später noch einmal; eine sehr große Datei " +
        "teile auf.",
      died:
        "Die Umwandlung wurde beendet, wohl weil sie zu viel Speicher brauchte. Teile die Datei auf, oder melde " +
        "es der Administration.",
      not_pdf: "Die gespeicherte Datei ist keine PDF-Datei, auch wenn sie als eine angegeben ist. Lade sie als PDF neu hoch.",
      file_gone: "Die Datei fehlt im Speicher des Servers. Melde das bitte der Administration.",
      handler_error:
        "Der Auftrag ist mehrmals gescheitert, etwa weil ein fremder Server nicht antwortete. " +
        "Versuch es später noch einmal.",
      result_not_storable: "Das Ergebnis ließ sich nicht speichern. Melde das bitte der Administration.",
      lease_lost: "Der Auftrag wurde unterbrochen, weil sein Dienst ausfiel. Versuch es noch einmal.",
    },
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
    // the backend's code for every 503, not only the database's
    service_unavailable: "Der Dienst antwortet gerade nicht. Versuch es in ein paar Sekunden noch einmal.",
    validation_failed: "Die Eingabe ist so nicht gültig. Prüfe sie und versuch es noch einmal.",
    file_too_large: "Die Datei ist größer, als ein Upload sein darf. Verkleinere sie oder teile sie auf.",
    // a body cut at its limit before any route read it
    content_too_large: "Die Datei ist größer, als der Server annimmt. Verkleinere sie oder teile sie auf.",
    archive_too_large: "Die Datei ist ein Archiv, das ausgepackt zu groß wird. Ein gewöhnliches Word-Dokument ist das nicht.",
    unsupported_type:
      "Diese Art Datei kann der Kompetenzkartierer nicht lesen. Möglich sind PDF, Word (DOCX), RTF, HTML, " +
      "Markdown, Text (UTF-8) und Turtle.",
    file_missing: "Es kam keine Datei an. Wähle eine Datei aus und versuch es noch einmal.",
    title_invalid: "Der Titel enthält Steuer- oder unsichtbare Zeichen. Tippe ihn neu, statt ihn einzufügen.",
    title_too_long: "Der Titel ist zu lang. Kürze ihn auf höchstens 500 Zeichen.",
    url_invalid:
      "Diese Adresse ruft der Server nicht ab. Eine Webadresse beginnt mit https:// oder http:// " +
      "und enthält keine Zugangsdaten.",
    too_many_uploads: "Du hast gerade viele Dateien hochgeladen. Warte eine Minute und versuch es dann noch einmal.",
    too_many_imports: "Du hast gerade viele Adressen abgerufen. Warte eine Minute und versuch es dann noch einmal.",
  },
} as const;

type Messages = typeof messages;

/** The locale the UI formats its numbers, plural forms and dates in. */
export const LOCALE = "de-DE";

/** A moment as the pages show it, date and time ("22.10.2026, 23:07"): one format wherever it shows. */
export const momentFormat = new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" });

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
    Object.hasOwn(params, name) ? display(params[name]) : match,
  );
}

/** The app's wording at `key`, e.g. t("login.errors.empty"). */
export function t(key: string, params?: MessageParams): string {
  return translate(messages, key, params);
}

export type { Messages };
