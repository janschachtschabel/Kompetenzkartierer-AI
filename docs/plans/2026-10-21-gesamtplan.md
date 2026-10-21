# Plan: Neubau auf Curriculum-Kern 1.0 – Kompetenzkartierer-AI

Stand 22.10.2026, Fassung 5. Am 22.10.2026 zur Umsetzung freigegeben; Detailplan für M0:
[`2026-10-22-m0-fundament.md`](2026-10-22-m0-fundament.md).
Fassung 5 legt das Embedding-Modell fest (§7.2, offene Frage 2): zweistufig, schnell mit
`m2v-gte-256-edu`, genauer mit `multilingual-e5-small` über ONNX, beides lokal.
Fassung 4: keine Datenübernahme aus der alten App (dort liegen nur Testextrakte); das
Wikipedia-Archiv (ZIM) ist eingeplant, auch als Wissen zu Themen und Entitäten; Markdown-
Extrakte und Zitate lassen sich für Dritte verbergen (§7.4).
Fassung 3 ergänzt §7.2–7.5: möglichst wenig Dritte live (lokale Abzüge per Sidecar,
schmales Hauptvolumen), Zugang ohne Konto für Nachschlagen und Suche, KI nur mit Token,
Umgang mit den Rechten an Wortlauten und den Vergleichsdatensatz als Quelle für den
Importer.
Fassung 2 übernimmt die Vorgaben vom 21.10.2026:
- LLM nur OpenAI-kompatibel wie im heutigen Kompetenzkartierer, ohne B-API, mit änderbarer
  Basis-URL für andere Anbieter;
