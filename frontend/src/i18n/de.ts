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
      conversion: "Blöcke",
      document: "Dokument",
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
  // An entry's file converted into blocks (ConversionPanel.vue, conversionWords.ts). Not
  // "conversion": the guards read "conversion.status" in a template as a key of the group.
  conversions: {
    heading: "Umwandlung in Blöcke",
    intro:
      "Die Umwandlung liest die PDF-Datei in Blöcke – Absätze, Überschriften, Tabellen, Kopf- und Fußzeilen –, " +
      "jeden mit einer ID, über die spätere Schritte ihn zitieren. Sie läuft im Hintergrund weiter, auch wenn du " +
      "die Seite verlässt.",
    start: "In Blöcke umwandeln",
    // an event, not a state: the line stays once the job has ended
    started: "Die Umwandlung wurde gestartet.",
    startFailed: "Die Umwandlung wurde nicht gestartet.",
    loadFailed: "Der Stand der Umwandlung wurde nicht geladen.",
    jobLabel: "Umwandlung in Blöcke",
    // waiting with no job this reader may follow (another account's, an editor's start)
    following: "Die Umwandlung wartet oder läuft; diese Seite fragt nach, bis sie fertig ist.",
    done: "Die Umwandlung ist fertig: {pages} {pages|Seite|Seiten} gelesen.",
    failed: "Die Umwandlung ist gescheitert.",
    facts: {
      pages: "Seiten",
      engine: "Werkzeug",
      finishedAt: "Abgeschlossen",
    },
    findingsHeading: "Befunde",
    noFindings: "Die Umwandlung fand nichts Auffälliges im Text.",
    showBlocks: "Blöcke ansehen",
    // the job was cancelled before it ended (a conversion's error_code "cancelled")
    cancelled: "Sie wurde abgebrochen. Starte sie neu, wenn du die Blöcke brauchst.",
    // the same, on the entry's page, where the cancel is the reader's own doing: no failure
    stopped: "Die Umwandlung wurde abgebrochen. Starte sie neu, wenn du die Blöcke brauchst.",
    // its job failed again and again on the service, not on the file (a conversion's "handler_error")
    handlerError:
      "Sie ist mehrmals gescheitert, ohne dass sich die Datei als Ursache zeigte. Versuch es später noch " +
      "einmal; bleibt es dabei, melde es der Administration.",
    pageRange: "{from}–{to}",
    // a sign of the document, quoted in a sentence of the page
    quoted: "„{text}“",
    // what the conversion noticed in the text (backend FindingCode)
    findings: {
      unmapped_symbol:
        "{count} {count|Zeichen|Zeichen} einer Symbolschrift ({codepoint}) auf {pageCount|Seite|Seiten} {pages} " +
        "nicht zugeordnet; in den Blöcken {count|steht es|stehen sie} unverändert, oft als Aufzählungszeichen.",
      encoding_suspect:
        "Die Textebene wirkt beschädigt: {count} {count|verdächtiges Zeichen|verdächtige Zeichen} ({share} des Texts), " +
        "etwa {examples}. Prüfe die Blöcke, bevor du aus ihnen zitierst.",
      // text the conversion left out of the blocks, its signs counted, by why (backend DropReason)
      text_dropped: {
        vertical:
          "{count} {count|Zeichen|Zeichen} Text auf {pageCount|Seite|Seiten} {pages} {count|steht|stehen} " +
          "senkrecht oder gedreht, oft ein Vermerk am Rand; die Blöcke lassen {count|es|sie} aus.",
        off_page:
          "{count} {count|Zeichen|Zeichen} Text auf {pageCount|Seite|Seiten} {pages} {count|steht|stehen} " +
          "außerhalb der sichtbaren Seite; die Blöcke lassen {count|es|sie} aus, denn niemand sieht " +
          "{count|es|sie} beim Lesen.",
        tiny:
          "{count} {count|Zeichen|Zeichen} Text auf {pageCount|Seite|Seiten} {pages} {count|ist|sind} kleiner " +
          "als ein Punkt gesetzt und beim Lesen nicht zu sehen; die Blöcke lassen {count|es|sie} aus.",
        unplaced:
          "{count} {count|Zeichen|Zeichen} Text auf {pageCount|Seite|Seiten} {pages} {count|hat|haben} in der " +
          "Datei keinen gültigen Platz; die Blöcke lassen {count|es|sie} aus.",
      },
      // a finding the page has no words for yet, or whose numbers did not come
      other: "Ein Befund, den diese Seite noch nicht beschreibt: {code}.",
    },
  },
  // The blocks of an entry's converted file, a page at a time (ConversionView.vue)
  conversionPage: {
    // the page's heading until the entry names it
    heading: "Blöcke",
    back: "Zurück zum Eintrag",
    intro:
      "Die Blöcke der Datei, Seite für Seite, so wie die Umwandlung sie gelesen hat. Mit der ID eines Blocks " +
      "oder einer Tabellenzelle zitieren spätere Schritte die Stelle.",
    // the browser's title: the entry, and the page shown
    tabTitle: "{title}, Seite {page}",
    loadFailed: "Die Blöcke wurden nicht geladen.",
    pageFailed: "Die Blöcke dieser Seite wurden nicht geladen.",
    hiddenTitle: "Nur für die Redaktion",
    notConvertedTitle: "Noch keine Blöcke",
    failedBody: "Die Umwandlung ist gescheitert. Warum, und wie du sie neu startest, zeigt die Seite des Eintrags.",
    toEntry: "Zur Seite des Eintrags",
    pageHeading: "Seite {page} von {pages}",
    printed: "Gedruckte Seitenzahl: {printed}",
    // what a screen reader hears once a page the reader moved to shows
    announce: "Seite {page} von {pages}: {count} {count|Block|Blöcke}.",
    emptyTitle: "Auf dieser Seite steht kein Text",
    emptyBody: "Die Umwandlung fand hier weder Text noch Tabelle, etwa weil die Seite nur ein Bild trägt.",
    noPageTitle: "Diese Seite gibt es nicht",
    noPageBody: "Die Datei hat {pages} {pages|Seite|Seiten}.",
    firstPage: "Zur ersten Seite",
    pager: {
      // names the landmark, so a screen reader can list it and jump to it by name
      label: "Seiten",
      previous: "Vorige Seite",
      next: "Nächste Seite",
      field: "Seite",
      of: "von {pages}",
      go: "Anzeigen",
      invalid: "Gib eine Seite von 1 bis {pages} an.",
    },
    // what a block is, where it is more than text (backend BlockKind). Read as
    // messages.conversionPage.kind[value]: a value holds an underscore.
    kind: {
      table: "Tabelle",
      page_header: "Kopfzeile",
      page_footer: "Fußzeile",
    },
    bold: "fett",
    italic: "kursiv",
    // a table begun on an earlier page, at the top of a page it runs on to
    continued: "Fortsetzung von Seite {page}",
    tableStart: "Zum Anfang auf Seite {page}",
    table: {
      caption: "Tabelle {table}",
      continuedCaption: "Tabelle {table}, Fortsetzung",
      // a cell of a table that runs on from the page before
      onPage: "auf Seite {page}",
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
    // how long a job has run or waited, in whole minutes and hours (JobProgress.vue)
    runningFor: "läuft seit {minutes} {minutes|Minute|Minuten}",
    runningJustNow: "läuft seit weniger als einer Minute",
    runningForHours: "läuft seit {hours} {hours|Stunde|Stunden} und {minutes} {minutes|Minute|Minuten}",
    runningForHoursOnly: "läuft seit {hours} {hours|Stunde|Stunden}",
    waitingFor: "wartet seit {minutes} {minutes|Minute|Minuten}",
    waitingJustNow: "wartet seit weniger als einer Minute",
    waitingForHours: "wartet seit {hours} {hours|Stunde|Stunden} und {minutes} {minutes|Minute|Minuten}",
    waitingForHoursOnly: "wartet seit {hours} {hours|Stunde|Stunden}",
    // handed back to the queue after a try: it waits for the next
    waitingAgain: "wartet auf den nächsten Versuch",
    // a cancel from the page: asked first, then followed until the job has ended (JobProgress.vue)
    cancel: {
      button: "Abbrechen",
      name: "Auftrag „{label}“ abbrechen",
      title: "Auftrag abbrechen?",
      message:
        "„{label}“ wird beendet. Was schon fertig ist, bleibt erhalten; du kannst den Auftrag danach neu starten.",
      confirm: "Auftrag abbrechen",
      keep: "Weiterlaufen lassen",
      requested: "Abbruch angefordert – der Auftrag endet in Kürze.",
      ended: "Der Auftrag ist schon beendet.",
      gone: "Den Auftrag gibt es nicht mehr, oder er ist nicht deiner.",
      failed: "Der Abbruch hat nicht geklappt. Versuch es gleich noch einmal.",
    },
    // how far a job has come, as it reports it (JobProgress.vue, PROGRESS)
    progress: {
      checking: "{done} von {total} {total|Adresse|Adressen} angesehen",
      converting: "Die Datei wird in Blöcke umgewandelt; bei einer großen Datei dauert das einige Minuten.",
      // extract.run: the stages X1 to X5 of a document
      extract_profile: "Das Sprachmodell liest Titel, Geltung und Begriffe des Dokuments.",
      // a count of 0 too: the lexicon's patterns may type every heading
      extract_outline: "Die Gliederung wird gebaut. Überschriften, die das Sprachmodell einordnet: {headings}.",
      extract_segments: "Das Dokument wird in {units} {units|Arbeitspaket|Arbeitspakete} geteilt.",
      extract_frame:
        "Das Sprachmodell liest die Rahmenteile: Kompetenzmodelle, Operatoren, Legenden, Regeln und Ziele.",
      // a unit is done once written: those done stay when the job stops
      extract_statements:
        "Das Sprachmodell liest die Aussagen der Arbeitspakete: {done} von {total} {total|Paket|Paketen} fertig.",
      // X5 asks no model; its SHACL check of a long document may take minutes
      check_document:
        "Das Dokument wird geprüft: ob jeder Wortlaut in seinen Blöcken steht, ob die Angaben stimmig sind und ob sie den Regeln des Curriculum-Kerns genügen. Bei einem langen Dokument kann das einige Minuten dauern.",
      // X6: only the work packages with findings, each once a repair
      repair_units:
        "Das Sprachmodell liest die Arbeitspakete mit Befunden noch einmal: {done} von {total} {total|Paket|Paketen} fertig.",
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
      too_dense:
        "Eine Seite der PDF-Datei trägt weit mehr Text, als eine Seite fassen kann; die Datei wurde nicht " +
        "umgewandelt. Prüfe, ob sie das Dokument selbst ist, und lade sonst eine andere Fassung hoch.",
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
      crashed:
        "Die Umwandlung ist an dieser Datei gescheitert; ein neuer Versuch ginge ebenso aus. Speichere die Datei " +
        "in einem PDF-Programm neu und lade sie noch einmal hoch, oder melde es der Administration.",
      not_pdf: "Die gespeicherte Datei ist keine PDF-Datei, auch wenn sie als eine angegeben ist. Lade sie als PDF neu hoch.",
      file_gone: "Die Datei fehlt im Speicher des Servers. Melde das bitte der Administration.",
      handler_error:
        "Der Auftrag ist mehrmals gescheitert, etwa weil ein fremder Server nicht antwortete. " +
        "Versuch es später noch einmal.",
      result_not_storable: "Das Ergebnis ließ sich nicht speichern. Melde das bitte der Administration.",
      lease_lost: "Der Auftrag wurde unterbrochen, weil sein Dienst ausfiel. Versuch es noch einmal.",
      // extract.run (backend app/pipeline/run.py, asking.py, unit_question.py)
      // charged to the document's owner, whoever started it; a new start goes on from the last stage done
      budget_exhausted:
        "Das Token-Budget des Kontos, dem das Dokument gehört, ist aufgebraucht; die Extraktion ist beendet. " +
        "Was schon fertig war, bleibt erhalten: Mit mehr Budget setzt ein neuer Start dort fort, wo sie endete. " +
        "Bitte die Administration um mehr Budget.",
      model_unanswered:
        "Das Sprachmodell hat auch nach mehreren Versuchen keine verwertbare Antwort geliefert. Starte die " +
        "Extraktion später noch einmal; scheitert sie wieder, melde es der Administration.",
      model_not_configured: "Für das Sprachmodell ist kein Zugang eingerichtet. Melde das bitte der Administration.",
      // not even one section beside the title pages and the frame fits the model's context
      prefix_too_long:
        "Ein Abschnitt des Dokuments ist zu lang, als dass das Sprachmodell ihn zusammen mit Titelei und " +
        "Rahmenteilen lesen könnte. Teile das Dokument auf, oder melde es der Administration.",
      document_gone: "Das Dokument gibt es nicht mehr; die Extraktion ist entfallen.",
      // a repair needs the extraction to have come to its check (X5)
      document_not_checked:
        "Die Extraktion des Dokuments ist noch nicht bis zur Prüfung gelaufen. Setze sie erst fort; danach " +
        "lässt es sich reparieren und erneut prüfen.",
      // the editors took away a node a stage still wrote to, while it waited for the tree
      node_gone:
        "Ein Knoten wurde gelöscht, an dem die Stufe noch schreiben wollte. Eine neue Reparatur " +
        "lässt ihn aus; bleibt die Extraktion daran hängen, melde es der Administration.",
      // a document the extraction wrote ends done: this one holds what no extraction wrote
      document_has_tree:
        "Am Dokument stehen schon Knoten oder Spezifikationen, die keine Extraktion angelegt hat; die " +
        "Extraktion schreibt nur in ein Dokument ohne sie. Lege dafür aus der Quelle ein neues Dokument an.",
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
    too_many_conversions:
      "Du hast gerade viele Umwandlungen gestartet. Warte eine Minute und versuch es dann noch einmal.",
    // an entry's content: its file and what the conversion read from it
    file_hidden: "Die Datei dieses Eintrags und was aus ihr gelesen wurde, sieht nur die Redaktion.",
    no_file: "Der Eintrag hat noch keine Datei. Sie kommt mit dem Hochladen oder dem Abruf seiner Adresse.",
    not_pdf: "Bisher werden nur PDF-Dateien in Blöcke umgewandelt.",
    no_conversion: "Die Datei wurde noch nicht in Blöcke umgewandelt. Die Umwandlung startest du auf der Seite des Eintrags.",
    not_converted: "Die Umwandlung ist noch nicht fertig. Wie weit sie ist, zeigt die Seite des Eintrags.",
    no_such_page: "Diese Seite gibt es in der Datei nicht.",
    // a document and its extraction (backend app/api/documents.py), and a model job's admission (limits.py)
    no_document: "Dieses Dokument gibt es nicht, oder dein Konto sieht es nicht.",
    not_owner: "Extraktion und Reparatur startet nur, wer das Dokument angelegt hat.",
    unknown_sector: "Diesen Bildungsbereich kennt die Anwendung nicht.",
    unknown_region: "Eines der gewählten Länder kennt die Anwendung nicht.",
    no_budget: "Dein Konto hat kein Token-Budget mehr für das Sprachmodell. Bitte die Administration um mehr Budget.",
    too_many_jobs: "Dein Konto hat schon viele Aufträge laufen. Versuch es in einer Minute noch einmal.",
    too_many_starts: "Zu viele Starts in kurzer Zeit. Versuch es in einer Minute noch einmal.",
    not_checked: "Die Extraktion des Dokuments ist noch nicht bis zur Prüfung gelaufen. Setze sie erst fort.",
    nothing_to_repair: "Kein Arbeitspaket hat mehr Befunde, die eine Reparatur angeht.",
    // an editor's change to a document's nodes and statements (backend app/api/edit_answers.py and its routes)
    no_node: "Diesen Knoten gibt es nicht mehr, oder dein Konto sieht ihn nicht.",
    no_statement: "Diese Aussage gibt es nicht mehr, oder dein Konto sieht sie nicht.",
    stale_revision: "Jemand hat das inzwischen geändert. Sieh dir den neuen Stand an und entscheide dann.",
    invalid_field: "Ein Feld lässt sich so nicht setzen. Prüfe die markierte Eingabe.",
    anchor_missing: "Eine Aussage braucht mindestens eine Fundstelle: Blöcke der Quelle oder eine Seite.",
    job_open: "Zu diesem Dokument läuft gerade ein Auftrag. Das geht wieder, sobald er fertig ist.",
    frozen: "Das Dokument ist festgeschrieben. Änderungen gehen nur in einer Entwurfskopie.",
    no_form: "Für den Bildungsbereich dieses Dokuments gibt es kein Formular zum Bearbeiten.",
    not_extracted:
      "Die Extraktion hat noch nicht alle Arbeitspakete gelesen. Erst wenn der Eigentümer sie fortgesetzt hat, " +
      "lässt sich das Dokument bearbeiten.",
    not_editor: "Das darf nur die Redaktion.",
    // a document's work and metadata, frozen and copied (backend app/api/document_meta.py, freeze.py)
    named:
      "Das Dokument hat schon seine IRI. Werk, Herausgeber und Fassung, aus denen sie besteht, bleiben, " +
      "wie sie sind.",
    no_work: "Dieses Werk gibt es nicht.",
    incomplete:
      "Zum Festschreiben fehlt noch etwas: das Werk mit Land und Kurztitel, der Herausgeber oder die Fassung " +
      "(beide mit mindestens einem lateinischen Buchstaben oder einer Ziffer).",
    no_iri_base: "Der Dienst hat keine IRI-Basis (IRI_BASE). Ohne sie lässt sich nichts festschreiben.",
    check_owed:
      "Die Prüfung steht aus: Das Dokument wurde noch nicht oder nicht seit den letzten Änderungen geprüft. " +
      "Prüfe es – oder setze die Extraktion fort, wenn sie nie bis zur Prüfung kam –, dann lässt es sich " +
      "festschreiben.",
    has_violations: "Die Befunde nennen Verstöße. Festschreiben geht nur, wenn du sie ausdrücklich annimmst.",
    iri_taken: "Ein anderes Werk oder Dokument hat diese IRI schon.",
    not_frozen: "Das Dokument ist noch nicht festgeschrieben. Ändere es direkt.",
    not_latest: "Es gibt schon eine spätere festgeschriebene Revision. Kopiere diese.",
    draft_open: "Zu diesem Dokument ist schon ein Entwurf offen.",
    vocabulary_changed:
      "Das Vokabular hat sich seit dem Festschreiben geändert: Eine Zeile des Dokuments passt nicht mehr dazu. " +
      "Bitte die Administration, das Vokabular zu prüfen.",
    not_extractable: "Eine Entwurfskopie wird nicht extrahiert. Bearbeite und prüfe sie.",
  },
  // Documents of a conversion and their extraction (ExtractionStart.vue, DocumentView.vue, SourceDocuments.vue)
  documents: {
    // by the notations of cv:EducationSectors (tests/documentWords.test.ts)
    sectors: {
      elementary: "Elementarbildung",
      school: "Schulbildung",
      vocational: "Berufsbildung",
      higher: "Hochschulbildung",
      adult: "Erwachsenen- und Weiterbildung",
    },
    stages: {
      X1: "Profil und Gliederung",
      X2: "Arbeitspakete",
      X3: "Rahmenteile",
      X4: "Aussagen",
      X5: "Prüfung",
      X6: "Reparatur",
    },
    runStates: {
      done: "fertig",
      failed: "gescheitert",
      budget_exhausted: "Budget aufgebraucht",
      running: "läuft",
      abandoned: "abgebrochen",
    },
    // why a run failed, where it names a type of failure rather than a code (DocumentRuns.vue); the
    // codes are a job's (jobs.failures), anything else the server's words, quoted
    runFailures: {
      LeaseLost: "Der Lauf ging nicht weiter: Der Auftrag wurde abgebrochen oder vom Server neu vergeben.",
    },
    // A document's work packages (DocumentUnits.vue, backend app/pipeline/units.py)
    units: {
      heading: "Arbeitspakete",
      table: "Arbeitspakete des Dokuments",
      loading: "Die Arbeitspakete werden geladen.",
      loadFailed: "Die Arbeitspakete ließen sich nicht laden.",
      noneTitle: "Noch keine Arbeitspakete",
      noneBody: "Sie stehen fest, sobald die Extraktion das Dokument geteilt hat.",
      columns: { key: "Paket", path: "Abschnitt", pages: "Seiten", state: "Stand" },
      // E0: what stands before the first heading; a document without headings is one package
      titlePages: "Titelei",
      wholeDocument: "Ganzes Dokument",
      page: "S. {first}",
      pages: "S. {first}–{last}",
      states: {
        done: "fertig, {statements} {statements|Aussage|Aussagen}",
        open: "offen",
        frame: "Rahmenteil, wird typisiert gelesen",
        none: "wird nicht gelesen",
      },
      // the packages whose statements the extraction reads
      summary: "{done} von {total} {total|Paket|Paketen} mit Aussagen fertig.",
    },
    // What the stages found on a document (DocumentFindings.vue, backend app/api/document_findings.py)
    findings: {
      heading: "Befunde",
      table: "Befunde des Dokuments",
      loading: "Die Befunde werden geladen.",
      loadFailed: "Die Befunde ließen sich nicht laden.",
      noneTitle: "Keine Befunde",
      noneBody: "Die Stufen der Extraktion haben an diesem Dokument bisher nichts gefunden.",
      columns: { severity: "Schwere", finding: "Befund", focus: "Betrifft" },
      // by Severity (backend app/domain/l1.py; tests/documentWords.test.ts)
      severities: { violation: "Verstoß", warning: "Warnung", info: "Hinweis" },
      counts: {
        violation: "{count} {count|Verstoß|Verstöße}",
        warning: "{count} {count|Warnung|Warnungen}",
        info: "{count} {count|Hinweis|Hinweise}",
      },
      truncated: "Gezeigt werden die ersten {shown} von {total} {total|Befund|Befunden}.",
      // the kind of the row a finding is about; another kind is shown as the server names it
      kinds: {
        document: "Dokument",
        node: "Knoten",
        statement: "Aussage",
        frame_part: "Rahmenteil",
        specification: "Spezifikation",
        anchor: "Anker",
        variant: "Variante",
      },
      // what a finding is about: its kind, its wording or title, the work package it names
      about: "{kind} „{label}“",
      inUnit: "{what}, Paket {unit}",
      // by the rule's name without its stage: the reading of an answer names its rules alike at X1,
      // X3, X4 and X6 (tests/findingWords.test.ts); SHACL's messages as the server gives them
      rules: {
        // X5's checks
        wording_not_found: "Der Wortlaut steht nicht in den Blöcken, auf die er verweist.",
        unit_without_statements: "Das Arbeitspaket wurde ganz gelesen, enthält aber keine Aussage.",
        shacl_timeout: "Die Regelprüfung (SHACL) dauerte zu lange; das Ergebnis bleibt gesperrt.",
        rule_bounds: "Die Grenzen einer Regel widersprechen sich.",
        retired_value: "Ein Wert, den die Vokabulare nicht mehr führen.",
        heading_as_statement: "Eine Aussage, die nur die Überschrift ihres Knotens wiederholt.",
        // what the reading of the model's answer found
        too_many_statements: "Die Antwort enthielt mehr Aussagen, als gelesen werden; die übrigen fehlen.",
        statement_without_block: "Eine Aussage ohne gültige Blockkennung; sie fehlt.",
        statement_without_wording: "Eine Aussage ohne Wortlaut; sie fehlt.",
        statement_too_long: "Eine Aussage über der Längengrenze; sie fehlt.",
        unknown_block: "Eine Blockkennung, die die Umwandlung nicht hat.",
        block_outside_unit: "Ein Block außerhalb des gefragten Arbeitspakets.",
        unknown_value: "Ein Wert, den die Auswahlliste nicht hat.",
        unknown_key: "Eine Kennung, die die Frage nicht genannt hat.",
        subkind_mismatch: "Eine Unterart, die nicht zur Aussageart gehört.",
        value_cut: "Ein Wert, auf die Höchstlänge gekürzt.",
        value_from_surroundings: "Ein Wert aus der Umgebung, nicht aus dem Wortlaut der Aussage.",
        target_not_content: "Ein Verweis auf eine Aussage, die keine Inhaltsaussage ist.",
        part_without_block: "Ein Rahmenteil ohne gültige Blockkennung; es fehlt.",
        statement_outside_frame: "Eine Aussage außerhalb der Rahmenteile; sie wird mit den Arbeitspaketen gelesen.",
        statement_without_node: "Eine Aussage der Titelei, die kein Knoten aufnimmt.",
        target_elsewhere: "Ein Verweis auf Inhalt an einem anderen Knoten oder an keinem.",
        // a stage's own
        unanswered: "Das Sprachmodell gab keine Antwort in der verlangten Form.",
        empty_answer: "Die Antwort enthielt keine neue lesbare Aussage, obwohl das Paket welche hat; es bleibt, wie es war.",
        pattern_timeout: "Ein Suchmuster des Lexikons brauchte zu lange und wurde übergangen.",
      },
      // the owner's repair (FindingsRepair.vue, backend POST /documents/{id}/repair)
      repair: {
        offer:
          "{count} {count|Arbeitspaket hat|Arbeitspakete haben} Befunde, die eine Reparatur angeht: Das " +
          "Sprachmodell liest {count|es|sie} noch einmal, danach wird das Dokument erneut geprüft. " +
          "Was die Redaktion geändert hat, bleibt.",
        start: "Reparieren",
        started: "Die Reparatur ist gestartet; ihr Stand steht unter „Extraktion“.",
        // the start gave back the document's extraction, waiting or running
        extractionRunning: "Es läuft schon eine Extraktion des Dokuments; ihr Stand steht unter „Extraktion“.",
        failed: "Die Reparatur wurde nicht gestartet.",
      },
    },
    untitled: "Dokument ohne Titel",
    start: {
      heading: "Extraktion",
      intro:
        "Aus der fertigen Umwandlung wird ein Dokument; das Sprachmodell liest sein Profil, seine Gliederung, " +
        "seine Rahmenteile und die Aussagen jedes Arbeitspakets; danach prüft die Anwendung das Ergebnis, " +
        "ohne Sprachmodell. Fertige Pakete bleiben, auch wenn die " +
        "Extraktion abbricht; ein neuer Start setzt dort fort. " +
        "Für eine PDF läuft bei dir höchstens eine Extraktion zugleich – läuft schon eine, führt der Knopf zu ihr. " +
        "Du kannst sie jederzeit abbrechen.",
      sector: "Bildungsbereich",
      sectorChoose: "Bereich wählen",
      sectorMissing: "Wähle den Bildungsbereich des Dokuments.",
      regions: "Länder",
      regionsHint: "Wofür das Dokument gilt; „Bund“, wenn es für alle Länder gilt.",
      submit: "Extraktion starten",
      failed: "Die Extraktion wurde nicht gestartet.",
    },
    page: {
      loadFailed: "Das Dokument wurde nicht geladen.",
      notFoundTitle: "Dieses Dokument gibt es nicht",
      notFoundBody: "Oder dein Konto sieht es nicht. Deine Dokumente findest du auf den Seiten ihrer Registereinträge.",
      facts: {
        heading: "Angaben",
        sector: "Bildungsbereich",
        regions: "Länder",
        source: "Registereintrag",
        created: "Angelegt",
      },
      sourceLink: "Zum Registereintrag",
      noRegions: "keine angegeben",
      extraction: "Extraktion",
      jobLabel: "Extraktion",
      // the document's job a repair started (documentJobs.ts)
      repairLabel: "Reparatur",
      none: "Noch keine Extraktion.",
      lastStatus: "Letzte Extraktion: {status}",
      lastRepairStatus: "Letzte Reparatur: {status}",
      // its job is another's to follow, or gone: the document is asked after (DocumentExtraction.vue)
      following: "Der Stand wird weiter abgefragt, bis die Extraktion endet.",
      started: "Die Extraktion ist gestartet; ihr Stand steht hier.",
      // a start gave back the document's repair, waiting or running (one job of a document at a time)
      repairRunning: "Es läuft schon eine Reparatur des Dokuments; ihr Stand steht hier.",
      // the start form led here: for this PDF one ran already, and what the form chose was not taken
      ledToRunning:
        "Für diese PDF lief schon eine Extraktion – hier ist sie. Bereich und Länder aus dem Formular " +
        "wurden nicht übernommen; ist sie beendet, kannst du ein weiteres Dokument anlegen.",
      resume: "Extraktion fortsetzen",
      resumeFailed: "Die Extraktion wurde nicht gestartet.",
      notOwn: "Die Extraktion startet nur, wer das Dokument angelegt hat.",
      runs: "Läufe der Stufen",
      runsTable: "Tabelle der Läufe",
      noRuns: "Noch keine Läufe.",
      columns: {
        stage: "Stufe",
        attempt: "Versuch",
        state: "Stand",
        started: "Beginn",
        finished: "Ende",
        failure: "Grund",
      },
    },
    list: {
      heading: "Dokumente",
      untitled: "Dokument ohne Titel vom {made}",
      empty: "Aus diesem Eintrag ist noch kein Dokument angelegt.",
      loadFailed: "Die Dokumente wurden nicht geladen.",
    },
    tree: {
      loadFailed: "Der Baum des Dokuments wurde nicht geladen.",
      // cv:ReviewStatuses by notation without its "rev_" (reviewStatus.ts)
      statuses: { proposed: "Vorgeschlagen", confirmed: "Bestätigt", rejected: "Verworfen" },
      filter: {
        label: "Nach Prüfstand filtern",
        option: "{label}: {nodes} {nodes|Knoten|Knoten}, {statements} {statements|Aussage|Aussagen}",
        all: "Alle zeigen",
      },
    },
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