- keine Anbindung an WLO oder edu-sharing; eine Inhaltssuche über deren API kommt später;
- eigenes Repository [Kompetenzkartierer-AI](https://github.com/janschachtschabel/Kompetenzkartierer-AI),
  geklont in den Unterordner `kompetenzkartierer-ai/`.

Grundlage sind vier Erkundungen vom 21.10.2026 (Backend, Frontend, Datenmodell gegen Kern 1.0,
compendious-text-fastapi), die Recherche im alten Repository unter `docs/recherche/` mit dem Ergebnis
`docs/recherche/ontologien/ergebnis/` (hier als `ontology/`) (Kern 1.0, Profile,
Vokabulare, Prüfregeln, Rechercheergebnisse), die Konkurrenzanalyse und die Betriebsvorgaben
des Technik-Teams („Dienste an den Maschinenraum übergeben“).

## Kurzantworten

- **Umbau oder Neubau?** Neubau im Unterordner `kompetenzkartierer-ai/`, einem eigenen
  Repository (Kompetenzkartierer-AI). Die heutige
  App `curriculum-extractor/` bleibt unverändert stehen und in Betrieb, bis der Neubau sie
  ablöst. Übernommen wird nur, was sich bewährt hat, und zwar als geprüfte Kopie mit ihren
  Tests, nicht als Abhängigkeit.
- **Warum kein Umbau?**
  - Das Datenmodell der App trägt Kern 1.0 nicht. Heute gibt es einen Baum je Lauf, einen
    Textwert je Eigenschaft, Kanten mit festem Typ und genau einen Bildungsbereich je Profil.
  - Der Betrieb ist auf genau eine Instanz gebaut. Die Datenbank ist eine SQLite-Datei, die
    Warteschlange liegt im API-Prozess, Zähler, Caches und Sperren liegen im Speicher.
    Quoten, Link-Regeln und Baumprüfungen sind nur richtig, weil SQLite alle Schreiber global
    sperrt.
  - Ein Umbau hieße zwei Migrationen nacheinander: erst SQLite → PostgreSQL samt
    Zustandslosigkeit (35–60 PT), dann das neue Datenmodell quer durch Extraktion, Export,
    Import, Themen und Recherche. 201 von 316 Backend-Testdateien hängen an SQLite, rund
    42.000 Zeilen Frontend-Tests an den heutigen API-Formen. Beide müssten ohnehin neu
    entstehen.
- **Datenhaltung:** PostgreSQL ist die führende Datenhaltung, mit Tabellen nach den drei
  Schichten des Kerns, JSONB für Profilfelder und Rohantworten, Volltext, `pg_trgm` und
  `pgvector`. RDF ist Austauschformat (Export, MEM, SHACL je Dokument), kein Primärspeicher.
  Apache AGE vorerst nicht.
- **Betrieb:** Die Vorgaben des Technik-Teams gelten ab dem ersten Commit, in der Variante
  ohne B-API: eigene Auth-Schicht, LLM-Schlüssel als Secret. Die Betriebsseite von
  `compendious-text-fastapi` (zwei Ports, Metriken, Logs, Tracing, Image, Helm-Values) dient
  als Vorlage.
- **LLM:** wie im heutigen Kompetenzkartierer: OpenAI-kompatibel, Basis-URL änderbar
  (Standard `https://api.openai.com/v1`), Standardmodell `gpt-6-luna`.
- **Wenig Dritte live:** Zur Anfragezeit ruft die App keinen Dritten auf. Wikidata, GND,
  ESCO, KldB und optional Wikipedia kommen als lokale Abzüge über Sidecars in eigene
  Volumes; live bleibt nur das Sprachmodell in Jobs (§7.2).
- **Zugang:** Anmeldung wie heute über Tokens, die ein Admin vergibt. Nachschlagen und Suchen
  sind per Option auch ohne Konto möglich; KI nur mit Token und Kontingent (§7.3).
- **Wortlaute:** bleiben gespeichert und für die Redaktion sichtbar. Ihre Anzeige und
  Weitergabe steuert ein Rechtestatus je Quelle, der sich jederzeit sperren lässt (§7.4).
- **Aufwand:** sieben Meilensteine, zusammen etwa 170–240 Personentage (PT). Der erste
  Meilenstein M0 liefert in 15–22 PT ein lauffähiges, clusterfähiges Gerüst.

## 1. Ziel

Eine App, die Lehrpläne aller Bildungsbereiche nach Curriculum-Kern 1.0 erfasst (Extraktion
oder Formular), sie an Kompetenz-, Niveau- und Normdatenschemata andockt, Kanten zwischen
Inhalten, Kompetenzen und Lehrplänen bildet und daraus die Anwendungsfälle einer
Wissenslandkarte bedient. Sie läuft zustandslos und horizontal skalierbar im Cluster.

## 2. Ausgangslage

### 2.1 Backend der heutigen App

| Befund | Beleg |
|---|---|
| 306 Module, rund 67.000 Zeilen; 316 Testdateien, rund 107.000 Zeilen; CI verlangt 96 % Abdeckung | `curriculum-extractor/backend` |
| SQLite über rohes `sqlite3`, 22 Tabellen, 8 Trigger, 51 Migrationsschritte (für PostgreSQL wertlos) | `db_schema.py`, `db_migrations.py` |
| Alle Schreiber über `BEGIN IMMEDIATE`; Quoten, Link-Regeln und Zyklusprüfung beim Verschieben sind nur dadurch richtig | `db_base.py:182`, `services/quota.py:260–275` |
| Worker als asyncio-Task im API-Prozess; beim Start werden alle laufenden Jobs zurückgesetzt, keine Lease | `main.py:236`, `db_jobs.py:498–519` |
| Rund 30 Stellen mit Zustand im Speicher (Limiter, Caches, Download-Tickets, Budgetzähler) | Bericht Backend |
| OpenAPI abgeschaltet, ein Port, kein `/ready`, kein `/metrics`, keine strukturierten Logs, kein Tracing | `main.py:384–386`, Dockerfile |
| Fachlich reif und nachnutzbar: Konvertierung, LLM-Schicht, Ankersuche, MEM-Client, Anreicherungsquellen, Dokument-Export, Abrechnungslogik | Bericht Backend, Tabelle Bausteine |

### 2.2 Frontend der heutigen App

| Befund | Beleg |
|---|---|
| Schlanker Stack (Vue, vue-router, selbst gehostete Schriften), keine UI-, Store- oder Diagramm-Bibliothek | `frontend/package.json` |
| Hohe Querschnittsqualität: Design-Tokens mit Dunkelmodus, eigenes `t()`, axe- und Kontrasttests, Schutztests gegen fest eingetippte Texte | `src/style.css`, `src/i18n/de.ts`, `tests/` |
| Allgemein gebaute Bausteine: Baum, Matrizen, Dialoge, Fortschritt, Quellenbeleg, Teilen | Bericht Frontend, Abschnitt 4 |
| Arbeitsbereichs-Views hängen an Dokument → Lauf → Knoten mit flachen Text-Eigenschaften; `RunCard` mit 24 Props und 17 Events, bis 15 Aktionen je Lauf | `RunCard.vue`, `DocumentDetailView.vue` |
| Keine Rollen für Lernende und Lehrkräfte, Anmeldung nur per API-Schlüssel, keine Graph-Visualisierung | Bericht Frontend, Abschnitt 6 |

### 2.3 Datenmodell gegen Kern 1.0

Die größten Lücken: Trennung von Knoten und Aussage mit Pflichtfeldern, Dokument und
Spezifikation n:m mit Varianten und Verwendung, n-äre Wertobjekte (Niveau, Zeit, Umfang,
Regel, Prüfung), eine eigene Konzept- bzw. Hub-Schicht, eine einheitliche Kantentabelle mit
Herkunft, Methode, Konfidenz und Prüfstand, das Lexikon der Länder- und Profilhinweise,
stabile IRIs über Läufe und Fassungen. MEM-Schule passt strukturell auf den Kern; für den
Import fehlen eine Herkunft „Import“ und eine Regel für Fundstellen.

### 2.4 compendious-text-fastapi

- Erfüllt alle Betriebsvorgaben mit Beleg im Code: zwei Ports, Prometheus mit 25 Alarmregeln
  und promtool-Tests, JSON-Logs, B3 und `x-client-trace-id`, gehärtetes Image,
  Helm-Values-Vorlage, Übergabedokument zur T6-Checkliste.
- Entity Linking: Erkennung per LLM oder spaCy; Wikidata und GND nur aus lokalen
  SQLite-Indizes, die Sidecars aus den Dumps bauen und atomar tauschen. Präzision 0,94 mit
  LLM-Prüfung. Die Index-Bauer brauchen nur die Standardbibliothek; die volle Verknüpfung
  hängt an Wikipedia-ZIM-Archiven (rund 19 GB).
- Der LLM-Client ist fest auf die B-API zugeschnitten und wird nicht übernommen; maßgeblich
  ist die LLM-Schicht des heutigen Kompetenzkartierers.
- Die App hängt an edu-sharing (Materialien, Sammlungen). Übernommen werden nur Muster und
  unabhängige Bausteine, keine Dienstanbindung.

### 2.5 Lehren aus der Vergleichs-App

Die Vergleichs-App (Antares/edupool, mit dem Agenten Kimi gebaut) zeigt, was Automatisierung
an Breite schafft: 19 Länder, rund 150.000 wörtliche Belege in drei Monaten. Sie zeigt auch
die Schwächen: KI-Unterthemen und Kernräume stehen neben Lehrplantext, die Prüfung ist nur
ein Teilstring-Abgleich, 98,8 % der Mapping-Kanten heißen „voll“, Vergleiche laufen über
Wortüberschneidung, Querverbindungen verweisen über Titel, die IDs sind hierarchisch, der
Download ist älter als die App. Daraus folgen die Regeln in Abschnitt 7.

## 3. Ansätze

**Ansatz A: Umbau im Bestand**
- Wie: erst PostgreSQL und Zustandslosigkeit nachrüsten, dann Datenmodell, Extraktion,
  Export und Views schrittweise auf Kern 1.0 umstellen.
- Vorteile: eine Codebasis; vorhandene Tests sichern die Zwischenstände.
- Nachteile: zwei große Migrationen nacheinander, die erste auf ein Modell, das danach ersetzt
  wird. Die globale Schreibsperre muss überall gleichwertig ersetzt werden, sonst brechen
  Quoten und Regeln still. Die meisten Tests müssen trotzdem neu geschrieben werden.
- Aufwand: etwa 145–225 PT, mit der größten Unsicherheit.
- Risiko: hoch; am Ende bleibt Altlast (Lauf als Zentrum, Module je Ontologie im Export).

**Ansatz B: Neubau im Unterordner mit Übernahme des Bewährten (Empfehlung)**
- Wie: neues Backend und Frontend unter `kompetenzkartierer-ai/`, Datenmodell und Pipeline direkt
  nach Kern 1.0, Betriebsseite nach dem Vorbild compendious. Fachbausteine werden mit ihren
  Tests kopiert und angepasst. Die alte App läuft weiter, bis M6 sie ablöst.
- Vorteile: sauberes Zielbild ohne Zwischenmigration; Clusterfähigkeit von Anfang an; jeder
  Meilenstein liefert lauffähige Software; Risiko für den laufenden Betrieb null.
- Nachteile: Funktionsgleichstand erst nach M2; die alte App bleibt bis dahin eingefroren
  stehen.
- Aufwand: etwa 170–240 PT.
- Risiko: mittel; beherrschbar über kleine Meilensteine.

**Ansatz C: neue Dienste neben der alten App**
- Wie: Die alte App extrahiert weiter; ein neuer Graph-Dienst liest ihre Exporte und baut
  daraus die Wissenslandkarte.
- Vorteile: erste Wissenslandkarte schnell (etwa 60–90 PT).
- Nachteile: zwei Datenmodelle, die auseinanderlaufen; Kern 1.0 verlangt Änderungen an der
  Extraktion selbst (Blöcke, Aussagen, Zerlegung, Kanten mit Herkunft); die Betriebsmängel
  der alten App bleiben.
- Risiko: hoch für die Datenqualität.

**Empfehlung: B.** A kostet ähnlich viel, endet aber mit Altlast und hat das höhere Risiko.
C ist nur als Zwischenlösung tragbar, und eine braucht es nicht, weil die alte App bis M6
weiterläuft.

## 4. Umfang

**Im Umfang**
- Alle fünf Bildungsbereiche nach Kern 1.0 (Schule, Elementar, Beruf, Hochschule,
  Erwachsenenbildung) mit Profilen, Vokabularen und Lexikon aus `ergebnis/`.
- Phase 1: Quellen erfassen, Extraktion (X0–X5) und Formular-Editor, Andocken (N1, N2),
  Anreicherung mit Berufen und Kompetenzen, Entity-Links zu Wikidata und GND,
  Abrechnung von Tokens und Seiten, MEM-Schule Import, Export und Bearbeitung.
- Phase 2: Kanten (G1) und die Abfragen der Wissenslandkarte (Abschnitt 8).
- Phase 3: Rollen und Sichten (Lernende, Lehrkräfte, Gesamtansicht), Visualisierung,
  Teilen und öffentliche Seiten, Suche und Auswertung, offene Daten; eine Schnittstelle, an
  die später eine Inhaltssuche über die API von WLO/edu-sharing andockt.
- Betrieb nach den Vorgaben des Technik-Teams, Übergabe an T6.

**Nicht im Umfang (Fassung 1)**
- Andere Staaten als Deutschland. Das Datenmodell bleibt dafür offen (`land:` erweiterbar,
  mehrsprachige Felder), Inhalte folgen nach M6.
- Selbsttests mit Bewertung und das anonyme Senden von Ergebnissen an die Forschung. Beides
  braucht ein Datenschutzkonzept für Minderjährige und kommt frühestens nach M5.
- Änderungen an der alten App und eine Datenübernahme: In der alten App liegen nur
  Testextrakte.
- Jede direkte Anbindung an WLO oder edu-sharing: keine B-API, keine Anmeldung über
  edu-sharing, keine Dienste aus dem WLO-Umfeld. Die App entsteht unabhängig; später dockt
  nur eine Inhaltssuche über deren API an.
- Ein öffentlicher SPARQL-Endpunkt ist optional (M5) und nur für veröffentlichte Daten.

## 5. Leitplanken

- **Ontologie als Spezifikation:** Kern 1.0 in `docs/recherche/ontologien/ergebnis/` ist die
  Quelle der Wahrheit. Vokabulare, Profile, Lexikon und Prüfregeln werden aus den TTL-Dateien
  geladen, JSON-Schemas der LLM-Stufen werden daraus erzeugt (`werkzeuge/erzeuge_schemas.py`).
  Kein Vokabular wird im Code abgeschrieben.
- **Betriebsvorgaben T6** gelten ab M0: OpenAPI mit Name und Beschreibung, zwei Ports,
  asynchrone Jobs ab 30 s, eigene Auth-Schicht (Variante ohne B-API), Prometheus, JSON-Logs,
  B3-Tracing, schlanke Images, zustandslos, PostgreSQL, Daten über Volumes, alles per Env,
  Secrets getrennt, optionale Komponenten abschaltbar.
- **CPU-only:** Alles läuft ohne GPU; GPU-Engines bleiben optional.
- **LLM:** wie im heutigen Kompetenzkartierer (`config.py`, `services/extraction/llm.py`),
  ohne die B-API-Varianten:
  - `OPENAI_BASE_URL`, Standard `https://api.openai.com/v1`, änderbar für jeden anderen
    OpenAI-kompatiblen Anbieter;
  - `OPENAI_MODEL`, Standard `gpt-6-luna`; `OPENAI_REASONING_EFFORT` und
    `OPENAI_TEXT_VERBOSITY` als geprüfte Wertelisten (Standard `low`);
  - `LLM_PROVIDER`: `openai` (Responses-API) oder `openai-compatible` (Chat Completions),
    beim Start geprüft;
  - `LLM_CONTEXT_TOKENS` optional; Prompt-Cache-Haltepunkt hinter dem Dokument wie heute;
  - Schlüssel `OPENAI_API_KEY` als Secret (Env oder `*_FILE`), nie im Log.
- **Keine Aufrufe Dritter zur Anfragezeit:** Fremddaten nur über Sync-Jobs und Sidecars als
  geprüfte Abzüge (§7.2). Ein Test mit gesperrtem Netz deckt jeden Lesepfad ab.
- **Ontologie im Repository:** Die Dateien aus `ergebnis/` (Ontologie, Vokabulare, Profile,
  Schemas, Prüfskript) werden als `ontology/` ins neue Repository übernommen und dort
  versioniert. Das Repository ist damit für CI und Betrieb in sich vollständig.
- **Herkunft und Prüfung** nach Abschnitt 7 sind Pflicht für jede Zeile, die nicht wörtlich aus
  einer Quelle stammt.
- **Sprache:** Bezeichner, Kommentare und Commit-Nachrichten Englisch; Oberfläche und
  Fachdoku Deutsch (wie heute). Jeder sichtbare Text läuft über die i18n-Schicht.
- **Qualitätsboden der Oberfläche:** WCAG 2.2 AA, Lade-, Leer-, Fehler- und Teilzustände,
  Tastaturbedienung, selbst gehostete Schriften und Assets, keine Anfragen an Dritte vor
  einer Einwilligung, keine personenbezogenen Daten in URLs, Local Storage oder Logs.
- **Tests zuerst** (rot, dann grün); Abdeckungsgrenze im CI wie heute.
- **Dateigrößen:** Dateien über 300 Zeilen werden geprüft und nach Zuständigkeit geteilt.

## 6. Architektur

### 6.1 Komponenten

| Komponente | Aufgabe | Skalierung | Zustand |
|---|---|---|---|
| `api` | öffentliche REST-API (Port 8000), intern `/health`, `/ready`, `/metrics` (Port 9000) | Replicas nach Last | keiner |
| `worker` | Jobs: Extraktion (X1–X6, N1, N2, G1), Import, Export, Prüfung (X5), Einbettungen | eigene Replicas | keiner |
| `converter` | Konvertierung PDF/DOCX → Blöcke (X0): Docling, pdfplumber, OCR; eigenes Image mit torch-CPU und LibreOffice | eigene Replicas, 1 Job je Pod | Modelle im Volume |
| `postgres` | führende Datenhaltung mit `pgvector`, `pg_trgm`, `unaccent` | extern oder mitgeliefert (Helm-Schalter) | ja |
| Objektspeicher | Quelldateien, Markdown, Blöcke, Rohantworten, Exporte (S3-kompatibel; MinIO lokal) | extern | ja |
| `redis` (optional) | gemeinsame Rate-Limits und Caches ab zwei API-Replicas | extern oder mitgeliefert | flüchtig |
| `web` | gebaute SPA hinter einem unprivilegierten nginx | Replicas | keiner |
| `migrate` | wendet Datenbankmigrationen an (Job/Init-Container, Advisory-Lock) | einmal je Release | – |
| `index-sync` (ab M3) | baut lokale Indizes aus offenen Abzügen (Wikidata über die dewiki-Dumps, GND über data.dnb.de, ESCO, KldB→ISCO) und tauscht sie atomar; Muster und Index-Bauer aus compendious | Sidecar bzw. CronJob, ein Lauf zur Zeit (Sperrdatei) | je Abzug ein eigenes Volume, nur lesend für api und worker |
| `zim-sync` (M3, abschaltbar) | lädt die ZIM-Archive von Wikipedia (ohne Bilder) und Klexikon mit Prüfsumme und Wiederaufnahme; Quelle für Entity-Linking und für Wissen zu Themen und Entitäten (§7.2) | Sidecar bzw. CronJob, Aktualisierung etwa alle 30 Tage | eigenes Volume (rund 18,7 GB, compendious plant 60 Gi) |
| Modell-Volumes | Konvertierungsmodelle (Docling, OCR) und das lokale Einbettungsmodell | einmal befüllt (Init-Container) | nur lesend eingebunden |
| `oxigraph` (optional, M5) | schreibgeschützter SPARQL-Endpunkt für veröffentlichte Graphen | – | befüllt beim Veröffentlichen |

**Warteschlange:** Die Job-Tabelle in PostgreSQL ist die Wahrheit. Worker holen Jobs mit
`FOR UPDATE SKIP LOCKED`, halten eine Lease mit Lebenszeichen und geben sie bei Abbruch oder
Absturz frei; abgelaufene Leases übernimmt ein anderer Worker. Die faire Bedienung je Konto
der heutigen App bleibt erhalten (eine Spur je Konto). Das spart einen eigenen Broker und
hält Job-Zustand, Abrechnung und Daten in einer Transaktion. Redis ist nur für gemeinsame
Limiter und Caches nötig; die Vorgaben nennen Redis als Beispiel, nicht als Pflicht.

**Schmales Hauptvolumen:** Es gibt kein gemeinsames App-Volume. Die Datenbank läuft extern,
Dateien liegen im Objektspeicher. Große Daten (Indizes, ZIM, Modelle) liegen je Datenart in
einem eigenen Volume, das ein Sidecar oder CronJob aus demselben Image befüllt und api und
worker nur lesend einbinden. Wo ein geteiltes Volume langsam ist, legt jeder Pod eine lokale
Kopie an (Muster `INDEX_COPY_DIR` aus compendious). Neue Stände werden neben dem alten gebaut,
atomar getauscht und von den Lesern ohne Neustart übernommen.

### 6.2 Datenfluss

```
Quelle (URL, Upload, MEM, Portal-Adapter)
  → Quellregister (URL, Abrufdatum, Prüfsumme, Quelltyp, Lizenz)
  → X0 converter: Blöcke mit Block-ID p<Seite>-b<Block>, PDF- und gedruckte Seite
  → X1 Dokumentprofil und Gerüst → X2 Segmente → X3 Rahmenteile → X4 Aussagen
  → X5 Prüfung: Wortlaut gegen Blöcke, Plausibilität, SHACL je Dokument, Summen
  → X6 Reparatur (nur bei Befunden)
  → Redaktion: Prüfstand je Knoten und Aussage, Festschreiben einer Fassung
  → N1 Zerlegung + Konzept-Kandidaten (Einbettung) → N2 Normdaten (Entity-Linking)
  → G1 Kanten-Kandidaten (Retrieval + Rerank, höchstens 40) → Wahl der Kantenart
  → Faktentabellen und Sichten für Matrix, Vergleich, Suche, Statistik
  → Veröffentlichen: öffentliche Sichten, Exporte (Kern-RDF, MEM, CASE, ELM, AMB), Datensatz-Stände
```

Ein MEM-Import überspringt X1–X4: Die Struktur kommt deterministisch aus dem MEM-Graphen,
Aussageart und Adressat per Regel. Die Wortlaute werden mit der Ankersuche im konvertierten
PDF wiedergefunden (Fundart `notFound`, wo das nicht gelingt).

### 6.3 Datenmodell

Alle adressierbaren Dinge teilen einen Kennungsraum: Die Tabelle `entity (id uuid, kind)`
gibt jedem Dokument, Knoten, jeder Aussage und jedem Konzept eine ID. Wertobjekte, Anker
und Kanten verweisen per Fremdschlüssel auf `entity.id`. So bleiben Verweise auf beliebige
Subjekte referentiell geprüft, ohne polymorphe Spalten. Interne IDs sind UUIDv7; IRIs werden
aus Werk, Fassung und Code-Pfad gebildet und bleiben über Läufe stabil.

| Schicht | Tabellen (Auswahl) |
|---|---|
| Quellen | `source_file` (SHA-256, Typ, Größe, Speicherschlüssel), `acquisition` (URL, Abrufdatum, Prüfsumme, Quelltyp amtlich/Archiv/Spiegel/Sekundär, Abrufkette, Lizenz), `document_block` (X0) |
| Geltung | `work`, `document` (Fassung, Gültigkeit, Region, Bereiche, Dokumenttyp, Rechtsform, Verbindlichkeit, Lizenz), `specification` (curriculum/framework/qualification/assessment), `document_specification` (n:m), `programme`, `qualification`, `occupation`, `variant`, `applicability_context` |
| L1 | `node` (Funktion, Profiltyp, Code, Originaltitel, Extraktionstiefe, Revision), `statement` (Wortlaut, Sprache, Aussageart, Unterart, Adressat, Verbindlichkeit, Einleitung, Wortlaut-Felder, `text_hash`), `anchor` (Block-ID, Seiten, Zitat, Fundart, Zelle, Zeichenspanne), `placement` |
| L2 | `decomposition`, `concept` (Inhalts-, Kompetenz-, Bereichskonzept, Körnung) mit `concept_closure`, `level_assignment` (Stufe, Spanne, Relation, Dimension, Kompetenzbereich), `time_span`, `workload`, `rule` mit Optionen, `assessment` |
| L3 | `alignment` (Kantenart, Ziel intern oder externe IRI, Zielsystem und -version, Herkunft, Methode, Konfidenz, Prüfstand, Prüfer, Begründung, Anker, Lauf) mit `alignment_source`; Sicht `alignment_short` nur für bestätigte und amtliche Kanten |
| Lexikon | `terminology_profile`, `lexical_cue` (Rolle, Art, Muster, Ziel, Geltung, Stärke, geprüft), `document_profile` |
| Vokabulare | `vocab_scheme`, `vocab_concept` (IRI, Notation, Labels als JSONB, broader), `vocab_release` (Hash der TTL-Dateien) |
| Läufe | `extraction_run` (Stufe, Modell, Prompt-, Profil- und Lexikonversion, Schlüssel der Rohantwort), `extraction_assertion`, `conflict_resolution` |
| Qualität | `validation_finding` (Lauf, Regel, Schwere, Fokus), `review_sample` (Goldstandard, Ergebnis), `quality_metric` |
| Suche | `search_text` (tsvector `german` + `unaccent`, gefaltete Spalten), `embedding` (Subjekt, Modell, Version, Vektor) |
| Fakten | materialisierte Sichten `element_facets`, `coverage_cell` |
| App | `account`, `role_grant`, `api_key`, `share`, `publication`, `job`, `llm_usage`, `conversion_usage`, `quota`, `audit_log` |

Pflichtwerte (Aussageart, Adressat, Kantenart, Herkunft …) sind Fremdschlüssel auf
`vocab_concept`, nicht feste CHECK-Listen. Neue Vokabularwerte brauchen damit keine Migration.

### 6.4 Schnittstellen

- REST unter `/api/v1`, OpenAPI aus dem Code mit Anzeigename, Kurzbeschreibung und Tags;
  `/openapi.json` am öffentlichen Port; interne Pfade nicht in der Spec.
- Lang laufende Vorgänge: `POST` legt einen Job an und gibt `202` mit Job-ID; `GET
  /api/v1/jobs/{id}` liefert Status und Fortschrittscodes.
- Content-Types: `application/json`; Dateiausgaben (TTL, DOCX, PDF, ZIP) und Uploads sind die
  Abweichung, die mit T6 abzustimmen ist.
- Fehler als einheitliches JSON (`code`, `message`, `details`); keine Stacktraces nach außen.

### 6.5 Ordnerstruktur

```
kompetenzkartierer-ai/      eigenes Repository Kompetenzkartierer-AI
  ontology/         Kern 1.0 aus ergebnis/: Ontologie, Vokabulare, Profile, Schemas, Prüfskript
  backend/
    app/
      api/          Router je Fachgebiet, Middleware, interne Endpunkte
      core/         Settings, Logging, Tracing, Metriken, Auth, Fehler
      db/           Pool, Migrationsläufer, Repositories je Aggregat
      domain/       Modelle und Regeln nach Kern 1.0 (ohne Framework-Importe)
      pipeline/     X0–X6, N1, N2, G1 als Job-Handler
      sources/      Quell-Adapter (Upload, URL, MEM, Portale), Konvertierung (Client)
      vocab/        Lader für TTL, Lexikon, Profile, JSON-Schemas
      exports/      Kern-RDF, MEM, CASE, ELM, AMB, DOCX/PDF/HTML, Markdown
      llm/          OpenAI-kompatibler Client, Budget, Abrechnung
      search/       Schnittstelle für externe Inhaltssuche (später WLO/edu-sharing-API)
      jobs/         Warteschlange, Worker, Lease, Fairness
    migrations/     versionierte SQL-Dateien
    tests/
  converter/        eigenes Image für X0
  frontend/         Vite + Vue 3 + TypeScript
  deploy/           Dockerfiles, docker-compose.yml, helm-values.example.yaml, Alarme
  docs/uebergabe/   Übergabe an T6 (Checkliste, Konfiguration, Steckbrief)
```

Abhängigkeiten zeigen nach innen: `api`, `jobs`, `db`, `sources` und `exports` dürfen
`domain` importieren, `domain` importiert nichts davon. Ein Importtest im CI erzwingt das.

### 6.6 Neue Abhängigkeiten

| Paket | Zweck | Begründung |
|---|---|---|
| `psycopg[binary,pool]` 3 | PostgreSQL | Standardtreiber, Pool, Server-seitige Parameter |
| `pgvector` (Python) | Vektor-Typ für psycopg | dünne Hülle um die Erweiterung |
| `prometheus-client` | Metriken | Vorgabe; Muster aus compendious |
| `boto3` oder `minio` | Objektspeicher | S3-Schnittstelle; Auswahl in M0 nach Größe und Lizenz |
| bestehend | FastAPI, pydantic-settings, pydantic-ai, rdflib, pyshacl, docling, httpx | übernommen wie im heutigen Kompetenzkartierer; das Modellprofil von pydantic-ai für `gpt-6-luna` wird in M0 geprüft |

## 7. Herkunft, Qualität, Drittanbieter, Zugang und Rechte

### 7.1 Herkunft, Qualität und Datensatz-Stände

Diese Regeln folgen aus Kern 1.0 und aus den Schwächen der Vergleichs-App.

1. **Quellregister:** Jede Quelle hat URL, Abrufdatum, Prüfsumme, Quelltyp und Lizenz. Bei
   gesperrten Portalen wird die Ersatzkette dokumentiert (Archiv, Spiegel). Die Oberfläche
   zeigt Quelltyp und Lizenz je Dokument.
2. **Herkunft und Prüfstand je Zeile:** Jeder Knoten, jede Aussage, jedes Wertobjekt und jede
   Kante trägt Herkunft (Quelle, Modell, Regel, Mensch, Import, vererbt), Lauf und Prüfstand.
   „Lehrplaninhalt“ ist nur, was aus der Quelle stammt. Erzeugtes (Zusammenfassungen,
   Suchtexte, Konzeptvorschläge) ist sichtbar gekennzeichnet, und Exporte filtern danach.
3. **Prüfung über den Wortlaut hinaus:** X5 prüft Wortlaut gegen Blöcke und zusätzlich
   Plausibilität (Überschrift als Aussage, Mindestinhalt, Aussageart passt zum Knotentyp,
   Summen) sowie SHACL je Dokument. Befunde werden als Zeilen gespeichert.
4. **Goldstandard und gemessene Güte:** Eine geschichtete Stichprobe je Land, Fach und Stufe
   wird redaktionell geprüft. Präzision und Vollständigkeit werden je Quelle gemessen und
   angezeigt. Der Abgleich MEM gegen Extraktion ist die erste Vorlage.
5. **Kanten kalibriert:** Konfidenzen werden gegen den Goldstandard geeicht. Ein Alarm
   meldet, wenn eine Kantenart oder Qualitätsstufe auffällig überwiegt. Kurzformen wie
   „steigert“ entstehen nur aus bestätigten oder amtlichen Kanten.
6. **Vergleiche über Konzepte, nicht über Wortüberschneidung:** Ähnlichkeit liefert
   Kandidaten; entscheiden LLM-Prüfung mit Begründung oder Redaktion.
7. **Kanten nur über IDs**, mit referentieller Integrität; stabile IRIs; Fassungen und
   Plangenerationen getrennt.
8. **Keine abgeleiteten Pläne:** Was aus Regeln folgt (Stufe aus Jahrgang, vererbtes Fach),
   ist als Regel mit Regelkennung gekennzeichnet und eine Sicht, kein eigener Lehrplan.
9. **Datensatz-Stände:** Veröffentlichte Daten erscheinen als versionierte Stände mit
   Prüfsummen, Zählungen und Prüfbericht. Der Download kommt aus demselben Build wie die
   öffentliche Ansicht; das CI prüft den Gleichstand. Methodik und Herkunftsangaben werden
   aus den Metadaten erzeugt.
10. **Rechte:** Rechtestatus je Quelle und eine eigene Lizenz für eigene Annotationen, siehe
    §7.4.

### 7.2 Möglichst wenig Dritte live

**Grundsatz:** Zur Anfragezeit ruft die App keinen Dritten auf. Fremddaten kommen über
Sync-Jobs oder Sidecars als geprüfte Abzüge (Prüfsumme, Stand) in Volumes oder in die
Datenbank. Alle Lesepfade funktionieren ohne Internet. Live bleiben nur das Sprachmodell und
optional Mistral OCR, beide nur in Jobs.

| Dritter | alte App | Neubau | Größe (bekannt) |
|---|---|---|---|
| Sprachmodell (OpenAI-kompatibel) | live in Jobs | live in Jobs; über `OPENAI_BASE_URL` auch ein eigener OpenAI-kompatibler Server | – |
| Mistral OCR | live, optional | live, optional, abschaltbar | – |
| Einbettungen | – | lokal auf CPU, zweistufig (siehe unten), Modelle im Volume | `m2v-gte-256-edu` rund 80 MB (int8); `multilingual-e5-small` in M3 messen |
| Wikidata | – | `index-sync` aus den dewiki-Dumps (`page_props`, `page`, `langlinks`) | Download rund 750 MB, Index 139 MB (compendious) |
| Wikipedia, Klexikon | – | `zim-sync` (Einleitung, Begriffsklärung, Normdaten-Block, Artikeltext) | Wikipedia rund 18,7 GB, Volume 60 Gi (compendious); Klexikon klein |
| GND | – | `index-sync` aus den DNB-Open-Data-Abzügen (Sachbegriffe, Geografika) | Download rund 65 MB, Index 55 MB (compendious) |
| ESCO | live API mit Cache | Abzug der ESCO-Klassifikation, Import in die Vokabular-Tabellen | in M3 messen |
| BERUFENET | live API mit Schlüssel | Abzug, soweit die BA einen anbietet; sonst Abruf nur im Anreicherungsjob mit Cache (in M3 prüfen) | – |
| KldB → ISCO | Download zur Laufzeit | Abzug beim Sync | klein |
| QDR/EQF, KIM, ISCED-F | lokale Kopien bzw. IRIs | in `ontology/` und den Vokabular-Tabellen | klein |
| MEM-Schule (SPARQL) | live beim Import | nur im Importjob; der Rohgraph liegt im Objektspeicher, Wiederholung ohne Netz | je Lehrplan klein |
| Lehrplanquellen | Abruf beim Upload oder URL-Import | Abruf nur im Quellregister-Job, Datei mit Prüfsumme im Objektspeicher | – |
| WLO/edu-sharing | – | später: Inhaltssuche über deren API hinter `search/`, mit Cache | – |

**Entity-Linking nach dem Vorbild compendious:**
1. Kandidaten: Das Sprachmodell nennt Wort und Wikipedia-Titel. Ohne Modell oder Budget
   übernehmen Regeln (spaCy und ein Wörterbuch aus Artikeltiteln).
2. Verknüpfen, nur lokal: Der Titel existiert und ist keine Begriffsklärung.
3. Kennungen: QID aus dem Wikidata-Index; GND aus dem Normdaten-Block (mit ZIM) oder aus
   dem GND-Index, erst über die QID, dann über den Namen, nur bei eindeutiger Zuordnung.
4. Optional eine LLM-Prüfung jeder Verknüpfung. compendious hat gemessen: Präzision 0,70
   ohne und 0,94 mit dieser Prüfung, bei sinkender Vollständigkeit.
5. Neu gegenüber compendious: Die Links hängen nach Kern 1.0 an Konzepten, nicht an
   Knoten, und tragen Herkunft, Methode, Konfidenz und Prüfstand.

**Embeddings, zweistufig und lokal:**
1. **Schnell für alles:** `JanSchachtschabel/m2v-gte-256-edu` (Model2Vec aus
   `gte-multilingual-base`, 256 Dimensionen, rund 70.000 deutsche Bildungsbegriffe im
   Vokabular, Apache-2.0, ohne torch). Es bettet jede Aussage, jedes Konzept und jede
   Suchanfrage ein, auch für die öffentliche Suche. Kombiniert wird es mit der Volltextsuche
   von PostgreSQL (Rangfusion), damit Fachbegriffe und Komposita nicht verloren gehen.
2. **Genauer für Kandidaten:** `intfloat/multilingual-e5-small` (384 Dimensionen, MIT) über
   ONNX Runtime ohne torch. Es ordnet die besten rund 200 Treffer neu und liefert die
   Kandidaten für N1 und G1, wo Qualität vor Durchsatz geht. Die Endentscheidung trifft dort
   ohnehin das Sprachmodell aus einer nummerierten Liste.

Begründung: Auf der Fächerklassifikation der Modellkarte liegt `m2v-gte-256-edu` nur knapp
hinter `multilingual-e5-small` (Macro-F1 0,568 gegen 0,587; Micro-F1 0,743 gegen 0,777),
liest aber ein Vielfaches an Texten je Sekunde. Klassifikation ist nicht Retrieval: In M3
misst ein Lauf am Goldstandard Recall@40 und nDCG@10 für vier Varianten (nur Volltext, nur
m2v, m2v mit Volltext, zusätzlich e5-Neuordnung) und legt die Schwellen fest. OpenAI-Embeddings
entfallen, weil sie eine zweite Abhängigkeit vom Anbieter schaffen. Je Vektor werden Modell und
Version gespeichert (`halfvec`, HNSW-Index); ein Modellwechsel heißt neu einbetten im
Hintergrund.

**Wikipedia-Archiv (ZIM) ist eingeplant.** Es liefert dem Entity-Linking die Prüfung auf
Existenz und Begriffsklärung, die Einleitung und den Normdaten-Block. Ohne Archiv fehlt das;
ein Wikidata-Index mit Kurzbeschreibung bleibt der Ausweichweg, wenn das Volume nicht
bereitsteht (Helm-Schalter).

**Wissen zu Themen und Entitäten:** Dasselbe Archiv macht Wissen abrufbar, ohne Dritte live
zu fragen:
- **Kurzbeschreibung** an jedem verknüpften Konzept oder jeder Entität: Einleitung des
  Artikels, für Lernende die Fassung aus Klexikon, mit Link zum Artikel.
- **Kontext für Aufgaben des Sprachmodells**, etwa Gliederung einer Themenrecherche oder
  Abgrenzung eines Themas. Die Artikelabschnitte werden lokal gesucht (Muster aus compendious:
  Absätze den Bausteinen zuordnen, Belege führen).
- **Kennzeichnung:** Wikipedia- und Klexikon-Texte stehen unter CC BY-SA. Sie erscheinen
  immer mit Quelle, Autorenhinweis und Lizenz. Sie sind getrennt vom Lehrplanwortlaut
  gespeichert und als Herkunft `wikipedia` bzw. `klexikon` gekennzeichnet. Modelltexte, die
  darauf aufbauen, gelten als bearbeitete Fassung und erhalten dieselbe Lizenzangabe.

**Betrieb der Abzüge:** Jeder Abzug meldet Stand, Prüfsumme und Alter als Metrik. Ein Alarm
schlägt an, wenn ein Stand veraltet oder ein Sync-Lauf fehlschlägt. Ohne Netz baut ein
CLI-Befehl die Indizes aus vorher kopierten Dumps.

### 7.3 Zugang, Rollen und KI-Kontingente

- **Hauptnutzende** sind Lehrkräfte, Entscheiderinnen und Entscheider aus Politik und
  Verwaltung sowie die Redaktion. Lernende nutzen die App vor allem zum Nachschlagen.
- **Anmeldung wie heute:** Ein Admin vergibt Tokens an Konten. Rollen sind `admin`,
  `redaktion` und `nutzer` (Lehrkräfte, Entscheider). Jedes Konto hat ein KI-Kontingent für
  Tokens und Seiten wie heute.
- **Öffentlicher Zugang per Option** `PUBLIC_ACCESS`:
  - `off`: nur mit Token;
  - `lookup`: veröffentlichte Lehrpläne, Bäume, Matrizen und Vergleiche nachschlagen;
  - `search`: zusätzlich Volltext- und semantische Suche mit dem lokalen Einbettungsmodell.

  Die Freigabe einzelner Funktionen regelt eine Liste `PUBLIC_FEATURES`; sie wird in M5
  festgelegt.
- **KI nie ohne Token:** Alle Endpunkte, die das Sprachmodell rufen (Extraktion, Recherche,
  Gliederung, Zusammenfassung), verlangen Token und Kontingent; ohne Token antworten sie mit
  401. Die öffentliche Suche nutzt nur das lokale Modell und verbraucht keine KI-Tokens.
- **Sicher ohne Konto:**
  - nur lesende Endpunkte;
  - eine eigene Datenbankrolle, die nur veröffentlichte Sichten lesen darf;
  - Rate-Limits je IP über Redis;
  - Antwort-Caches;
  - Grenzen für Seitengröße und Abfragekomplexität;
  - keine Cookies außer technisch nötigen.
- **Lernende ohne Registrierung:** eigener Plan, Lernziele abhaken, Lernstand nur im Browser,
  als Markdown oder JSON exportierbar. Der Server speichert nichts über sie.
- **Später:** Profile und Lernwege für lebenslanges Lernen brauchen Konten für Lernende. Das
  Datenmodell lässt die Rolle zu; das Konzept mit Datenschutz für Minderjährige folgt nach M6.

### 7.4 Rechte an Wortlauten

Das ist keine Rechtsberatung, sondern eine Einordnung, die vor dem öffentlichen Start (M5)
rechtlich geprüft werden sollte.

**Einordnung**
- Gesetze, Verordnungen, amtliche Erlasse und Bekanntmachungen genießen keinen
  urheberrechtlichen Schutz (§ 5 Abs. 1 UrhG). Viele Schul-Lehrpläne erscheinen als Erlass oder
  Verwaltungsvorschrift, oft im Amtsblatt; für sie spricht viel für Gemeinfreiheit.
- Andere amtliche Werke, die zur allgemeinen Kenntnisnahme veröffentlicht sind, sind ebenfalls
  frei, aber mit Änderungsverbot und Pflicht zur Quellenangabe (§ 5 Abs. 2 mit §§ 62, 63 UrhG).
- Nicht alles ist amtlich. Mehrere Kita-Bildungspläne sind in Verlagen erschienen (laut
  Recherche etwa verlag das netz). Rahmencurricula der Erwachsenenbildung tragen Rechte Dritter
  (laut Recherche Goethe-Institut im Auftrag des BAMF; der GER-Begleitband © Klett).
  Modulhandbücher stehen nur teils in amtlichen Bekanntmachungen. Hier liegt das eigentliche
  Risiko.
- Kurze Zitate mit Quellenangabe als Beleg sind durch das Zitatrecht gedeckt (§ 51 UrhG). Eine
  vollständige öffentliche Wiedergabe geschützter Texte ist es nicht. Kopien für die
  automatisierte Analyse erlaubt das Gesetz unter Bedingungen (§§ 44b, 60d UrhG).
- Die Vergleichs-App erklärt „keine Lehrplantexte enthalten“ und veröffentlicht doch Wortlaute
  unter CC0. Das zeigt, dass die Frage real ist; bei richtiger Steuerung ist sie beherrschbar.

**Umsetzung:**
1. **Speichern:** alle Wortlaute, weil Redaktion, Beleg und Prüfung sie brauchen.
2. **Rechtestatus je Quelle und Dokument:** `amtlich`, `offen_lizenziert` (mit Lizenz),
   `geschuetzt`, `unklar` (Standard). Gesetzt wird er von der Redaktion, mit Beleg.
3. **Anzeige:**
   - Angemeldete Nutzerinnen und Nutzer sehen den Wortlaut.
   - Öffentlich erscheinen `amtlich` und `offen_lizenziert` vollständig mit Quellenangabe.
   - `geschuetzt` und `unklar` erscheinen nur als Kurzzitat (Länge einstellbar) mit Quelle
     und Link zum Original.
4. **Exporte und offene Daten:** Wortlaut nur bei `amtlich` und `offen_lizenziert`; sonst
   Struktur, Links und eigene Annotationen.
5. **Sperren:** ein Schalter je Quelle, Land oder Dokumenttyp, der sofort in allen Sichten und
   Exporten greift, weil die Regel im Lesepfad sitzt. Kein Neubau nötig. Dazu Löschen auf
   Anforderung.
6. **Eigene Dokumente,** etwa Entwürfe einer Lehrplankommission: Die Rechte liegen beim
   hochladenden Konto. Standard ist privat; veröffentlicht wird nur mit ausdrücklicher
   Bestätigung der Rechte.
7. **Für Dritte verbergbar:** Markdown-Extrakte (die konvertierte Quelle samt Blöcken) und
   Zitate (Wortlaute von Aussagen, Fundstellen-Zitate, Suchausschnitte) lassen sich für Dritte
   ausblenden. Dritte sind alle außer dem Eigentümerkonto, Konten mit Schreibfreigabe sowie
   Redaktion und Admin.
   - Einstellungen `THIRD_PARTY_MARKDOWN` (`hidden` | `accounts` | `public`, Standard
     `hidden`) und `THIRD_PARTY_VERBATIM` (`full` | `quote` | `hidden`, Standard nach
     Rechtestatus).
   - Beide lassen sich je Quelle, Land, Dokumenttyp und Dokument überschreiben; es gilt die
     strengere Regel.
   - Die Regel greift in Oberfläche, API, Exporten, Suchausschnitten und offenen Daten. Bei
     `hidden` bleiben Gliederung, Titel der Einheiten, Kanten, Niveaus und eigene Annotationen
     sichtbar, dazu ein Link zum Original.
   - Verbergen ist kein Löschen. Die Daten bleiben für Redaktion und Eigentümer erhalten.
   - Die Lizenzprüfung der Länder (läuft) setzt die Rechtestatus und damit die Standards.

### 7.5 Importquelle Vergleichsdatensatz

Die CSV-Dateien im alten Repository unter `docs/recherche/konkurrenz/` stammen aus dem
CC0-Datensatz der Vergleichs-App (`data_deutschland.json.gz`, Stand v62.493). Sie wurden mit
`tools/build_csv.py` erzeugt.

| Datei | Inhalt | Zeilen |
|---|---|---|
| `lehrplan_dokumente_de.csv` | ein Dokument je Land × Schulform × Fach, mit URL, Archiv-URL, Quelltyp, Verifikation, Jahrgängen, Verbindlichkeit | 1.831 |
| `lehrplan_urls_de.csv` | eine Zeile je Quell-URL | 2.274 |
| `umgehungshinweise_de.csv` | gesperrte Portale und Umwege (Wayback, Sekundärquelle, Sperre 403/429, Spiegel, GEI) | 355 |

**Befund:**
- Nur allgemeinbildende Schule: Gymnasium 1.108, ESA 321, MSA 269, Grundschule 133.
- BW (501) und BY (450) machen die Hälfte aus.
- Eine md5 haben nur 131 von 1.831 Dokumenten.
- Verifikation: „volltext“ 1.264, „kanonisch“ (ohne eigenes Landesdokument) 243.
- 90 Zeilen sind ESA-Ableitungen, also gekürzte Pläne anderer Schulformen.

**Verwendung:**
- **Übernommen werden nur Saatdaten für das Quellregister:** URL, Archiv-URL, Land, Schulform,
  Fach, Jahrgänge, Verbindlichkeit und Quelltyp. Sie landen als Kandidaten mit Herkunft
  „Vergleichsdatensatz v62.493“ und Status `ungeprueft`.
- **Nicht übernommen** werden Titel, Beschreibung, Themen, Knotenzahlen und Verifikationsangaben
  als Inhalt. Sie dienen höchstens als interner Hinweis für die Nachrecherche.
- ESA-Ableitungen und „kanonisch“ modellierte Zeilen werden nicht als eigene Lehrpläne
  angelegt.
- **Nachrecherche in zwei Stufen:**
  1. Ein Prüfjob ruft jede URL einmal ab: erreichbar, Dateityp, Prüfsumme, Datum.
  2. Er gleicht die Liste mit unseren Länderrecherchen (Tabelle T1 je Land) ab; Abweichungen
     klärt ein Rechercheauftrag.
- **Umgehungshinweise** werden als Zugangsnotiz je Portal übernommen: gesperrt, Archiv
  vorhanden, Spiegel vorhanden. Regel: Wir nutzen amtliche Quellen. Öffentliche Archive wie
  die Wayback Machine sind als Quelltyp „Archiv“ erlaubt, Spiegel nur gekennzeichnet und
  hilfsweise. Technische Zugangssperren wie Captchas, Geo- oder Bot-Sperren umgehen wir nicht.

## 8. Anwendungsfälle und ihre Bausteine

| Anwendungsfall | braucht | Meilenstein |
|---|---|---|
| Lehrplan extrahieren, prüfen, bearbeiten, festschreiben | X0–X6, Editor, Redaktion | M1 |
| Lehrplan von Hand anlegen (Formular) | schemagetriebenes Formular aus dem Profil | M1 |
| MEM-Lehrplan importieren, bearbeiten, exportieren | MEM-Adapter, Ankersuche, SHACL-Tor | M2 |
| Niveau, Kompetenzbereich, Zeit, Umfang, Regeln, Prüfungen erfassen | L2-Wertobjekte im Editor | M3 |
| Berufe, Kompetenzen, Normdaten (ESCO, KldB, QDR, ISCED-F, Wikidata, GND) zuordnen | Anreicherungsquellen, N2-Adapter | M3 |
| Was lernt man im Leben zu Thema X, nach Bildungsstufen | Konzepte, `mentions`, Fakten, Einbettungen, Recherche-Job | M4 |
| Lehrkräfte durchsuchen ihre Pläne und bekommen passende Inhalte | Suche (Volltext, semantisch), G1 | M4 |
| Lehrpläne vergleichen (Land ↔ Land, Fassung alt ↔ neu) | Konzepte, `text_hash`, Kanten | M4 |
| Abdeckungsmatrix Land × Stufe × Fach | `element_facets`, `coverage_cell`, Prüfprotokoll | M4 |
| Statistik zur Granularität | Aggregat-Sichten | M4 |
| Querschnittsziele auswerten (Nachhaltigkeit, Digitalisierung, Gesundheit, Demokratie) | `qz:`-Hub, `contributesTo`, Barometer-Sicht | M4 |
| Kanonisches Referenzschema je Fach und Stufe mit Kennzahl „restfrei angebunden“ | Konzeptschema + Kanten | M4 |
| Lernende ohne Konto: eigener Plan, Lernziele im Wortlaut abhaken, Lernstand als Markdown, Vorlesen | öffentlicher Zugang `lookup`, Lernstand im Browser, Web-Speech-API | M5 |
| Entscheider: Abdeckung, Vergleich der Länder, Querschnittsziele, Granularität auf einen Blick | Gesamtansicht, Barometer, Statistik, Exporte | M4/M5 |
| Schulwechsel-Report im Inland | Vergleich + Export | M5 |
| Lehrkräfte: Dashboard, Themen je Klassenstufe, Verbindlichkeit, Kompetenzbereiche, Belege, Querverweise, Druck/PDF/Markdown | Rolle Lehrkraft, Sichten, Dokument-Export | M5 |
| Curriculum-Werkstatt: Themen übernehmen, eigene Einheiten, Halbjahr, Stunden, Notizen, Medien, Fortschritt, JSON-Import/-Export | Werkstatt-Modell je Konto | M5 |
| Gesamtansicht: Länder-Explorer, Landkarte, Vergleich zweier Länder, Sequenz-Dashboard, CSV-Exporte | Sichten, Karte als eigenes SVG | M5 |
| Lernmedien finden | Schnittstelle `search/` an Konzepten und Aussagen; die Inhaltssuche über die API von WLO/edu-sharing dockt später an | Schnittstelle M5, Anbindung nach M6 |
| Teilen unter Nutzern und öffentlich, offene Daten | Freigaben, Veröffentlichung, Datensatz-Stände | M5 |
| Berufsschul-Rahmenlehrpläne nachschlagen | Profil `beruf:`, KMK-RLP als Quelle | M1/M4 |
| Ausland, Selbsttest, Forschungsfreigabe | – | nach M6 |

## 9. Nichtfunktionale Anforderungen

- **Leistung:** Matrixabfragen und Facettensuche über alle Lehrpläne Deutschlands (Annahme:
  300.000–500.000 Elemente, im Lastlauf von M4 geprüft) antworten unter 1 s aus den materialisierten
  Sichten; Suche unter 500 ms ohne Rerank. Gemessen mit einem Lastlauf in M4.
- **Sicherheit:** Rechteprüfung in SQL (Filter oder Row Level Security), nie in Python nach dem
  Laden. Rate-Limits für öffentliche und LLM-Endpunkte. Uploads nach Typ und Größe geprüft,
  Archive mit den bekannten ZIP/TAR-Schutzregeln der heutigen App. Secrets nur aus Env oder
  `*_FILE`, nie im Log, nie in Fehlermeldungen. Audit vor jeder Veröffentlichung.
- **Barrierefreiheit:** WCAG 2.2 AA; jede Grafik hat eine Tabellen- oder Textalternative.
- **i18n:** Deutsch zum Start, Katalog-Schlüssel und Pluralregeln von Anfang an; Datenmodell
  mehrsprachig.
- **Datenschutz:** Lernende brauchen kein Konto; ihr Lernstand bleibt im Browser. Keine
  Drittanbieter-Ressourcen im Browser und keine Aufrufe Dritter zur Anfragezeit (§7.2);
  Einwilligung vor jeder optionalen Datenweitergabe.
- **Beobachtbarkeit:** HTTP-, Job-, LLM- und Konvertierungsmetriken; Alarme für volle
  Warteschlange, Lease-Verluste, LLM-Fehlerquote, Quotenstände, Speicherplatz.

## 10. Übernahme aus dem Bestand

| Baustein | Quelle | Art |
|---|---|---|
| Zwei-Port-Start, Logging, Tracing, Metriken, Alarme, Dockerfile-Härtung, Helm-Values, Übergabedokumente | `compendious-text-fastapi` (`app/serve.py`, `app/api/internal_port.py`, `app/logging.py`, `app/tracing.py`, `app/api/metrics.py`, `monitoring/`, `docs/uebergabe/`) | kopieren und anpassen |
| Wikidata- und GND-Indizes mit atomarem Tausch, Sync aus den Dumps mit Prüfsumme | compendious `app/sources/{local_index,local_copy,dump_sync,wikidata/index,gnd/index}.py` | kopieren (M3), Abhängigkeiten auf compendious-Settings kappen |
| Konvertierung (Docling, pdfplumber, OCR, Mistral) mit Kindprozess und Frist | `curriculum-extractor/backend/ce_api/services/conversion` | kopieren, um Block-IDs erweitern |
| LLM-Schicht (pydantic-ai, OpenAI-Provider mit `OPENAI_BASE_URL`, Responses- oder Chat-API, Prompt-Cache-Haltepunkt, Zählung je Aufruf) | `config.py`, `services/extraction/llm.py` | übernehmen ohne die B-API-Varianten |
| Ankersuche (exakt, Leerraum, unscharf; Replay-Maße) | `services/extraction/anchors.py` | kopieren, auf Blöcke umstellen |
| Token- und Seitenabrechnung, Quoten | `db_usage.py`, `services/usage.py`, `services/quota.py` | Logik übernehmen, Sperre durch `SELECT … FOR UPDATE` je Konto ersetzen |
| MEM-Client (SPARQL, Katalog, Länder-Erkennung), MEM-Export mit SHACL-Tests | `services/mem`, `export/mem_ttl.py` | kopieren, auf Kern-Tabellen umstellen |
| Anreicherungsquellen (ESCO, Berufenet, KldB→ISCO, QDR, ISCED-F, HQR, GER, KMK) | `services/enrichment` | Quellen kopieren, Ablage als `alignment` an Konzepten |
| Dokument-Export HTML/DOCX/PDF | `services/docgen` | kopieren |
| Prompts der Extraktion | `services/extraction/prompts.py` | als Ausgangspunkt, neu auf X1–X4 zugeschnitten |
| Frontend: Tokens, `t()`, HTTP-Client, Baum, Matrizen, Dialoge, Fortschritt, Quellenbeleg, Teilen, statische Schutztests, axe- und Kontrasttests | `curriculum-extractor/frontend/src`, `tests/` | kopieren und anpassen |
| Nicht übernommen | Baum-Walk über `typical_parents`, Duplikat-Logik am Lauf, Export-Module je Namespace, Backup über die SQLite-API, Job-Rahmen im Prozess, `authz` mit Filtern in Python, Arbeitsbereichs-Views | – |

## 11. Verhältnis zur alten App

- Keine Datenübernahme: In der alten App liegen nur Testextrakte. Die neue App beginnt mit
  leerem Bestand; Konten legt der Admin neu an.
- Die alte App bleibt eingefroren stehen und kann jederzeit abgeschaltet werden.
- Die Test-PDFs und die gemessenen MEM-Vergleiche der alten App dienen als Prüfmaterial für
  die neue Pipeline (Regressionsset und erste Vorlage des Goldstandards), nicht als Daten.

## 12. Meilensteine

Jeder Meilenstein bekommt vor seinem Beginn einen eigenen Plan mit Aufgabenliste
(`docs/plans/`); hier stehen Ergebnis, Abnahme und Aufwand.

| # | Ergebnis | Abnahme (Auszug) | PT |
|---|---|---|---|
| M0 | Fundament: Gerüst, Betriebsseite, PostgreSQL, Migrationen, Jobs mit Lease, eigene Auth, LLM-Einstellungen, Ontologie im Repository, Objektspeicher, Vokabular-Lader, Images, CI, Übergabe-Gerüst, Frontend-Rahmen | Abschnitt 14, M0 | 15–22 |
| M1 | Quellen und Extraktion L1: Quellregister mit Rechtestatus, Saat aus dem Vergleichsdatensatz und Prüfjob für URLs (§7.5), Konvertierungs-Worker mit Block-IDs, X1–X6, Lexikon samt Import der Rechercheergebnisse (mit Stichprobenprüfung), X5 mit SHACL, Abrechnung, schemagetriebener Editor, Redaktion und Festschreiben | Ein Lehrplan je Bereich läuft durch; X5-Befunde stehen als Zeilen; Quote und Abrechnung stimmen unter parallelen Workern | 40–55 |
| M2 | MEM-Schule: MEM-Import mit Ankersuche, Bearbeitung als Entwurfskopie, MEM-Export mit SHACL-Tor, KMK-Bildungsstandards als Kompetenzrahmen | MEM-Rundreise besteht die MEM-SHACL-Tests; Trefferquote der Ankersuche je Land gemessen | 9–14 |
| M3 | Deutung und Andocken L2: Zerlegung (N1), Konzepte und Hubs, Niveau/Zeit/Umfang/Regel/Prüfung im Editor, Anreicherungsquellen als lokale Abzüge (ESCO, KldB), `index-sync` und `zim-sync`, Entity-Linking (N2) nach §7.2, Wissen zu Themen und Entitäten, lokale Einbettungen | Kandidatensuche liefert gemessene Trefferquote am Goldstandard; Links hängen an Konzepten; Wikipedia-Texte mit Lizenzangabe; kein Aufruf Dritter im Lesepfad (Test mit gesperrtem Netz) | 31–43 |
| M4 | Kanten und Wissenslandkarte L3: G1, Kalibrierung, Goldstandard-Werkzeug, Faktentabellen, Matrix, Vergleich, Thema im Lebenslauf, Barometer, Statistik, Referenzschema | Lastlauf erfüllt Abschnitt 9; Verteilungsalarm getestet | 30–40 |
| M5 | Sichten, Visualisierung, Teilen: zuerst Lehrkräfte und Entscheider (Dashboard, Werkstatt, Gesamtansicht mit Karte und Graph), dann öffentlicher Zugang `lookup`/`search` für Lernende ohne Konto (§7.3), Wortlaut-Anzeige nach Rechtestatus und Verbergen für Dritte (§7.4), Schnittstelle für die Inhaltssuche, öffentliche Seiten, Datensatz-Stände, optional SPARQL | Axe ohne Befund, Tastaturpfade getestet, Download gleich öffentlicher Stand, verborgene Texte erscheinen in keiner Sicht und keinem Export für Dritte | 36–52 |
| M6 | Übergabe: Ressourcen-Baseline unter Last, Alarme, Helm-Values final, Übergabepaket T6 | T6-Checkliste vollständig beantwortet | 8–12 |

Summe: etwa 170–240 PT. M3 und Teile von M5 (Frontend-Sichten) lassen sich parallel zu M4
bearbeiten, wenn zwei Personen oder Agenten-Wellen arbeiten.

## 13. Aufgabenliste M0 (Fundament)

Schritt 0: `/better-coding-workflow` aufrufen (vor jedem Paket neu laden).
Alle Pfade relativ zu `kompetenzkartierer-ai/` (Wurzel des neuen Repositorys). Jede Aufgabe
beginnt mit dem roten Test.

0. **Ontologie übernehmen.** `ontology/` mit `ontologie/`, `vokabulare/`, `profile/`,
   `schemas/`, `werkzeuge/`, `pruefung/` aus `docs/recherche/ontologien/ergebnis/` des alten
   Repositorys, unverändert. Nachweis: `python -I ontology/pruefung/pruefe.py` meldet `OK`
   wie im alten Repository.

**Paket A: Gerüst und Betriebsseite**

1. **Projektgerüst.** `backend/pyproject.toml` (Python 3.13, FastAPI, pydantic-settings,
   psycopg 3 mit Pool, prometheus-client, rdflib, pyshacl; Dev: pytest, ruff, mypy),
   `backend/app/__init__.py`, `README.md`. Test `tests/test_import.py`: `import app` gelingt,
   `app.__version__` entspricht der Paketversion. Nachweis: `pytest -q` grün, `ruff check`
   und `mypy app` ohne Befund.
2. **Settings.** `app/core/settings.py`: alle Einstellungen als Env mit Defaults;
   Secrets (`OPENAI_API_KEY`, `MISTRAL_API_KEY`, `DATABASE_URL`, `S3_SECRET_KEY`, `API_KEY_PEPPER`) zusätzlich als
   `*_FILE`; `hide_input_in_errors`. Tests mit ausschließlich erfundenen Werten (nie
   `Settings()` aus der echten Umgebung): Defaults, `*_FILE` hat Vorrang, ein fehlendes
   Pflichtfeld nennt den Namen und keinen Wert.
3. **Zwei Ports.** `app/serve.py`, `app/api/internal.py` nach Vorbild compendious:
   öffentlich 8000, intern 9000 mit `/health`, `/ready`, `/metrics`. Tests: interne Pfade
   antworten am öffentlichen Port mit 404; `/ready` meldet 503, solange die Datenbank nicht
   erreichbar ist; die OpenAPI-Spec enthält keinen internen Pfad.
4. **OpenAPI-Metadaten.** Titel, Kurzbeschreibung, Beschreibung, Tags, Version aus dem
   Paket; `/openapi.json` am öffentlichen Port. Test: Felder vorhanden und nicht leer.
5. **Logging und Tracing.** `app/core/logging.py`, `app/core/tracing.py`,
   `app/api/request_log.py`: `LOG_FORMAT=text|json`, `LOG_LEVEL` geprüft, eine Zeile je
   Anfrage, `x-client-trace-id` und B3-Header werden übernommen und an ausgehende Aufrufe
   weitergereicht. Tests: JSON-Zeile enthält `trace_id` aus dem Header; ungültiges Level wird
   beim Start abgewiesen; kein Secret in der Logzeile.
6. **Metriken.** `app/core/metrics.py`: HTTP-Zähler und -Dauer, Job-Zähler nach Art und
   Ausgang, LLM-Aufrufe und Tokens; Multiprozess-Sammler. Test: `/metrics` am internen Port
   enthält die Namen, am öffentlichen Port 404.

**Paket B: Datenbank**

7. **Pool und Migrationsläufer.** `app/db/pool.py`, `app/db/migrate.py`,
   `migrations/0001_base.sql`: versionierte SQL-Dateien, Tabelle `schema_migration`,
   `pg_advisory_lock`, damit gleichzeitig startende Pods nicht doppelt migrieren. Tests
   gegen PostgreSQL (Compose-Dienst, Marker `pg`): zweimal parallel aufgerufen wird jede
   Datei genau einmal angewendet; eine neuere Datenbank als der Code wird abgewiesen.
8. **Grundtabellen.** `migrations/0002_core.sql`: `entity`, `account`, `role_grant`,
   `api_key` (Hash mit Pepper), `job`, `llm_usage`, `conversion_usage`, `quota`,
   `audit_log`; Erweiterungen `vector`, `pg_trgm`, `unaccent`. Tests: Fremdschlüssel und
   Eindeutigkeiten greifen; `entity.kind` ist Pflicht.
9. **Vokabular-Lader.** `app/vocab/loader.py`, `migrations/0003_vocab.sql`: lädt die
   TTL-Dateien aus `ontology/` (Pfad per Env) in `vocab_scheme`,
   `vocab_concept`, `vocab_release`; idempotent über den Hash. Tests: Anzahl der Schemata
   und Stufen in `lvl:` stimmt mit der TTL überein (24 und 135); zweiter Lauf ändert nichts;
   geänderte TTL ergibt einen neuen Stand.

**Paket C: Jobs, Auth, Speicher**

10. **Warteschlange.** `app/jobs/queue.py`, `app/jobs/worker.py`: anlegen, holen per
    `FOR UPDATE SKIP LOCKED` mit Spur je Konto, Lease mit Lebenszeichen, Freigabe bei
    Ablauf, Abbruch per Markierung, begrenzte Wiederholungen; Einstieg
    `python -m app.jobs.worker`. Tests: zwei Worker verarbeiten 50 Jobs ohne Doppelausführung
    (Stresslauf); ein Worker ohne Lebenszeichen verliert die Lease, ein anderer übernimmt;
    abgebrochene Jobs starten nicht mehr.
11. **Auth.** `app/core/auth.py`: eigene Schicht ohne B-API; Tokens vergibt ein Admin wie
    heute (gehasht mit Pepper, sperrbar); Rollen `admin`, `redaktion`, `nutzer`; Schalter
    `PUBLIC_ACCESS` (`off` | `lookup` | `search`) für den Zugang ohne Konto (§7.3). Tests:
    ohne Token 401 bei `off`; mit `lookup` sind veröffentlichte Lesepfade ohne Token
    erreichbar, Schreibpfade nicht; Endpunkte mit Sprachmodell antworten ohne Token immer 401;
    falsche Rolle 403; gesperrtes Konto 401; das Limit für Fehlversuche greift.
12. **LLM-Einstellungen.** `app/llm/settings.py`, `app/llm/client.py` nach dem heutigen
    Kompetenzkartierer: `OPENAI_BASE_URL` (Standard `https://api.openai.com/v1`),
    `OPENAI_MODEL` (Standard `gpt-6-luna`), `OPENAI_REASONING_EFFORT`,
    `OPENAI_TEXT_VERBOSITY`, `LLM_PROVIDER` (`openai` | `openai-compatible`),
    `LLM_CONTEXT_TOKENS`. Tests: Standardwerte; unbekannter Anbieterwert wird beim Start
    abgewiesen; die Wertelisten für Reasoning und Ausführlichkeit stimmen mit den Typen der
    Bibliothek überein; eine geänderte Basis-URL wird für Responses- und Chat-API genutzt
    (Aufruf über einen Mock-Transport); der Schlüssel erscheint in keiner Log- oder
    Fehlerzeile.
13. **Objektspeicher.** `app/core/storage.py`: Schnittstelle mit Dateisystem-Umsetzung
    (Tests, Entwicklung) und S3-Umsetzung (MinIO im Compose). Tests: Schreiben, Lesen,
    Löschen, Pfad-Ausbruch (`..`) abgewiesen; Integrationstest gegen MinIO mit Marker `s3`.

**Paket D: Images, CI, Übergabe, Frontend-Rahmen**

14. **Images und Compose.** `deploy/api.Dockerfile` (mehrstufig, slim, Digest gepinnt,
    Nutzer 10001, HEALTHCHECK am internen Port), `deploy/web.Dockerfile` (nginx
    unprivilegiert), `.dockerignore`, `deploy/docker-compose.yml` mit api, worker, migrate,
    postgres (pgvector), minio, optional redis; Härtungsanker wie compendious. Nachweis:
    `docker compose up` startet alles, `/ready` am internen Port meldet 200.
15. **CI.** Workflow im neuen Repository (`.github/workflows/ci.yml`): Prüfskript der Ontologie, ruff, mypy, Tests mit
    PostgreSQL-Dienst, Abdeckungsgrenze, Image-Build, Rauchtest, Tags `sha-<sha12>` und bei
    Git-Tags SemVer. Nachweis: grüner Lauf auf einem Testzweig.
16. **Übergabe-Gerüst.** `docs/uebergabe/anforderungen.md` (T6-Checkliste Punkt für Punkt, Variante ohne B-API),
    `konfiguration.md` (aus den Settings erzeugt; ein Test vergleicht beide),
    `deploy/helm-values.example.yaml` mit abschaltbaren Komponenten.
17. **Frontend-Rahmen.** `frontend/` mit Vite, Vue 3, TypeScript; übernommen: `style.css`
    (Tokens, Dunkelmodus), `t()` mit Katalog, HTTP-Client, Lade-, Leer- und Fehlerzustände,
    Dialoge mit Fokusfalle; statische Schutztests (fest eingetippte Texte, Katalog,
    Design-Tokens, Kontrast, axe-Helfer). Startseite mit Anmeldung und rollenabhängiger
    Navigation. Nachweis: `vitest run` grün, axe ohne Befund.

Pakete A und B sind die Voraussetzung; C und D können danach parallel laufen.

## 14. Verifikation

**M0-Abnahme**
- `docker compose up` startet api (2 Replicas), worker (2 Replicas), migrate, postgres, minio;
  die Migration läuft genau einmal.
- Öffentlicher Port: `/openapi.json` mit Titel und Beschreibung; `/health`, `/ready`,
  `/metrics` antworten 404. Interner Port: alle drei antworten.
- Eine Anfrage mit `x-client-trace-id` erscheint mit derselben ID in den JSON-Logs von api und
  worker.
- 50 Test-Jobs auf zwei Workern: jeder genau einmal ausgeführt; Abschuss eines Workers während
  eines Jobs führt zur Übernahme nach Ablauf der Lease.
- Image läuft als Nutzer 10001, enthält keine Daten oder Modelle; Größe wird gemessen und im
  Übergabedokument festgehalten.
- Vokabular-Lader: Zahlen stimmen mit `pruefe.py`-Lauf über `ergebnis/` überein.

**Später je Meilenstein:** Abnahmen aus Abschnitt 12, ausgeführt als Befehl mit Ausgabe
(`/better-coding-verify`). Regressionen: die Tests aller vorigen Meilensteine laufen in jedem
CI-Lauf mit.

## 15. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Kern 1.0 ist ein Entwurf und noch nicht eingecheckt | in M0 als `ontology/` ins neue Repository übernehmen und dort versionieren; `docs/recherche/` im alten Repository als Archiv committen; Änderungen am Kern laufen über `pruefe.py` und einen Vokabular-Stand |
| Alte App bleibt parallel stehen | eingefroren: nur Betrieb und Fehlerbehebung, keine neuen Funktionen, keine Datenübernahme |
| Wikipedia-Texte unter CC BY-SA | Quelle, Autorenhinweis und Lizenz an jeder Anzeige; Modelltexte auf dieser Grundlage mit derselben Lizenzangabe; getrennt vom Lehrplanwortlaut |
| pydantic-ai kennt `gpt-6-luna` nicht (Haltepunkt, Reasoning-Kontext) | Modellprofil in M0 prüfen wie im heutigen Kompetenzkartierer; Anfragekörper per Mock-Transport abfangen und vergleichen |
| Ein anderer Anbieter hinter `OPENAI_BASE_URL` kann weder Responses-API noch Prompt-Cache | `LLM_PROVIDER=openai-compatible` nutzt Chat Completions; Budget und Abrechnung zählen trotzdem je Aufruf |
| Konvertierung braucht bis 4,5 GB RAM je Job | eigener `converter` mit 1 Job je Pod und Ressourcengrenzen |
| Rechte an Wortlauten ungeklärt | Lizenzprüfung der Länder läuft; bis dahin Rechtestatus `unklar`; Markdown und Zitate für Dritte verbergbar (§7.4) |
| Datenqualität bei Masse | Abschnitt 7: Goldstandard, Kalibrierung, Verteilungsalarm, Redaktion |
| Laufzeitabhängigkeit vom Netz (LLM, MEM, ESCO) | Caches in PostgreSQL, Fristen, Schutzschalter; Normdaten lokal ab M3 |
| Umfang wächst in M4/M5 | jeder Meilenstein mit eigenem Plan und Freigabe |

## 16. Offene Fragen (mit Empfehlung)

1. **Lizenzen der Länder:** Die Prüfung läuft (Nutzer). Ihr Ergebnis setzt die Rechtestatus
   je Quelle und damit die Standards für Dritte (§7.4). Bis dahin gilt `unklar`.
2. **Embedding-Modell:** entschieden am 22.10.2026, zweistufig lokal (§7.2). Offen ist nur
   die Schwelle für die e5-Neuordnung; sie folgt aus der Messung in M3.

Annahme für die Auslegung (keine Frage, im Lastlauf von M4 geprüft): 300.000–500.000
Elemente für alle Lehrpläne Deutschlands; die Vergleichs-App hat rund 300.000 Knoten nur für
die allgemeinbildende Schule und nur Struktur.

**Entschieden:**
- 21.10.2026: keine B-API und keine Anbindung an WLO/edu-sharing; LLM wie im heutigen
  Kompetenzkartierer; eigenes Repository Kompetenzkartierer-AI im Unterordner
  `kompetenzkartierer-ai/`; Entity-Linking mit eigenen Wikidata/GND-Indizes.
- 22.10.2026:
  - möglichst wenig Dritte live, lokale Abzüge per Sidecar, schmales Hauptvolumen;
  - Anmeldung über Tokens vom Admin; Nachschlagen und Suchen optional ohne Konto; KI nur mit
    Token;
  - Lernende ohne Registrierung, Profile und Lernwege später;
  - Wortlaute bleiben gespeichert, Anzeige und Weitergabe nach Rechtestatus, jederzeit
    sperrbar;
  - der Vergleichsdatensatz dient nur als Saat für das Quellregister;
  - keine Datenübernahme aus der alten App (nur Testextrakte);
  - Wikipedia-Archiv (ZIM) eingeplant, auch als Wissen zu Themen und Entitäten;
  - Markdown-Extrakte und Zitate für Dritte verbergbar.
