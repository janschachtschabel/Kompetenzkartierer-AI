# Detailplan M1: Quellen und Extraktion L1

Stand 22.10.2026, Fassung 2 (nach der Planprüfung), Entwurf zur Freigabe. Teil des
[Gesamtplans](2026-10-21-gesamtplan.md), Abschnitt 12 (M1, 40–55 PT). Ziel: Lehrpläne aus dem
Quellregister über Konvertierung (X0) und Extraktion (X1–X4) mit Prüfung (X5) und Reparatur
(X6) als L1-Daten nach Curriculum-Kern 1.0 erfassen, mit Abrechnung, schemagetriebenem Editor,
Redaktion und Festschreiben. Voraussetzung: M0 einschließlich Paket D.

## Arbeitsweise

- Wie in M0: je Paket Schritt 0 `/better-coding-workflow` laden (bei Oberfläche zusätzlich
  `/better-coding-frontend`); jede Aufgabe beginnt mit dem roten Test; nach jedem Paket
  `/better-coding-review` mit frischen Prüfern in Scheiben, Befunde mit
  `/better-coding-workflow` beheben, Korrekturen gezielt auf Rückschritte prüfen lassen, dann
  `/better-coding-verify` und `main` per Fast-Forward. Kein Push ohne Auftrag.
- **Migrationsnummern** vergibt erst der Merge auf `main` (der Läufer lehnt Lücken ab). Im Plan
  stehen Migrationen mit Namen; parallel laufende Pakete nummerieren beim Rebase neu.
- **Kein echtes Sprachmodell in Tests:** Modellaufrufe laufen gegen `FunctionModel` bzw. einen
  httpx2-Mock-Transport hinter `build_model`. Echte Läufe nur in der Abnahme (Paket 11), nach
  Kostenschätzung und Zusage des Nutzers; der Schlüssel kommt aus seiner Umgebung, nie in
  Dateien oder Ausgaben.
- **Downloads:** `python-multipart`, `pdfplumber`, `pdfminer.six`, `pypdfium2` und die
  Docling-Pakete liegen im lokalen uv-Cache; die tiktoken-Kodierung `o200k_base` (3,6 MB) im
  tiktoken-Cache. Neu zu laden wären nur die Docling-, Layout- und OCR-Modelle (Paket 3b, eigene
  Freigabe), die Linux-Pakete für das Image (freigegeben am 22.10.) und die Abnahme-PDFs (vorher
  einzeln mit Titel, Adresse und Größe genannt).
- **Rechenlast nie in der Event-Loop:** Konvertierung im Kindprozess; SHACL, unscharfe
  Ankersuche und Lexikon-Muster über `asyncio.to_thread` bzw. einen Prozess-Pool; der
  synchrone Objektspeicher über `asyncio.to_thread`. Sonst verliert der Job seine Lease.
- Neue Einstellungen kommen mit ihrer Aufgabe in `Settings`/`LLMSettings` und in
  `docs/uebergabe/konfiguration.md` (der Test aus Paket D vergleicht beide).
- Vorlagen der alten App über 300 Zeilen (TreeView 480, JobProgress 388, ContextEditor 358,
  UploadPanel 343, TreeNodeItem 313, `llm.py` 602, `anchors.py` 537) werden beim Kopieren
  nach Zuständigkeit geteilt.

## Festlegungen für M1

- **Ontologie als Quelle:** Pflichtwerte mit festem Schema (Aussageart, Adressat, Funktion,
  Herkunft, Fundart, Stufe, Verbindlichkeit, Bereich, Prüfstand …) sind zusammengesetzte
  Fremdschlüssel `(scheme_iri, iri)` auf `vocab_concept`; die dafür nötige Eindeutigkeit
  `UNIQUE (scheme_iri, iri)` kommt mit der ersten Domänentabelle (M0-Festlegung). Profilwerte
  (Knotentyp, Unterart, Dokumenttyp) verweisen auf `vocab_concept.iri`; die App prüft, dass sie
  zum aktiven Profil gehören und ihr `skos:broader` den Kernwert trifft. Neue Schreibzugriffe
  prüfen `retired_in IS NULL`. Ausgabeschemas der LLM-Stufen sind die Dateien in
  `ontology/schemas/`, eingelesen als `pydantic_ai.StructuredDict`.
- **Was der Kern nicht kennt, regelt die App** (Gesamtplan §7): Rechtestatus (`amtlich`,
  `offen_lizenziert`, `geschuetzt`, `unklar`, Standard `unklar`), Quelltyp (`amtlich`,
  `archiv`, `spiegel`, `sekundaer`) und Registerstatus (`unchecked`, `reachable`,
  `unreachable`, `acquired`; in der Oberfläche „ungeprüft" usw.) sind CHECK-Listen. Woher ein
  Registereintrag oder Hinweis stammt, steht in einer eigenen Spalte `provenance`
  (`upload`, `url`, `vergleichsdatensatz-v62.493`, `laenderrecherche`, `ttl`, `recherche`,
  `redaktion`), nie in `origin`: `origin` ist die Kern-Herkunft (`cv:Origins`) eines Werts.
  Der Prüfstand an Knoten und Aussagen nutzt `cv:ReviewStatuses` als Fremdschlüssel.
- **Fundstelle ist Pflicht** (konzept §5.4, `cur-shapes.ttl`): Auch von Hand angelegte Aussagen
  hängen an einer Quelle. Im Formular wählt die Redaktion Blöcke als Fundstelle; findet sie
  keinen passenden, entsteht eine Fundstelle mit Seite und Fundart `notFound`. Ganz quellenlose
  Entwürfe gibt es in M1 nicht; sie bräuchten eine Änderung am Kern über `pruefe.py`.
- **Tabellen**, jede adressierbare Zeile über `entity (id, kind)`:
  - Register: `source`, `source_file`, `acquisition`, `access_note`, `host_throttle`.
  - X0: `conversion`, `document_block`, `conversion_usage`.
  - L1: `work`, `document`, `document_profile`, `specification`, `variant`,
    `document_specification`, `node`, `statement`, `statement_addressee`, `anchor`,
    `anchor_block`, `frame_part`, `extraction_run`, `validation_finding`.
  - Lexikon: `terminology_profile`, `lexical_cue`, `cue_review`.
  - Abrechnung: `llm_usage`, `quota`, `usage_reservation`.
  - `frame_part` hält die X3-Ergebnisse (Kompetenz- und Niveaumodelle, Operatoren, Legende,
    Regeln) als Schemaobjekt mit Belegblöcken; typisierte L2-Tabellen folgen in M3. Geltung
    (`programme`, `qualification`, `occupation`) folgt mit dem Andocken in M3; bis dahin hält
    `specification` den Feldtext und `variant` die Varianten aus X1. Platzierungen über mehrere
    Spezifikationen folgen mit M2 (MEM) bzw. M3.
  - Tiefe eines Knotens wird aus `parent_id` abgeleitet, nicht gespeichert.
- **Block-IDs** `p<Seite>-b<Block>` (Muster aus `cur-shapes.ttl`), Seite physisch und 1-basiert;
  gedruckte Seitenzahl separat, wenn erkennbar. Der Dokumenttext für die Prompts ist der
  Blocktext mit vorangestellter Block-ID je Block.
- **Jobs:** Arten `source.fetch`, `source.check`, `source.convert`, `extract.run` (X1–X4,
  danach X5), `extract.repair` (X6). Handler bekommen ihre Abhängigkeiten über einen
  `JobContext` (Pool, Speicher, Settings, Modellfabrik) aus `make_handlers(context)`; keine
  Modul-Globalen. Fortschritt steht in `job.progress` (Code + Parameter, lease-geprüft); jeder
  Job trägt die Trace-ID seiner Anfrage, der Worker loggt mit ihr. `WORKER_KINDS` beschränkt
  einen Worker auf Arten, so laufen Konvertierungen in eigenen Pods mit einem Job je Pod
  (Gesamtplan §6.1). Endpunkte, die einen Job anlegen, antworten 202 mit der Job-ID.
- **Sichtbarkeit in SQL, an `source` und `document`, nie an `source_file`** (die Datei wird
  kontenübergreifend über SHA-256 geteilt). Registereinträge ohne Eigentümer (Saat,
  Recherche) sehen alle Konten als Metadaten; Datei, Blöcke und Markdown sehen nach
  `THIRD_PARTY_MARKDOWN` (`hidden` | `accounts` | `public`, Standard `hidden`) nur
  Eigentümer, Redaktion und Admin (Gesamtplan §7.4.7). Dateien gehen mit
  `Content-Disposition: attachment` und `X-Content-Type-Options: nosniff` hinaus.
- **Kosten:**
  - `llm_usage` je Aufruf (Eingabe, davon Cache, Ausgabe, Anfragen, unbeantwortete Anfragen),
    `conversion_usage` je Konvertierung (Seiten, Engine, abrechenbar).
  - Grenzen je Konto in `quota` (Token, Seiten; `NULL` = unbegrenzt; Seitengrenze nur für
    abrechenbare Engines, pdfplumber ist es nicht).
  - Jede Anfrage setzt `max_output_tokens` (Responses) bzw. `max_completion_tokens` (Chat) auf
    `LLM_MAX_OUTPUT_TOKENS`; Reasoning zählt darin mit. Die Wiederholungen des SDK sind aus
    (`max_retries=0`); Warten bei 429/5xx übernimmt die eigene Schleife, und jeder Versuch
    reserviert neu. Ausgabe-Wiederholungen des Agenten (`retries`) zählen als eigene Versuche.
  - Vor jedem Versuch reserviert der Job in einer Transaktion mit `SELECT … FROM quota …
    FOR UPDATE` die Obergrenze (Eingabe nach tiktoken + `LLM_MAX_OUTPUT_TOKENS`); danach
    ersetzt die Buchung die Reservierung. Bricht ein Job ab, wird seine offene Reservierung als
    Verbrauch gebucht (gekennzeichnet `estimated`), nicht freigegeben: der Anbieter hat schon
    gerechnet.
  - Gezählt wird für jeden Anbieter mit tiktoken (`o200k_base`, lokal); die Präfixgrenze trägt
    einen Sicherheitsabstand von 10 %.
  - Höchstens `MAX_JOBS_IN_FLIGHT` (Standard 20) wartende oder laufende Modelljobs je Konto;
    darüber antwortet der Start mit 429 und `Retry-After`.
- **Rate-Limits** (Gesamtplan §9) je Konto in der Datenbank (Redis bleibt optional): Uploads,
  URL-Importe und Starts von Modelljobs je Minute, einstellbar; darüber 429.
- **Metriken:** Jobs nach Art und Ausgang, Laufzeit, Lease-Verluste; Modellaufrufe, Token,
  Fehler; Konvertierungen und Seiten; Reservierungen. Der Worker bedient `/metrics` auf einem
  eigenen internen Port.
- **IRIs** nach konzept §11 mit Basis `IRI_BASE`, vergeben beim Festschreiben; vorher tragen
  Dokumente eine Entwurfs-IRI aus ihrer UUID. Das Werk setzt die Redaktion ausdrücklich
  (X1 schlägt vor, konzept §5.1). Fehlende Codes vergibt die Pipeline aus der Position
  (`code_assigned`). `text_hash` nach konzept §11.
- **Festschreiben und Revisionen:** Ein Dokument ist eine Fassung. Festschreiben erzeugt eine
  unveränderliche Revision (`document.frozen_at`, `revision`); ein Trigger weist Änderungen an
  Knoten, Aussagen und Fundstellen festgeschriebener Revisionen ab. „Als Entwurf kopieren"
  öffnet eine neue Revision derselben Fassung (gleiche IRIs, Prüfstand übernommen); beim
  nächsten Festschreiben ersetzt sie die vorige, die als Verlauf lesbar bleibt. Eine neue
  amtliche Fassung ist ein neues Dokument mit `supersedes` (über die Quelle, nicht über den
  Editor).
- **Lesekontext** nach konzept §13.1: Präfix aus Blocktext, Dokumentprofil (X1) und
  Auswahllisten (X3), dahinter `CachePoint`, danach der Auftrag je Einheit. Byte-gleich ist der
  Präfix für alle X4- und X6-Aufrufe eines Dokuments (X1 und X3 laufen vorher). Zu lange
  Dokumente: Titelei, Inhaltsverzeichnis, Rahmenteile und der Abschnitt der Einheit samt
  Nachbarn.
- **Extraktionstiefe** nach konzept §5.3 (`cv:ExtractionDepths`, am Knotentyp): `skip` →
  kein X4-Aufruf; `typed` → nur Knoten typisieren; `full` → Aussagen. Das ist der größte
  Kostenhebel.
- **Werte aus Regeln** (Gesamtplan §7.1.8) tragen Herkunft `rule` und eine Regelkennung
  (`rule_id`), nie den Anschein eines Wortlauts.
- **Lexikon bleibt TTL** (Gesamtplan §5, konzept §12.4): Die Recherche-Übernahme schreibt
  `ontology/profile/laender/<bereich>-DE-XX.ttl` (geprüft in Git, `pruefe.py` grün); geladen wird
  wie alle Profile. Entscheidungen der Redaktion (Stichprobe, neue Begriffe) stehen in
  `cue_review` und gehen per Werkzeug zurück in die TTL. Hinweis-Muster laufen über das Paket
  `regex` mit Zeitgrenze (ReDoS).
- **Rohantworten** jedes Modellaufrufs liegen im Objektspeicher unter
  `runs/<run-id>/<stufe>/<n>.json` (Stufe klein, z. B. `x4`); `extraction_run` verweist darauf.

## Pakete

Reihenfolge: der schmalste durchgehende Schnitt zuerst (Upload → Register → Konvertierung →
Blockansicht), dann Daten und Abrechnung, dann die Stufen, dann Editor und Lexikon.
Abhängigkeiten: 2 und 3 nach 1; 4 nach 3; 5 nach 4; 6 nach 5; 7 nach 6; 8 nach 7; 9 nach 8;
10.1–10.3 nach 4 (parallel zu 5–9), 10.4 nach 6; 3b nach 3, sobald freigegeben; 11 zuletzt.
Summe rund 52 PT, mit 3b 55 PT.

### Paket 1: Quellregister und Upload (4 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 1.1 | Speicher in der App | `app/api/app.py` (`app.state.storage` aus `open_storage`, Paket D), `app/core/storage_async.py` (`put/get/exists/delete` über `asyncio.to_thread`) | `create_app` öffnet den Speicher und bricht bei fehlendem `STORAGE_DIR` oder Bucket mit Namen ab (`open_storage` fragt bei S3 einmal `head_bucket`, also im Lifespan per `to_thread`); Aufruf blockiert die Loop nicht (Loop-Wachhund im Test) | `pytest tests/api/test_app.py tests/core/test_storage_async.py` |
| 1.2 | Job-Kontext, Fortschritt, Trace | `app/jobs/context.py` (`JobContext`, `make_handlers`), Migration `job_progress` (`job.progress`, `job.trace_id`), `app/jobs/queue.py` (`report_progress`), `WORKER_KINDS` | Handler bekommt Pool und Speicher aus dem Kontext; Fortschritt nur mit gültiger Lease; Worker loggt mit der Trace-ID des Jobs; Worker nimmt nur seine Arten | `pytest -m pg tests/jobs/` |
| 1.3 | Job-Metriken | `app/core/metrics.py`, Worker-Metrikport: `INTERNAL_PORT` wie die API (in 1.3 entschieden statt eines eigenen `WORKER_METRICS_PORT`: im Cluster hat jeder Pod seinen Port; ein Worker neben der API auf demselben Rechner braucht ein eigenes `INTERNAL_PORT`) | Zähler je Art und Ausgang, Laufzeit, Lease-Verlust in `/metrics` des Workers; `/health` am selben Port für die Liveness-Probe, die das Helm-Beispiel bis dahin offenlässt | `pytest tests/jobs/test_worker_metrics.py` |
| 1.4 | Job-Abfrage | `app/api/jobs.py` (`GET /api/v1/jobs/{id}`, `POST …/cancel`) | fremde Jobs 404; Status, Fortschritt, Fehlercode; Abbruch nur für die eigene Spur | `pytest tests/api/test_jobs.py`, `test_auth_surface`, `test_openapi` |
| 1.5 | Dateiprüfung | `app/sources/filetype.py`, `app/sources/archives.py` (Kopie `filetype.py` der alten App mit Tests) | Magic Bytes PDF; ZIP-Regeln (5.000 Teile, 256 MiB, 100× je Teil > 1 MiB); unbekannter Typ abgewiesen | `pytest tests/sources/test_filetype.py` |
| 1.6 | Tabellen Register | Migration `sources`: `source` (`provenance`, Rechtestatus, Quelltyp, Registerstatus, Eigentümer), `source_file` (SHA-256 eindeutig), `acquisition` | CHECK-Listen greifen; gleiche Datei zweimal → eine `source_file`, zwei `source`; `entity.kind` passt | `pytest -m pg tests/db/test_sources_schema.py` |
| 1.7 | Upload | `app/api/sources.py` (`POST /api/v1/sources`, multipart nach der Tokenprüfung gelesen und vom Parser beim Zwischenspeichern gezählt, `MAX_UPLOAD_MB` 50 → 413 nach dieser Größe vor dem Lesen, danach die Datei einmal im Speicher), `app/db/sources.py`, Abhängigkeit `python-multipart`, Rate-Limit Uploads | Datei unter `sources/<sha256>`; 413/415 mit eigenem Code; Konto nötig; Audit-Zeile; 429 über dem Limit | `pytest tests/api/test_sources_upload.py` |
| 1.8 | URL-Import | `app/sources/url_fetch.py` (aus `url_import.py` + `http_body.py`, auf httpx2, `trust_env=False`, IP-Pinning: Verbindung nur zur geprüften Adresse, Trace-Header über `outgoing_headers`), Job `source.fetch`, Rate-Limit | nur http/https; private, Loopback- und Link-Local-Adressen abgewiesen, auch nach Weiterleitung und bei wechselnder DNS-Antwort; Größengrenze nach Entpacken | `pytest tests/sources/test_url_fetch.py tests/jobs/test_source_fetch.py` (Mock-Transport) |
| 1.9 | Register lesen | `GET /api/v1/sources` (Seiten, Filter Status/Land/Herkunft/Text), `GET /api/v1/sources/{id}` mit Abrufkette, Quelltyp, Lizenz | Sichtbarkeit in SQL (fremder Upload 404); Metadaten der Saat für alle Konten | `pytest tests/api/test_sources_read.py` |
| 1.10 | Register pflegen, Datei holen | `PATCH /api/v1/sources/{id}` (Eigentümer: Titel, Land, Bereich; Redaktion zusätzlich die Bedingungen: Rechtestatus mit Beleg, Quelltyp, Lizenz), `GET …/file` | `nutzer` darf den Rechtestatus nicht setzen (403); Datei nach `THIRD_PARTY_MARKDOWN`, mit `attachment` und `nosniff` | `pytest tests/api/test_sources_edit.py` |
| 1.11 | Oberfläche Register | `views/SourcesView.vue`, `components/UploadForm.vue` und `components/ImportForm.vue` (statt eines `UploadPanel.vue`: je Formular eine Aufgabe), `components/SourceTable.vue`, `components/JobProgress.vue` auf `jobWatch.ts` (Backoff auch im Lauf, nicht nur bei Fehlern wie in der alten App), `api/sources.ts`, `api/jobs.ts`, Katalogtexte, `refusals.ts` (+ Test) für 413/415/429, `jobMessages.ts` für die Fehlercodes der Jobs; `GET /api/v1/info` nennt `max_upload_mb`, damit die Seite eine zu große Datei vor dem Senden abweist | Lade-, Leer-, Fehlerzustand; Upload mit `role="status"`; URL-Formular; Fortschritt mit Backoff 1→8 s, Stopp bei 401/404; axe ohne Befund | `vitest run`, Browser-Probe |

### Paket 2: Saat aus dem Vergleichsdatensatz und Prüfjob (3 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 2.1 | Daten ins Repository | `data/seed/vergleichsdatensatz/{lehrplan_dokumente_de,umgehungshinweise_de}.csv` (CC0, v62.493) mit `README.md` (Herkunft, Lizenz, Prüfsummen) | Prüfsummen gleich denen im README | `pytest tests/sources/test_seed_files.py` |
| 2.2 | Saat-Import | `app/sources/seed.py`, `python -m app.sources.seed` | `provenance` `vergleichsdatensatz-v62.493`, Status `unchecked`; ESA-Ableitungen und „kanonisch" ausgelassen; `URL=lokal` nimmt `URL_Original`; zweiter Lauf ändert nichts; übernommen die Felder aus §7.5, dazu Bildungsstufe, Fach-Schlüssel und Wayback-Zeitstempel; Titel, Themen, Knotenzahlen nicht übernommen; Zählung: 1.498 Einträge, 1.278 Adressen (1.279 Zeichenketten: eine trägt einen Vermerk in Klammern und gleicht einer anderen), 34 Hosts | `pytest -m pg tests/sources/test_seed.py` |
| 2.3 | Zugangsnotizen | Migration `access_notes`, Import aus `umgehungshinweise_de.csv` | Kategorie, Land, Hinweis, URL; Zuordnung je Land, Schulform, Fach (leer = alle); Notizen ohne passenden Eintrag bleiben gespeichert, werden aber erst mit einem passenden Eintrag gezeigt; Anzeige im Register | `pytest -m pg tests/sources/test_access_notes.py` |
| 2.4 | Länderrecherche T1 als zweite Saat | `app/sources/research_t1.py` mit einem Spaltenleser je Auftrag (Schule, Elementar, Beruf, Hochschule, EB) | `provenance` `laenderrecherche`, Beleg E/S übernommen; Quelltyp aus dem Host (GEI-Depot, Wayback: Archiv; umwelt-online: Sekundärquelle) oder dem Vermerk an der ersten Adresse (bis zum nächsten „\|", ohne weitere Adresse darin, beginnend mit Archivkopie, Spiegel, Schulkopie oder Sekundärquelle), gültig für jeden Eintrag derselben Adresse: 5 Archiv, 7 Spiegel, 12 Sekundärquelle; Abgleich: URL nur in Saat, nur in Recherche, in beiden; Zählung: 668 Dokumente aus 684 Zeilen (6 durch ein Semikolon verschoben, 9 ohne Adresse, 1 ohne Titel), 593 Adressen; 34 weitere Adressen in den URL-Feldern der Einträge gezählt, nicht übernommen (`further_address`); Abgleich 1.210 nur Saat, 525 nur Recherche, 68 in beiden | `pytest -m pg tests/sources/test_research_t1.py` |
| 2.5 | Prüfjob | Job `source.check`: ein Abruf je URL (Status, Typ, Größe, SHA-256, Datum), Inhalt nur gestreamt und gehasht, nicht gespeichert; `host_throttle` hält den Abstand je Host über alle Worker (`CHECK_HOST_INTERVAL_S`, 2 s); robots.txt beachtet, auch für jedes Weiterleitungsziel, das zudem seinen Takt nimmt; eigener User-Agent (`FETCH_USER_AGENT`), keine Trace-Header an fremde Hosts; Stand je URL sofort gespeichert, ein wiederholter Job überspringt endgültig Geprüftes – 429/503 (`throttled`, `Retry-After` ≤ 1 Tag) und 502/504/Zeitüberschreitung/Verbindungsabbruch (`unavailable`) fragt er erneut, die übrigen Adressen des Hosts warten mit; ein später gesäter Kandidat übernimmt das Ergebnis seiner Adresse; Start per `POST /api/v1/sources/checks` (nur Admin, 409 `check_running`); Umfang nach beiden Saaten 1.803 Adressen auf 143 Hosts | Mock-Transport: 200/404/403/429/Weiterleitung/Zeitüberschreitung ergeben die richtigen Status; 403/429 werden vermerkt, nicht umgangen (kein anderer User-Agent, kein automatischer Wechsel auf Archiv oder Spiegel); HTML-Seiten bekommen den Typ `html` (konvertierbar erst mit 3b) | `pytest -m pg tests/jobs/test_source_check.py` |
| 2.6 | Oberfläche | Filter „Kandidaten", Prüfstart (Admin), Zugangsnotiz je Eintrag | Zustände, Tastatur, axe | `vitest run` |

### Paket 3: Konvertierung X0 mit Block-IDs (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 3.1 | Engine-Schnittstelle | `app/conversion/base.py` (`Block(id, page, kind, text, bbox, font_size, bold, italic, cells)`, `Cell(id, page, row, column, text, header)`, `Conversion(engine, engine_version, pages, printed_pages, blocks, findings)`, Register mit `offered_engines`, Engines erst beim Aufruf importiert), `text_layer.py` aus der alten App (eine unlesbare Datei ist ein eigener Fall, nicht „braucht OCR“); `table_md.py` erst mit Docling (3b) | Block-ID-Muster gleich dem in `cur-shapes.ttl`; Zell-IDs ab 1 wie das Kern-Beispiel `T4:r3c2`; Register nennt angebotene Engines | `pytest tests/conversion/test_base.py` |
| 3.2 | pdfplumber-Blöcke | engine-neutral `app/conversion/layout.py` (Rohtypen), `lines.py` (Wörter → Zeilen → Blöcke), `tables.py` (Kopfzeile, über Seiten), `assemble.py` (Lesereihenfolge, Namen); `pdfplumber_blocks.py` (die Engine), Abhängigkeiten `pdfplumber`, `pdfminer.six`, `pypdfium2` | Zeilen zu Blöcken nach Abstand (≤ 0,5 × Größe) und Schriftwechsel; fett/kursiv aus dem Schriftnamen (auch Adobe-Kurzformen `Bd`, `It`); Tabellen als ein Block mit Zellen `T<n>:r<i>c<j>`, Kopfzeile aus fetten Zeichen; Tabellen über Seiten zusammengeführt (gleiche Spaltenzahl, keine oder dieselbe Kopfzeile); Lesereihenfolge; Testdateien aus `backend/tools/make_conversion_fixtures.py` (reportlab, invariant; die PDFs der alten App sind nicht eingecheckt). Nachtrag nach dem Review: Zeilen nach senkrechter Überlappung (Hoch- und Tiefstellung bleiben in der Zeile), ein Leerzeichen nur bei einer Lücke; Spaltenzwischenräume bestätigt über mehrere Zeilen mit bündig beginnender nächster Spalte und Text von mindestens 4 × Größe auf beiden Seiten (Aufzählungszeichen und Nummern sind keine Spalte), dann auch für Nachbarzeilen geltend (bis eine Zeile entfernt, sonst nur bei einer Lücke von mindestens dem Doppelten der übrigen Wortabstände: Blocksatz über die volle Breite unter Spalten bleibt heil; `gutters.py`), Lesereihenfolge per XY-Schnitt (`reading_order.py`); Zeilen nach der Spanne ihrer häufigsten Größe; ein viel höheres oder niedrigeres Wort klebt an keinem Wort, das mehr als doppelt so groß ist; ein einzelnes solches Wort gehört zu der einen nahen Zeile, deren Spanne seine Mitte hält, wenn die größere der beiden keine weitere Zeilenmitte der Seite deckt (Fußnotenmarke vor ihrer Notiz, „[1]“ im Satz), ein viel höheres nur, wo es höchstens so weit neben einem Wort der Zeile steht, wie dieses groß ist (Operator einer Formel), eine Überschriftennummer so weit, wie sie selbst groß ist („3 Ziele und Inhalte“); mehrere viel kleinere Wörter gehören zur Zeile nur zwischen ihren Wörtern („[1, 2]“ im Satz); Wasserzeichen, Initiale, Symbol neben zwei Zeilen und mehrere viel kleinere Wörter neben der Zeile (Randnotiz, Beschriftung hinter einem Titel) bleiben eigene Zeilen; eine kleiner gesetzte Hoch-/Tiefstellung oder Fußnotenmarke gehört zur Zeile ihres Wortes; doppelt gedruckte Zeichen einmal gelesen; Tabellen über Seiten: das Seitenende ist der tiefste Inhaltsblock, fortgesetzt wird mit dem obersten Block unter dem Teil, ein angehängter Teil, der am tiefsten endet, hält die Kette offen; senkrechter Text, Text außerhalb der sichtbaren Seite (CropBox, auch bei /Rotate gedreht), unter 1 pt und ohne endliche Lage verworfen – auch in Tabellenzellen – und als Befund `text_dropped` in Zeichen gezählt; Steuerzeichen und einzelne Surrogate entfernt; liest pdfplumber andere Seiten als die Textebene zählt, ist die Datei `unreadable` (gezählt, bevor die Seiten gebaut werden); mehr als 100.000 Zeichen auf einer Seite, wie pdfplumber sie liest, sind `too_dense`. Zur Messung an echten Dokumenten in Paket 11: 1,5-zeiliger Satz zerfällt in Einzelzeilen-Blöcke; Tabulator-Listen mit breiter erster Spalte werden spaltenweise gelesen; eine Seite, deren zweite Spalte nur 1–2 Zeilen hat, bleibt verschränkt; eine Initiale oder ein Randsymbol steht als eigener Block vor seinem Absatz; ein Formel-Operator ohne Abstand zu seinem Nachbarn wird mit ihm zu einem Wort gelesen („F = Sf(x) dx“); die erste Zeile über die volle Breite direkt unter Spalten kann noch geteilt werden; kleiner gesetzte Wörter hinter einer Überschrift auf ihrer Höhe (Stundenangabe) bleiben eine eigene Zeile; eine 8-pt-Notiz neben 11-pt-Text klebt an der Zeile; mehrere viel größere Wörter zwischen Wörtern einer Zeile bleiben eine eigene Zeile; „[1]“ im Satz neben einer Randnotiz auf gleicher Höhe verlässt den Satz; „[1, 2]“ am Zeilenende und eine kurze letzte Zeile mit mehrheitlich klein gesetzten Zeichen werden eigene Blöcke | `pytest tests/conversion/` |
| 3.3 | Rand, Symbole, Kodierung | `app/conversion/page_edges.py` (aus `repeated_blocks.py`: oberste und unterste 8 % der Seite, ab 3 Wiederholungen und einem Fünftel der Seiten, ein Seitenzahl-Block immer), `app/conversion/symbols.py`, `app/conversion/encoding.py` | Kopf-/Fußzeilen markiert statt gelöscht (Nachtrag nach dem Review: ein Block ganz in der Zone, oder einer von höchstens drei Zeilen, der dort beginnt und innerhalb von 12 % endet – dieser als Seitenzahl nur, wo sie auf mindestens drei Seiten mitläuft, gleich wie lang das Dokument ist (zwei Fußnoten mit gleichem Versatz zählen nicht), und liegt eine Gruppe zur Hälfte oder mehr dort, als mitlaufende Zählung nur neben selbst mitlaufenden Seitenzahlen im Fuß; Text mit Zahlen zählt als Wiederholung nur, wo jede Zahl bleibt, mit der Seite läuft – jeder Versatz auf zwei Seiten, ein Sprung im Zählen bleibt mitlaufend – oder abschnittsweise bleibt neben einer mitlaufenden; eine Zahl läuft nur so wie die Seitenzahlen des Fußes, eine Seite, deren Fuß widerspricht (Fußnote, Druckfehler), fällt aus der Zählung, mindestens die Hälfte muss passen; widersprechen selbst mitlaufende Seitenzahlen, zählt die Seite dagegen: es läuft, wo nicht mehr Seiten widersprechen, als der Fuß bestätigt (Druckfehler in einem Kopf, Fuß mit einem zweiten Teil ab 1, der nicht länger ist als der erste) – „Lernfeld 1 … 5“ oben bleiben Überschriften; eine allein stehende Zahl oben nur, wo sie mitläuft und zum Fuß passt, eine Jahreszahl allein unten nur, wo sie wiederkehrt. Offen für Paket 11: nummerierte Überschriften ganz in der Zone auf Folgeseiten ohne Fußzahl werden Kopfzeile; eine einzeilige Fußnote „… S. 40“ im Fuß gilt als Seitenzahl, und zwei solche mit gleichem Versatz nehmen einem nummerierten Kolumnentitel ohne Fußzahlen die Zählung; drei Fußnoten mit gleichem Versatz knapp über dem Fuß gelten als Seitenzahlen; zwei Seitenzahlen knapp über dem Fuß eines Dokuments von drei Seiten bleiben ungelesen); gedruckte Seitenzahl erkannt (arabisch, römisch in einer Schreibung, auch die mitlaufende Zahl eines Kolumnentitels); U+F0DA → ➔ und U+F0DE → ⇒ (konzept §13.2); jedes andere Zeichen der Private Use Area bleibt stehen und wird gezählt (Befund `unmapped_symbol` mit Codepunkt und Seiten); Anteil kaputter Zeichen (Ersetzungszeichen, `(cid:n)`, doppelt kodiertes UTF-8) ab 1 % und 20 Stück → Befund `encoding_suspect` | `pytest tests/conversion/` |
| 3.4 | Kindprozess | `app/conversion/runners.py` (spawn, Antwort als Datei, ohne Settings; das Kind loggt in Level und Format des Dienstes unter der Anfrage des Jobs, die PDF-Bibliotheken höchstens Warnungen), `app/conversion/convert.py` (Ablehnungen `unreadable` – auch eine Seite, die die Datei zählt, aber nicht hergibt –, `too_many_pages` vor dem Lesen der Seiten, `too_dense` bei mehr als 100.000 Zeichen auf einer Seite, auch außerhalb ihrer Box, `needs_ocr`, `empty`) | Frist und Abbruch beenden den Prozess; Lease-Verlust beendet ihn; Ergebnis als JSON zurück; ein Absturz in der Umwandlung ist der Datei (`crashed`, endgültig, auch ein eigenes Signal wie SIGSEGV), SIGKILL `died`, ein Ende ohne Antwort und ohne Signal wird wiederholt; Linux-Teile (Prozessgruppe, OOM-Wert) nur unter POSIX | `pytest tests/conversion/test_runners.py` |
| 3.5 | Tabellen und Job | Migration `0011_conversion` (`conversion`, `document_block`, `conversion_usage`), `app/db/conversions.py`, Job `source.convert` (`app/conversion/job.py`), `app/conversion/markdown.py`, `MAX_PDF_PAGES` (800), `CONVERT_TIMEOUT_S` (900) | leere Ausgabe ist ein Fehler; Datei ohne Textebene → `needs_ocr`; Blöcke und Markdown gespeichert; `conversion_usage` je Konvertierung, eine Wiederholung bucht nicht doppelt; ein Job schreibt Ergebnis oder Fehler nur, solange die Konvertierung auf ihn wartet (Nachtrag nach dem Review: ein wiederholter oder nach Lease-Verlust weiterlaufender Job überschrieb sonst die richtige); Metriken `kka_conversions_total`, `kka_conversion_pages_total` | `pytest -m pg tests/jobs/test_source_convert.py tests/db/test_conversion*.py` |
| 3.6 | API und Oberfläche | `POST /api/v1/sources/{id}/conversions` (202, die vorhandene 200), `GET /api/v1/sources/{id}/conversion`, `GET …/conversion/blocks?page=` – am Registereintrag statt an `source_file` (Abweichung: Sichtbarkeit an `source`, nie an `source_file`; dieselbe Regel wie `GET …/file`, `app/api/source_content.py`); höchstens `CONVERSIONS_PER_MINUTE` (20) Starts je Konto und Minute; die Job-ID nur für das startende Konto und Admins (wer dieselbe Datei hochlädt, erfährt an der vorhandenen Konvertierung, dass sie schon hier war: der Preis einer Umwandlung je Datei); eine Seite nennt die Tabellen früherer Seiten, die auf ihr weiterlaufen, mit ihren Zellen dort (`continued`); `views/ConversionView.vue`, `components/ConversionPanel.vue`, `refusals.ts` | Fortschritt – auch für wen der Job nicht antwortet (das Panel fragt dann die Konvertierung) –, Fehler mit Grund, Seiten per Tastatur; axe ohne Befund | `pytest tests/api/test_conversions.py`, `vitest run` |

### Paket 3b: Docling, OCR und DOCX (3 PT, nach Download-Freigabe der Modelle)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 3b.1 | Docling-Engine | `app/conversion/docling_blocks.py` (aus `docling_conv.py`, Blöcke aus `iterate_items()`/`prov` mit BBox), Modelle im Volume (`MODELS_DIR`) | gleiche Block-IDs-Regeln wie pdfplumber; Tabellen-Fixtures mit den Tabellenmaßen der alten App | `pytest tests/conversion/test_docling_blocks.py` |
| 3b.2 | OCR und DOCX | EasyOCR (CPU, deutsch) für Seiten ohne Textebene, DOCX direkt, HTML-Quellen | `needs_ocr` entfällt für Scans; DOCX ergibt Blöcke | `pytest tests/conversion/test_ocr_docx.py` |
| 3b.3 | Auswahl | Engine je Konvertierung (`engine`), Standard nach Dateityp | Register nennt verfügbare Engines | `pytest tests/api/test_conversions.py` |

Ohne 3b nimmt M1 nur PDFs mit Textebene an; die Abnahme wählt solche.

### Paket 4: L1-Datenmodell, Profile und Lexikon laden (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 4.1 | Vokabular nachschlagen | `app/vocab/lookup.py` (`concept(conn, iri)`, `by_notation(conn, scheme, notation)`, `profile_concepts(conn, sector)`), Migration `vocab_scheme_iri` (`UNIQUE (scheme_iri, iri)`) | zurückgezogene Begriffe nicht neu wählbar; je Profil Knotentypen/Unterarten/Dokumenttypen: schul 10/13/8, elem 16/11/9, beruf 25/10/17, hs 13/6/21, eb 14/12/12 | `pytest -m pg tests/vocab/test_lookup.py` |
| 4.2 | Tabellen Geltung | Migration `l1_documents`: `work`, `document` (Fassung, Revision, Entwurfs-IRI, Rechtestatus, Eigentümer), `document_profile` (`termMappings`, `newTerms`, Tabellenschemata), `specification`, `variant`, `document_specification` | Pflichtfelder nach `cur-shapes.ttl`; Dokumenttyp nur aus dem Profil | `pytest -m pg tests/db/test_l1_documents.py` |
| 4.3 | Tabellen Knoten und Aussagen | Migration `l1_nodes`: `node` (Funktion, Knotentyp, Code, `code_assigned`, Originaltitel mit Sprache, Position, Verbindlichkeit, Tiefe der Extraktion, `origin`, `review_status`, `rule_id`, `revision`, Lauf), `statement` (Wortlaut mit Sprache, Einleitung, Art, Unterart, Verbindlichkeit, `origin`, `review_status`, `text_hash`, `revision`, Lauf), `statement_addressee` | Baum ohne Zyklen (Trigger); Aussage nur an Knoten; Unterart passt zur Art; Adressat ≥ 1 | `pytest -m pg tests/db/test_l1_nodes.py` |
| 4.4 | Tabellen Fundstelle, Lauf, Befund | Migration `l1_anchors`: `anchor` (Seiten, gedruckte Seite, Zitat, Fundart, Wert, Zeichenspanne, Zelle), `anchor_block` (Verweis auf `document_block`), `frame_part`, `extraction_run`, `validation_finding` | Block-ID-Muster; Seite oder gedruckte Seite Pflicht; Befund mit Regel, Schwere, Fokus | `pytest -m pg tests/db/test_l1_anchors.py` |
| 4.5 | Domänenregeln | `app/domain/l1.py` (ohne Framework-Importe): `text_hash`, IRI-Bildung, Code-Vergabe aus Position, Prüfung Profilwert ↔ Kernwert | Beispiele aus konzept §11; Importtest: `domain` importiert nichts aus `api`, `db`, `jobs` | `pytest tests/domain/` |
| 4.6 | Repository L1 | `app/db/documents.py`, `app/db/nodes.py` (Teilbaum in einer Transaktion, Lesen als Baum) | Teilbaum atomar; Sichtbarkeit in SQL | `pytest -m pg tests/db/test_documents.py` |
| 4.7 | Lexikon laden | Migration `lexicon` (`terminology_profile`, `lexical_cue` mit allen Feldern aus konzept §12.1; `maps_to` als IRI ohne Fremdschlüssel, weil 226 von 1.460 Zielen Klassen, Properties oder Schemata sind; beim Laden gegen den Ontologiegraphen geprüft), `app/vocab/lexicon.py`, Erweiterung von `python -m app.vocab.load` | 1.267 Hinweise aus `profile/` (112/375/34/239/55/21/395/36); Muster kompilieren mit `regex` und Zeitgrenze; zweiter Lauf unverändert; Stand an `vocab_release`; jedes Ziel existiert im Graphen | `pytest -m pg tests/vocab/test_lexicon.py` |
| 4.8 | Aktives Profil | `app/domain/lexicon.py` (`active_cues(cues, region, document_type, plan_generation)`) nach konzept §12.2 und §12.4 | spezifischer gewinnt; geprüft vor ungeprüft; Gleichstand → beide mit Regeltext; Homonym mit `alsoMapsTo` | `pytest tests/domain/test_lexicon.py` |

Nachtrag zur Umsetzung (23.10.):

- **Migrationen:**
  - Reihenfolge `lexicon`, `l1_documents` (mit `extraction_run`, auf den Knoten und Aussagen verweisen), `l1_nodes`, `l1_anchors`.
  - `vocab_scheme_iri` entfällt, weil es `UNIQUE (scheme_iri, iri)` schon seit `sources` gibt.
  - Hilfsfunktionen `has_text` und `all_match`.
- **Bereich eines Profils:** Den kennt nur das geladene `terminology_profile` (Bereich und Namensraum). Darauf bauen `profile_concepts(conn, sector_notation)`, `region_with_ancestors` und `cues_for` auf.
- **Leser:**
  - Er liest `ontologie/` und `vokabulare/` ohne Unterordner und nur `profile/` rekursiv, wo die Länderdateien liegen (`profile/laender/`); Leserformat 2.
  - Literale liest er so, wie sie geschrieben sind: rdflib normalisiert beim Parsen sonst still (aus `"2023-08-01Z"^^xsd:date` würde `"2023-08-01"`). Der Schalter `rdflib.NORMALIZE_LITERALS` gilt prozessweit; der Leser läuft heute allein im Ladebefehl. Läuft rdflib einmal nebenläufig im selben Prozess (SHACL in Paket 8), ist das neu zu bewerten.
  - Abgewiesen werden: zwei Profile eines Bereichs, ein Profil ohne Hinweis, ein Muster, das nicht auch mit Pythons `re` kompiliert, Layoutsignal, Orte, Regionen oder Dokumenttypen aus dem falschen Schema, ein Datum, das kein `xsd:date`, `gYearMonth` oder `gYear` ohne Zeitzone ist, und `scopeSector` mit einem fremden Bereich.
- **Länderhinweise:** Eine Länderdatei hängt ihre Hinweise per `cur:hasCue` an das Profil ihres Bereichs und gibt ihnen ihre Region als Geltung. Ein eigenes Profil „Bereich + Land“ (konzept §12.4) gibt es nicht; das aktive Profil eines Dokuments sind so die Hinweise eines Profils.
- **Speicher:** Beim Laden werden alle aktiven Profile zuerst zurückgezogen und die der Dateien per Upsert wiederbelebt. Nur so können zwei Profile ihre Bereiche tauschen.
- **Domäne:**
  - Aufgeteilt in `wording.py` (`text_hash`), `iris.py`, `blocks.py` (Block- und Zellmuster, aus `conversion/base.py` verschoben), `l1.py` (Entwürfe, Profilprüfung, Wertelisten) und `lexicon.py`.
  - Der Importwächter arbeitet mit einer Positivliste: Standardbibliothek und `regex`. Er löst relative Importe auf, meldet Aufrufe, die importieren (`import_module`, `__import__`), und prüft in einem frischen Interpreter, was der Import der Domäne lädt.
  - Entwürfe nennen jeden Block, Adressaten und Geltungsbereich einmal, in der Reihenfolge der ersten Nennung. Ein Seitenende ohne Anfang und ein Wortlaut mit einzelnem Surrogat werden schon beim Entwurf abgewiesen.
- **`text_hash`:**
  - NFC, Striche vereinheitlicht, Formatzeichen (Nullbreite, BOM) entfernt, `casefold`, führende Nummerierung entfernt, Leerraum zusammengezogen.
  - Worttrennung am Zeilenende: Zwischen einem Buchstaben und einem Kleinbuchstaben gehen Trennstrich (auch weich, U+2010 oder U+2011) und Umbruch weg. Vor einem Großbuchstaben oder zwischen Ziffern bleibt der Bindestrich, nur der Umbruch geht („E-Mail“, „5-6“). Ein Halbgeviert- oder Geviertstrich am Zeilenende trennt kein Wort; er bleibt, und nur der Umbruch geht („5–6“).
  - Nummerierung: ein- oder zweistellige Zahlen mit bis zu fünf Teilen („2.1.3.4“), bis zu drei hintereinander („1. a)“). „1.000“ und „100.“ bleiben, ein Buchstabe mit Punkt ist eine Abkürzung („z. B.“).
  - Mehrdeutig bleibt, was wie beides aussieht: „3. Klasse“, „1.5 Stunden“ und „i. d. R.“ verlieren ihren ersten Teil, „Ein-“ / „und“ über den Zeilenumbruch wird ein Wort. `casefold` macht „Maße“ und „Masse“ gleich.
- **IRIs:**
  - Die Basis ist ein Parameter, eine http(s)-IRI mit Schrägstrich am Ende, ohne Zugangsdaten, Query oder Fragment. `IRI_BASE`, die Vergabe beim Festschreiben sowie die IRIs von Aussagen und Fundstellen folgen mit 9.6.
  - Ein Slug liest zerlegte Umlaute wie zusammengesetzte und behält höchstens 100 Zeichen, bis zum letzten ganzen Wort.
  - Knotensegmente entstehen aus dem Code allein (das Kern-Beispiel „1“ wird zu `…/1`, eindeutig über den Pfad); ein Typkürzel davor kann mit 9.6 kommen. Vergebene Codes und Codes ohne ASCII-Buchstaben oder -Ziffer („α“, „•“) heißen `pos-<Platz>`, sich treffende Segmente zählen weiter. Knoten-IRIs gibt es nur unter der http(s)-IRI eines festgeschriebenen Dokuments.
- **Fundstelle:**
  - Sie hängt mit höchstens einem Fremdschlüssel an Knoten, Aussage, Rahmenteil oder Spezifikation desselben Dokuments; ohne Gegenstand steht sie für das Dokument selbst (wo X1 Titel und Daten las). Ein Verweis auf `entity` würde verwaisen, weil Entity-Zeilen beim Löschen stehen bleiben.
  - Ihre Blöcke sind über einen Fremdschlüssel Zeilen von `document_block` der Konvertierung des Dokuments. Eine Fundstelle mit `cv:match_notFound` nennt ihre Seite und keinen Block (8.1, 9.4).
- **Prüfungen in der Datenbank:**
  - Der Baum hat keinen Zyklus. Prüft ein Constraint-Trigger nach jeder Anweisung, mit Sperre je Dokument.
  - Wächter, die eine Zeile gegen andere prüfen, die eine fremde Transaktion inzwischen ändern kann, gelten nur unter `read committed`; jede andere Stufe weisen sie ab (`invalid_transaction_state`). Das betrifft: einen Knoten verschieben, eine Fundstelle oder einen Adressaten von einer bleibenden Aussage nehmen, eine Spezifikation oder Variante für sich wegnehmen. Nur `read committed` sieht nach dem Warten neu hin. `repeatable read` behält seinen ersten Blick, und `serializable` findet den Konflikt nur, wenn alle Seiten `serializable` laufen. Wer eine Fundstelle oder einen Adressaten wegnimmt, nimmt beim Commit die Baumsperre des Dokuments (`lock_node_tree`, dieselbe wie `lock_tree`). So warten zwei solche Transaktionen, die jede einen übrig ließen, aufeinander. Die Zeile der Aussage zu sperren, wäre falsch: Das Löschen eines Knotens sperrt dessen Aussagen vor ihren Fundstellen, und daraus entstünde ein Deadlock.
  - Regel für X6 (Paket 8) und den Editor (Paket 9): Wer Fundstellen oder Adressaten wegnimmt oder Aussagen bzw. Knoten bearbeitet oder löscht, nimmt zuerst `lock_tree`. Sonst kann die Baumsperre beim Commit auf eine Gegenseite treffen, die sie schon hält und auf eine Zeile dieser Transaktion wartet.
  - Der Knotentyp liegt unter der Funktion und die Unterart unter der Art. Geprüft wird beim Schreiben einer Zeile; was ein späteres Neuladen der Vokabulare an `skos:broader` ändert, findet X5.
  - Beim Commit hat jede Aussage mindestens einen Adressaten und eine Fundstelle (wie `StatementShape`).
  - `applies_to` nennt Spezifikationen und Varianten des eigenen Dokuments, jede einmal. Sie bleiben, solange ein Knoten sie nennt (geprüft beim Commit). Gesperrt sind sie wie bei einem Fremdschlüssel, mit ihrem Dokument gehen sie.
  - Layoutmerkmale stammen aus `cv:LayoutMarkers`, der Dokumenttyp ist ein `cur:DocumentType`. Ein Rahmenteil aus einer Regel nennt die Regel.
  - Ein Seitenende steht nur neben seinem Seitenanfang.
  - Ein Wächtertest verlangt für jeden kaskadierenden Fremdschlüssel einen Index, der mit allen seinen Spalten beginnt oder mit einer, die nicht `document_id` ist.
  - Die Profilzugehörigkeit und zurückgezogene Kernwerte prüft das Repository.
- **Einzelheiten:**
  - `extraction_run` hat noch keinen Ausgang; der kommt mit 6.6. Knoten, Aussagen und Rahmenteile nennen ihren Lauf (`run_id`, über `write_subtree(..., run_id=)`); wird ein Lauf gelöscht, bleiben sie ohne ihn, während die Befunde eines Laufs mit ihm gehen.
  - `newTerms` stehen als JSON in `document_profile`; Paket 10 löst sie bei Bedarf heraus.
  - Eine Spezifikation gehört einem Dokument und geht mit ihm; ihr Schlüssel ist je Dokument eindeutig. `document_specification` entfällt: Eine Spezifikation über mehrere Dokumente kommt mit den Platzierungen in M2/M3.
  - Das Dokument trägt seinen Herausgeber als Text (`issuer`) und `draft_iri = urn:uuid:<id>`. Eine IRI nennt jede Revision einmal (`UNIQUE (iri, revision)`), und `revision` zählt die Änderungen einer Zeile (9.3).
  - Für später notiert: Den `focus_id` eines Befunds setzt X5 (8). Die Liste `educationSectors` sowie `targetsContent` und `checkedAbsent` kommen mit Paket 6 und 7.
- **Sichtbarkeit:**
  - Dokument und Baum lesen Eigentümer, Redaktion und Admin (`DOCUMENT_VISIBLE`, in jeder Abfrage). Regeln für Dritte folgen mit dem Editor (9).
  - `create_document(connection, maker, *, third_party_content, …)` findet den Eintrag in SQL nur, wenn sein Inhalt dem Ersteller zu lesen ist: der eigene, für die Redaktion jeder, einer ohne Konto, wo `THIRD_PARTY_MARKDOWN` ihn Konten öffnet. Der Eintrag ist gesperrt, solange seine Rechte übernommen werden.
  - Regionen müssen im aktiven Regionen-Vokabular stehen; jede wird einmal gespeichert.
  - `read_tree` liest in einem Snapshot (eigene Transaktion `REPEATABLE READ READ ONLY`, wo der Aufrufer keine hat; in dessen Transaktion so, wie diese liest). Den eigenen Snapshot und die Sichtbarkeit in jeder Abfrage prüft kein Test: Die erste Abfrage entscheidet über die Sichtbarkeit, beides ist Schutz in der Tiefe.
  - Das Typisieren sperrt das Dokument `FOR NO KEY UPDATE`, wartet also nicht auf Knoten, die gerade hineingeschrieben werden.
  - `lock_tree` ist die Sperre, die alle Schreibzugriffe auf einen Baum teilen; auch die Verschiebungen des Editors nehmen sie.
- **Aktives Profil:**
  - `active_cues(cues, regions, document_type, plan_generation, *, wider_regions)`: `regions` sind die eigenen Regionen des Dokuments, `wider_regions` die, in denen sie liegen. Der Aufrufer trennt, was `region_with_ancestors` liefert. Ein Hinweis gilt, wenn seine Regionen eine der beiden Mengen schneiden.
  - Ist Dokumenttyp oder Plangeneration unbekannt (None), gelten Hinweise dieser Geltung, bekommen aber keinen Rang. Eine bekannte, nicht passende Geltung schließt aus.
  - Hinweise konkurrieren je Art und Wort, Muster oder Layout. Rang: eigene Region vor umfassender vor keiner (Land vor Deutschland vor Bereich), dann die Zahl der bekannten passenden Geltungen, dann geprüft, dann Stärke.
  - Bei Gleichstand mit anderem Ziel bleiben beide mit `tie`. Negative Hinweise und Homonyme konkurrieren nicht und gelten immer.
  - Ein `Cue` trägt Orte, Daten, die übrigen Geltungen und die Beispiele für den Prompt. Das Dokumentprofil legt Paket 6 beim Bau des Prompts darüber.
  - Am echten Lexikon (5 Profile × 16 Länder) gelten 9.811 Hinweise. 41 davon weichen in der Konkurrenz, es bleiben 9.770 statt 9.272, davon 64 mit `tie`:
    - 17 Hinweise für ganz Deutschland weichen dem Landeshinweis auf demselben Wort.
    - 8-mal weicht `schul:cue-kb-kompetenzbereich` (0,8, Deutschland und acht Länder) in den übrigen Ländern einem Landeshinweis mit demselben Ziel (0,6).
    - 16-mal ist es die bekannte HCO-Kollision „Applicability“.
  - Weicht ein Hinweis einem spezifischeren mit demselben Ziel, geht seine Stärke mit ihm. Ob der Prompt dafür eine Ausnahme braucht, etwa für die Markierung „starkes Signal“ ab 0,8, entscheidet Paket 6.
- **Profilangaben:** Ein Profil trägt in den Tabellen nur Bereich, Namensraum und `rdfs:label`. Was es sonst sagt, etwa ein Steckbrief, den eine Länderdatei an das Bereichsprofil hängt (konzept §12.4), wird nicht gespeichert; das folgt, sobald es gebraucht wird.
- **Leser, Unterordner:** Unter `profile/` liest er jeden Unterordner, nicht nur `laender/`. Eine alte Kopie dort würde mit denselben IRIs zusammenfallen; neue Ordner neben `laender/` sollen aber ohne Codeänderung gelesen werden. Alte Kopien gehören deshalb nicht unter `profile/`.
- **Paket 10:** `pruefe.py` liest keine Unterordner und sieht `profile/laender/` deshalb nie. Für 10.1 („pruefe.py OK“) muss es `profile/` rekursiv lesen.
- **Muster:**
  - Sie laufen mit `regex` und einer Zeitgrenze von 50 ms (`PatternTimeout`).
  - Ein Datenwächter prüft die 46 Muster mit Beispielen: Sie treffen ihre positiven Beispiele und keines der negativen.
- **Abhängigkeit:** `regex` ist jetzt direkt deklariert, in der Version des Locks. Der Export ändert sich dadurch im via-Vermerk, deshalb lädt der Image-Neubau die Wheels neu.

### Paket 5: Modellschicht und Abrechnung (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 5.1 | Aufrufschicht | `app/llm/calls.py` (aus `llm.py`, geteilt: Agent mit `StructuredDict`, `CachePoint` hinter dem Präfix, `max_output_tokens`, SDK-Wiederholungen aus, eigene Warteschleife bei 429/5xx mit Retry-After, Trace-Header über `outgoing_headers`), `app/llm/attempts.py` (Zählung gesendeter Anfragen) | Mock-Transport: Haltepunkt hinter dem Präfix; Obergrenze im Anfragekörper (Responses und Chat); Ausgabe gegen das Schema; Nutzung auch bei Fehlschlag lesbar; Schlüssel in keiner Logzeile | `pytest tests/llm/` |
| 5.2 | Token zählen | `app/llm/budget.py` (Kopie, tiktoken `o200k_base` aus `TIKTOKEN_CACHE_DIR`, nie aus dem Netz) | ohne Kodierung im Cache klarer Startfehler statt Download; Zählung stimmt mit der alten App | `pytest tests/llm/test_budget.py` (gesperrtes Netz) |
| 5.3 | Rohantworten | `app/llm/raw.py` (`runs/<run>/<stufe>/<n>.json`) | Ablage vor der Auswertung; Wiederholung schreibt eine neue Nummer | `pytest tests/llm/test_raw.py` |
| 5.4 | Tabellen Abrechnung | Migration `usage` (`llm_usage`, `quota`, `usage_reservation`) | Zahlen nicht negativ; Reservierung hängt an Job und Konto; `estimated` gekennzeichnet | `pytest -m pg tests/db/test_usage_schema.py` |
| 5.5 | Reservieren und Buchen | `app/usage/ledger.py` (`reserve`, `book`, `book_abandoned`) | zwei Worker, 40 Jobs, Mock verbraucht genau seine Reservierung, Grenze für 12 Aufrufe → genau 12; Mock verbraucht die Hälfte → entsprechend mehr; abgebrochener Job: Reservierung wird als `estimated` gebucht; Buchung ersetzt Reservierung in einer Transaktion | `pytest -m pg tests/usage/test_ledger.py` (Stresslauf) |
| 5.6 | Zulassung | `app/usage/admission.py` (Restbudget, `MAX_JOBS_IN_FLIGHT`, Rate-Limit Starts) | 403 ohne Budget; 429 mit Retry-After über 20 offenen Modelljobs oder über dem Rate-Limit; Admin unbegrenzt nur mit `NULL`-Grenze | `pytest -m pg tests/usage/test_admission.py` |
| 5.7 | API und Metriken | `PUT /api/v1/accounts/{id}/quota` (Admin), `GET /api/v1/me/usage`; Metriken Aufrufe, Token, Fehler, Reservierungen; `LLM_MAX_OUTPUT_TOKENS`, `MAX_JOBS_IN_FLIGHT` in Settings und `konfiguration.md` | `test_auth_surface`, `test_openapi`; Audit-Zeile | `pytest tests/api/test_usage_api.py` |

Nachtrag zur Umsetzung (24.10.):

- **Token zählen (5.2):**
  - Die Kodierung `o200k_base.tiktoken` liegt im Repo, in `backend/app/llm/` (Nutzerentscheid 23.10.), statt aus `TIKTOKEN_CACHE_DIR` zu kommen. Geladen wird sie per Pfad und geprüftem SHA-256, nie aus dem Netz; dazu ein Lizenzhinweis und `.gitattributes` `-text -diff`.
  - API und Worker prüfen beim Start Reasoning-Aufwand, Kontextfenster und Kodierung (`check_model_layer`). Sie lehnen auch ein `LLM_MAX_OUTPUT_TOKENS` ab, das neben `RESERVE_TOKENS` (17.000) nicht ins Fenster passt. `RESERVE_TOKENS` rechnet noch mit der gemessenen Antwort der alten App (rund 5.900 Token und eine Wiederholung). Ob es mit dem Deckel wachsen muss, entscheidet die Raumrechnung des Präfixes (Paket 6/7).
  - `tiktoken` ist direkt deklariert. Der Export ändert sich dadurch nur im via-Vermerk.
- **Aufruf (5.1):**
  - `StructuredDict` prüft die Antwort nicht gegen das Schema; eine Probe ließ `{"n": "x"}` gegen `integer` durch. Deshalb gibt es einen eigenen Prüfer `app/llm/schema.py` für genau die Teilmenge der sechs Schemas, der als `output_validator` per `ModelRetry` nachfragt. Zwei Wächtertests verlangen, dass er jedes Schlüsselwort der Schemas kennt und jede Form, die sie ihm geben: Typen aus `KNOWN_TYPES`, `additionalProperties` nur `false`, `items` als ein Schema. `integer` bleibt streng, `3.0` wird nachgefragt. `jsonschema` wäre ein Download mit fünf Paketen gewesen.
  - pydantic-ai 2.42 kennt `output_retries` nicht; es heißt `retries=2`.
  - Reserviert wird je Modellanfrage, nicht je Aufruf. `ask` geht den Lauf Knoten für Knoten durch: Vor jedem `ModelRequestNode` reserviert er, am `CallToolsNode` bucht er die gemeldete Nutzung und legt danach die Antwort ab, noch bevor der nächste Knoten sie prüft. So ist jede Ausgabe-Wiederholung eine eigene, neu reservierte Anfrage. Scheitert die Buchung oder wird sie abgebrochen, bucht er dieselbe Nutzung noch einmal, nicht die Schätzung; der Meter nimmt eine Reservierung nur einmal.
  - Den reservierten Deckel liest `build_agent` aus den Einstellungen des Modells (`max_tokens`), damit Reservierung und Anfrage nicht auseinanderlaufen.
  - Ein eigener `AsyncOpenAI` mit `max_retries=0` und einem Client, der jede Anfrage zählt (`Attempts`) und die Trace-Header setzt. `max_tokens` = `LLM_MAX_OUTPUT_TOKENS` wird zu `max_output_tokens` bzw. `max_completion_tokens`.
  - Gebucht wird so:
    - Eine abgewiesene Anfrage (HTTP-Fehler) kostet 0 Token und zählt als eine Anfrage.
    - Eine gesendete ohne Antwort (Zeitüberschreitung, Abriss, Abbruch im Flug) kostet ihre Reservierung, gekennzeichnet `estimated`, unter `asyncio.shield` gebucht.
    - Ebenso eine Antwort ohne Nutzungsangabe und eine, die kein Modell lesen konnte (etwa eine 200-Seite eines Proxys). Die zweite lässt den Aufruf scheitern; bis zum Review galt sie als „nie in Form“, und ihre Reservierung blieb stehen.
    - Eine nie gesendete kostet nichts. Der Client zählt eine Anfrage, bevor er verbindet; `ConnectError`, `ConnectTimeout` und `PoolTimeout` in der Ausnahmekette gelten deshalb als nie gesendet (`never_sent`).
  - Gewartet wird wie in der alten App, aber ohne Wiederholungen des SDK. Ein nicht erreichter Anbieter wird wie ein 5xx noch zweimal gefragt, denn die SDK-Wiederholungen, die das früher taten, sind aus.
  - Hat eine Stufe keine Ausgabe, sagt `Answer.failure` warum (nie in Form, Antwort am Deckel abgeschnitten, Inhaltsfilter); eine Warnzeile nennt es ohne den Körper.
- **Rohantworten (5.3):**
  - Abgelegt wird je `ModelResponse` die JSON-Form von pydantic-ai, mit Nutzung, Modell und Zeit, bevor die Antwort geprüft wird.
  - Weil der Speicher nicht auflisten kann, springt die Nummer per `exists` hinter Vorhandenes. Das hält für einen Ablegenden je Lauf und Stufe; zwei nebeneinander könnten dieselbe Nummer nehmen.
  - Gefunden dabei: Unter Windows behält `Path.resolve()` in einem Rennen das Präfix `\\?\`, und `FileSystemStorage` wies den Schlüssel dann ab. Behoben mit `without_long_prefix`, für Schlüssel wie für eine Wurzel, die schon in der Langform steht.
- **Tabellen (5.4):**
  - `quota`: Ohne Zeile gilt die Grenze 0, `NULL` heißt unbegrenzt, für jede Rolle.
  - `llm_usage` hat keinen Fremdschlüssel auf Job und Lauf, damit sie überdauert, wie das Audit-Log. Das Konto bleibt, solange es Verbrauch hat. `estimated` hat keinen Standard: Der Schreiber sagt es.
  - `usage_reservation` hält Job und Konto, bis sie gebucht ist (Fremdschlüssel ohne `ON DELETE`, also NO ACTION, der Standard von PostgreSQL). Sie trägt Zweck, Modell und Lauf für die Buchung.
  - Ein Index auf jedem `account_id` und auf `job_id`.
- **Ledger (5.5):**
  - Rest = Grenze − Σ Verbrauch − Σ Reservierungen, summiert unter `SELECT … FROM quota … FOR UPDATE` und nur unter `read committed` (`read_committed_alone`). Es gibt keinen Zähler, der von den Zeilen abweichen kann. `simplify:` Die Summen lesen alle Zeilen eines Kontos, das kann später eine laufende Summe übernehmen.
  - `book` ersetzt die Reservierung in einer Anweisung und genau einmal. Eine späte Buchung nach `book_abandoned` bucht nichts mehr: Die Schätzung steht.
  - `reserve` und `book` laufen je in einer eigenen Transaktion. Auf einer Verbindung, die schon in einer steckt, lehnen sie ab: Die Zeilensperre der Quote hielte sonst bis zum Commit des Aufrufers jede andere Anfrage des Kontos an, und ein Rollback nach dem Senden nähme die Reservierung mit.
  - `book_abandoned` ist gebaut und getestet. Aufgerufen wird es erst mit den Modelljobs (Paket 6).
  - `remaining_tokens` entfällt; dafür gibt es `usage_of(...).tokens_left`.
  - Abweichung beim Stresslauf: 8 statt 2 Worker. Mit zweien kam das Rennen an der Grenze zu selten zustande, und der Mutant „ohne `FOR UPDATE`“ überlebte 5 von 5 Läufen; mit acht stirbt er 8 von 8. Die Schranke ist für W Worker verallgemeinert: Unverbraucht bleibt weniger als ein Aufruf plus (W − 1) × (Reservierung − Kosten). Verbraucht jeder Aufruf genau seine Reservierung, sind es genau 12. Dazu kommt ein Ledger-Test mit 20 gleichzeitigen Verbindungen, Mutant 10 von 10.
- **Zulassung (5.6):**
  - `admit_model_job` läuft in der Transaktion, die den Job einreiht, unter einer Sperre je Konto und nur unter `read committed`. Ohne offene Transaktion lehnt es ab, weil die Sperre sonst vor dem Einreihen ginge; unter `repeatable read` sähe es die Jobs der anderen nicht.
  - Die Reihenfolge ist Budget, offene Modelljobs, Rate. Das Budget gilt als verbraucht, wenn der Verbrauch die Grenze erreicht. Was laufende Aufrufe reserviert halten, zählt nicht mit, denn ihre Buchungen geben das meiste zurück; die erste Reservierung des Jobs entscheidet. Die Rate zählt zuletzt, damit ein abgewiesener Start keinen Platz kostet.
  - Fachliche Ausnahmen; die Antworten (403 `no_budget`, 429 `too_many_jobs`, 429 `too_many_starts`) baut `admit_model_start` in `app/api/limits.py`.
  - `MODEL_JOB_KINDS` ist leer, bis X1 kommt. Ein Start mit kleinem Rest scheitert erst an der ersten Reservierung.
- **API, Metriken, Image (5.7):**
  - `PUT …/quota` verlangt beide Grenzen ausdrücklich (JSON-Zahl bis 10^15 oder `null`, nicht `"5000"` oder `true`), damit keine aus Versehen fehlt. Die Endpunkte stehen unter dem Tag `usage`.
  - Metriken: `kka_llm_requests_total{outcome}` (answered, refused, unanswered, unsent), `kka_llm_tokens_total{kind}` (input, cached_input, output, estimated) und `kka_usage_reservations_total{outcome}` (held, refused, booked, late, abandoned).
  - Das Image kopiert `ontology/schemas` (`SCHEMA_DIR`).
  - Die Seitengrenze ist nur eine Spalte. Durchgesetzt wird sie mit der ersten abrechenbaren Engine (3b).
- **Festlegungen für Paket 6, aus dem Review:**
  - `book_abandoned(job_id)` läuft am Ende jedes Versuchs eines Modelljobs, in der Transaktion, die ihn unter seiner Lease beendet: `complete`, `mark_cancelled`, `fail`, `release`. Dann nimmt es alles, was ein Abbruch zwischen Reservierung und Buchung liegen ließ, und nie eine Reservierung des nächsten Versuchs.
  - `requeue_expired` beendet abgelaufene Leases ohne Lease und gibt heute nur Statuswerte zurück. Für Modelljobs gibt es dort `RETURNING id, status` und in derselben Transaktion ein mengenweises `book_abandoned` (`DELETE … WHERE job_id = ANY (%s)`). Ein wartender Job, den `request_cancel` beendet, hält keine Reservierung eines laufenden Versuchs. Die seines beendeten Vorversuchs hat dessen Ende gebucht. Was ein Vorversuch nach dem Verlust seiner Lease noch reserviert, bucht er selbst, sobald die Antwort kommt. Stirbt sein Prozess dazwischen und endet der Job danach ohne weiteren Versuch, bliebe die Reservierung offen; deshalb bucht der Sweep auch die offenen Reservierungen beendeter Jobs (`done`, `failed`, `cancelled`) mengenweise wie `book_abandoned`.
  - Jede Stufe jedes Versuchs bekommt ihren eigenen Lauf (`extraction_run`, je Stufe wie 6.6). Die Rohantworten zweier Versuche, die sich nach einem Lease-Verlust kurz überschneiden, liegen so unter verschiedenen Schlüsseln.
  - `Answer.failure` ist heute der Text der Meldung von pydantic-ai. Unterscheidet die Stufe danach, etwa eine am Deckel abgeschnittene Antwort (ein Signal für `LLM_MAX_OUTPUT_TOKENS`) von einer, die nie in Form kam, liefert `calls.py` dafür eine stabile Art mit: den Ausnahmetyp und den `finish_reason` der letzten Antwort.

### Paket 6: X1 Dokumentprofil, Gerüst und X2 Segmente (6 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 6.1 | Präfix | `app/pipeline/prefix.py` (Blocktext mit IDs, Dokumentprofil, Auswahllisten; Kürzung nach §13.1) | Präfix byte-gleich über alle X4-/X6-Aufrufe eines Dokuments; Kürzung behält Titelei, Verzeichnis, Rahmenteile, Abschnitt + Nachbarn | `pytest tests/pipeline/test_prefix.py` |
| 6.2 | X1 Dokumentprofil | `app/pipeline/x1_profile.py`, Prompt `app/pipeline/prompts/x1.py` | FunctionModel liefert `x1-dokumentprofil`; Dokument, Spezifikationen, Varianten, `document_profile` gespeichert; Werkvorschlag ohne Setzen; Profilwert außerhalb → `validation_finding` statt Absturz | `pytest -m pg tests/pipeline/test_x1_profile.py` |
| 6.3 | Gerüst deterministisch | `app/pipeline/skeleton.py` (Überschriften aus Schrift/Layout/Verzeichnis; Muster mit Stärke ≥ 0,9 typisieren ohne Modell, über `asyncio.to_thread`) | „Lernfeld 5: …" → Lernfeld; „Inhaltsfeld 3" in NW → Inhaltsfeld; Negativbeispiele der Hinweise treffen nicht | `pytest tests/pipeline/test_skeleton.py` |
| 6.4 | X1 Gliederung | `app/pipeline/x1_outline.py` (nur unklare Überschriften an das Modell, `x1-gliederung`) | nur unklare gehen raus; Funktion = Kernwert des Knotentyps | `pytest -m pg tests/pipeline/test_x1_outline.py` |
| 6.5 | X2 Segmente | `app/pipeline/x2_segments.py` (Einheiten mit Blockbereich; über ~15 Seiten an Unterknoten teilen; Extraktionstiefe skip/typed/full) | Einheiten decken alle Inhaltsblöcke genau einmal; `skip` erzeugt keinen Auftrag, `typed` keinen Aussagen-Auftrag | `pytest tests/pipeline/test_x2_segments.py` |
| 6.6 | Lauf-Rahmen | `app/pipeline/run.py` (Job `extract.run`, Stufen nacheinander, `extraction_run` je Stufe, Fortschrittscodes, Wiederaufnahme ab der letzten fertigen Stufe), Wächter Fortschrittscodes ↔ Frontend | Abbruch zwischen Stufen; keine fertige Stufe doppelt; Budget erschöpft → `budget_exhausted`, Teilergebnis bleibt | `pytest -m pg tests/pipeline/test_run.py` |

**Nachtrag zur Umsetzung (24.10.)**

- **Stufen und Läufe.** `extract.run` kennt X1 und X2. Je Stufe und Versuch ein Lauf; Migration 0017
  ergänzt `attempt`, `outcome` (`done`, `failed`, `budget_exhausted`; leer, solange er läuft oder
  abgebrochen wurde) und `result`. Eine Stufe schreibt ihr ganzes Ergebnis mit dem Ende ihres Laufs in
  einer Transaktion unter `hold_lease` (Zeilensperre unter der eigenen, nicht abgelaufenen Lease).
  Scheitert X1 nach dem Profilaufruf, ist dessen Antwort verloren und wird neu gefragt (billiger als
  ein zweiter Schreibweg). Jede andere Ausnahme beendet den eigenen Lauf `failed` mit ihrem Typ als
  `failure` und geht weiter (Lease-Verlust, Datenbankfehler).
- **Wiederaufnahme dokumentweit (Review).** Fertig ist eine Stufe mit einem fertigen Lauf am
  Dokument, gleich welcher Job (`done_stages`): ein neuer Job nach `budget_exhausted` oder nach
  verbrauchten Versuchen setzt an der letzten fertigen Stufe fort. Wo X1 steht, sagt `x1_state`
  dreiwertig: `open`, `done` (ein fertiger X1-Lauf, gleich welcher Job) oder `tree` (Knoten oder
  Spezifikationen ohne fertigen X1-Lauf, etwa von Hand angelegt). Am Anfang der Stufe: `done`
  überspringt X1 (ein anderer Job schrieb es, seit dieser nachsah), `tree` endet mit
  `document_has_tree`. Die Schreibtransaktion sperrt nach `hold_lease` die Dokumentzeile und fragt
  erneut (`lock_for_x1`): `done` beendet den eigenen Lauf `failed` („written by another run“),
  nichts wird geschrieben, X2 folgt; `tree` beendet ihn `failed` mit `document_has_tree`.
  `attempt` ist `job.attempts`; nach einer Freigabe (`release` zählt den Versuch zurück) kann eine
  Nummer zweimal vorkommen, Läufe ordnet `started_at`. `x1_state` liest beides in einer Anweisung
  (ein Snapshot): X1 schreibt Baum und Laufende zugleich, eine Abfrage in zwei Schritten sah sonst
  den Baum ohne den Lauf (Abschlussprüfung).
- **Arbeitspakete im Lauf-Ergebnis.** X2 legt seine Pakete als `result.packages` seines Laufs ab
  (Schlüssel `E0`, `E1` … in Dokumentreihenfolge, Knoten, erster/letzter Block, Seiten, Titelpfad,
  Tiefe, Auftrag) statt in eigenen Tabellen; Paket 7 liest den letzten fertigen X2-Lauf.
- **Gerüst (6.3).** Testbeispiel korrigiert: „Inhaltsfeld 3: …“ (der Hinweis verlangt `[:.]`) →
  `schul:Inhaltsbereich`. Nummerierung allein macht keine Überschrift (nur mit fett oder größer);
  Muster zählen nur, wenn sie einen Knotentyp des Profils nennen; eine Tabelle ist Überschrift, wo
  ein solches Muster ihre erste Zelle trifft (KMK-RLP setzen Lernfelder als Tabelle), sonst ist
  Tabelleninhalt nie eine. Vor dem Verzeichnis nichts (Titelei), Layout allein auf Seite 1 eines
  mehrseitigen Dokuments nichts (Titelblatt). Ein starker Hinweis typisiert, wo alle starken, die
  treffen, einen Knotentyp nennen und kein Homonym trifft. `level` ist die Tiefe im Baum.
  Nach dem Review: Ein Verzeichnis ist ein Lauf, dessen Seiten nie fallen, höchstens die Seitenzahl
  des Dokuments erreichen und nicht alle gleich sind (eine Lernfeldübersicht mit Stunden, ein
  Fußnotenblock mit Jahren sind keins). Wo die Titelei endet, entscheidet allein der erste Lauf von
  mindestens drei Einträgen des Dokuments, was immer er ist, und kein Lauf danach (Abbildungen,
  das Verzeichnis eines Anhangs): dort, wo seine Seiten gelesen werden und er einen Titel
  („Inhalt…“) hat oder auf den ersten fünf Seiten steht (ein Verzeichnis hinter langem Vorwort
  trägt seinen Titel), oder wo er mit Titel vorn steht, auch wenn seine Seiten abgelehnt werden;
  sonst nirgends. Im Zweifel wird die Titelei zu Überschriften; Überschriften werden Titelei nur
  auf den ersten fünf Seiten (ein erster Lauf dort, der kein Verzeichnis ist) und im Restfall A1
  unten (drei Prüfrunden hatten die Entscheidung je einem späteren Lauf überlassen, jeder öffnete
  einen Totalverlust).
  Verzeichnismuster sind Hinweise mit `mapsTo cv:occ_toc`; `occursIn cv:occ_toc` tragen Wörter
  von Überschriften, die auch im Verzeichnis stehen. Verzeichniszeilen werden mit einfachem
  Leerraum gelesen (sonst quadratisch). Läuft das Muster eines Homonyms oder eines starken
  Hinweises zu lange, typisiert keine Regel. Das zweite Gerüst liest nach dem Dokumenttyp der
  Redaktion, wo sie einen gesetzt hat, sonst nach dem aus X1.
- **X1 Profil (6.2).** Auszug: Anfang bis 8 000 Zeichen, Verzeichnis, Geltungsstellen ±1 Block bis
  4 000 Zeichen. Befunde statt Absturz (`x1.unknown_key`, `unknown_value`, `unknown_block`,
  `duplicate_key`, `blank_value`, `value_cut`); Regionen und Bereich bleiben die der Anlage
  (`x1.regions_differ`, `x1.other_sectors`, info), ein vorher gesetzter Dokumenttyp bleibt
  (`x1.document_type_differs`), ein Werk wird nur vorgeschlagen (`x1.work_suggestion`). Belastet
  wird der Eigentümer des Dokuments; wer starten darf, entscheidet 7.5. Daten: Ausgabe und
  Geltung stehen als Datum so genau, wie der Wortlaut reicht („1. August 2019“, „1.8.2019“,
  „Juni 2019“, „2019-08“; deutsche Monatsnamen samt „Jänner“, auch in Großbuchstaben; ein
  Schuljahr „2019-20“ oder „2011-12“ ergibt das Jahr, ein Monatsname, der nur unter re.I trifft
  („Auguſt“), ebenso), der
  Wortlaut selbst in `result.said` des X1-Laufs (`issuedText`, `validFromText`, Regionen,
  Bereiche), nicht in der Fundstelle. Der Profilauftrag nennt das heutige Datum (für `lifecycle`);
  beide Prompts sagen, dass der Dokumenttext Inhalt ist, nie Anweisung. Antworten werden an der
  Lesegrenze speicherbar gemacht (NUL und einzelne Surrogate → U+FFFD).
- **X1 Gliederung (6.4).** Die unklaren Überschriften gehen in Teilen zu 50 an das Modell (300
  Überschriften × ~80 Antworttoken sprengten sonst `LLM_MAX_OUTPUT_TOKENS`). Fehlt eine in der
  Antwort: Funktion `grouping` mit Kindern, sonst `unit`, Herkunft `rule` mit Regel
  `x1.outline_unanswered` und Befund. Prüfstand aller Pipeline-Knoten `proposed`.
- **X2 (6.5).** Eigener Text je Knoten von seiner Überschrift bis zur nächsten; `skip` erbt nach
  unten (ein übersprungener Anhang samt Teilen); eine Überschrift ohne eigenen Text bleibt ein Paket
  mit Auftrag `none` (auch unter `full`), damit jeder Inhaltsblock genau einmal abgedeckt ist; ein
  Dokument ohne Überschriften ist ein Paket `full`. Teilung über 15 Seiten an Seitengrenzen. Die
  Tiefe am Knoten (`extraction_depth_iri`, etwa von der Redaktion gesetzt) gilt vor der seines Typs.
- **Buchung am Jobende (Festlegung aus Paket 5).** `book_abandoned` läuft an jedem Jobende in der
  beendenden Transaktion, für jeden Job, nicht nur Modelljobs (ein `DELETE` ohne Treffer). Der Sweep
  bucht mengenweise die Reservierungen aller Jobs, die gerade nicht laufen (`book_left_behind`);
  `requeue_expired` braucht dafür kein `RETURNING id`. Gezählt (`kka_usage_reservations_total`,
  `abandoned`) wird erst nach dem Commit, beim Aufrufer.
- **Fortschrittscodes flach:** `extract_profile`, `extract_outline {headings}`,
  `extract_segments {units}` (Punkte läse das eigene `translate` in `de.ts` als Verschachtelung).
  Das Modell entsteht je Prozess beim ersten Bedarf (`LazyModel`), der Worker startet ohne
  Schlüssel.
- **Dateien:** Prompts `prompts/x1_profile.py` und `prompts/x1_outline.py` (statt `prompts/x1.py`),
  Fragen `x1_question.py`, Auszug `x1_excerpt.py`, Stufe `x1_stage.py`, Verzeichnis `toc.py`,
  Fortschritt `progress.py`; die Entwürfe für Profil, Spezifikation und Variante liegen in
  `app/domain/l1.py` (die Datenbankschicht importiert nie die Pipeline). Tests unter
  `tests/pipeline/` (u. a. `test_x1_profile_read.py`, `test_x1_question.py`, `test_x1_outline*.py`,
  `test_x2_*.py`, `test_run.py`) und `tests/db/test_profile.py`.
- **Grenzen und Messpunkte (Paket 11):** Überschriftenerkennung, die Schwelle 0,9 und die 15 Seiten
  sind nicht an echten Dokumenten gemessen. Das Schema `x1-gliederung` kann eine Schein-Überschrift
  nicht verwerfen; sie wird ein Knoten für die Redaktion. Verzeichnisse als Tabelle und Einrückung
  von Verzeichniseinträgen werden nicht gelesen. Ein Muster über seiner Zeitgrenze trifft nichts
  und wird als Befund genannt. Nummerntiefe und Größenrang teilen eine Skala: nummerierte Kapitel
  unter einem größeren unnummerierten Teil („Teil C“ 20 pt, „1 …“ 16 pt) werden dessen Geschwister
  (Review A3) – an echten Dokumenten messen, bevor die Heuristik umgebaut wird. Die Seitenprüfung
  des Verzeichnisses hat keine Toleranz: Amtsblatt-Seiten (245 ff.), Web-PDFs ohne Leerseiten, je
  Teil ab 1 gezählte Seiten, eine falsch gelesene Ziffer lehnen ein echtes Verzeichnis ab; es
  kostet dann seine Einträge (Ebenen, nur dort genannte Überschriften) und, steht es hinten oder
  ohne Titel, Schein-Überschriften aus der Titelei, nicht die Überschriften (Nachprüfung R1-2).
  Messen; ein besserer Maßstab wären die gedruckten Seitenzahlen der Umwandlung statt der
  Seitenzahl der PDF. Restfälle der Titelei-Regel, bewusst offen: (A1) ein gelesenes Verzeichnis
  mit Titel weit hinten als erster Lauf von mindestens drei Einträgen – das eines Anhangs, eines
  Kapitels oder eines Teils, wo das vordere nicht gelesen wird (als Tabelle, ohne Leitpunkte und
  Nummer, in Läufe unter drei Einträgen zerteilt) – beendet die Titelei dort, was davor steht, wird
  keine Überschrift: der einzige Verlust über die ersten fünf Seiten hinaus; auf ihnen beendet sie
  auch ein erster Lauf, der kein Verzeichnis ist (Fußnoten mit Seitenverweisen, eine „Gliederung“
  mit Stunden), und die Überschriften davor fallen weg; geht dem echten Verzeichnis ein anderer
  Lauf voraus – abgelehnt ohne Titel vorn (eine Stundenübersicht als Text, Fußnoten mit Jahren),
  gelesen ohne Titel hinten (Fußnoten mit Seitenverweisen im Vorwort) oder abgelehnt hinten –,
  endet sie nirgends, die Titelei liefert dann Schein-Überschriften. Zwei ältere Grenzen: jeder
  gelesene Lauf fällt aus den Überschriften, auch einer, der keins ist (drei Überschriften
  hintereinander mit Zahlen am Ende, „Inhalt“ als echte Überschrift darüber); ein Titel wird nur
  als ganze Zeile erkannt („Inhaltsverzeichnis:“ nicht). Alles an echten Dokumenten zählen.
- **Offen für Paket 7 (7.5):** Ein unterlegener Job läuft nach X1 mit X2 weiter. Schreiben X3/X4
  ohne dieselbe zweite Prüfung, schrieben zwei Jobs sie doppelt. Vorher entscheiden: höchstens ein
  offener `extract.run` je Dokument (beim Start), oder dieselbe Prüfung unter der Dokumentsperre in
  jeder schreibenden Stufe. **Entschieden in 7a:** höchstens ein offener Job je Dokument, von der
  Datenbank erzwungen (Nachtrag Paket 7a). Nach einem Abbruch kann der alte Handler noch
  auslaufen; darum schreibt jede schreibende Stufe (X3/X4 in 7b) in einer Transaktion mit
  `hold_lease`, und vor jeder Modellanfrage prüft der Lauf die Lease (`check_lease`).

### Paket 7: X3 Rahmenteile und X4 Aussagen (6 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 7.1 | X3 Rahmenteile | `app/pipeline/x3_frame.py`, Prompt `prompts/x3.py` | `x3-rahmenteile` in `frame_part` (Modelle, Operatoren, Legende, Regeln) und Rahmenaussagen als Aussagen an einem Rahmenknoten; einmal je Dokument | `pytest -m pg tests/pipeline/test_x3_frame.py` |
| 7.2 | X4 Auftrag | `app/pipeline/prompts/x4.py` (Einheit, Blockbereich, Titelpfad, aktiver Lexikonausschnitt nach §12.2) | Auftrag verschieden je Einheit, Präfix gleich; nur passende Geltung im Ausschnitt | `pytest tests/pipeline/test_x4_prompt.py` |
| 7.3 | X4 Aussagen | `app/pipeline/x4_statements.py` (parallel, höchstens `EXTRACT_CONCURRENCY` Aufrufe je Dokument) | nur Block-IDs aus dem Bereich der Einheit; Werte aus dem Umfeld mit Herkunft `inherited`/`rule`, nicht als Wortlaut; Herkunft `model`, Prüfstand `proposed`; Einheit atomar | `pytest -m pg tests/pipeline/test_x4_statements.py` |
| 7.4 | Anbindung Abrechnung | Reservierung vor jedem Versuch (Paket 5) | Budgetende mitten in X4: fertige Einheiten bleiben, Rest offen, Lauf fortsetzbar | `pytest -m pg tests/pipeline/test_x4_budget.py` |
| 7.5 | Start über die API | `POST /api/v1/documents` (aus einer Konvertierung, Bereich, Land) → 202 mit Dokument und Job; `GET /api/v1/documents/{id}/runs` | Konto, Budget, Rate-Limit (401/403/429); fremde Konvertierung 404 | `pytest tests/api/test_documents.py` |
| 7.6 | Oberfläche Lauf | `views/DocumentView.vue` (Stufe, Fortschritt, fertige Einheiten schon während des Laufs), `refusals.ts` für `budget_exhausted` | Zustände; `role="status"` nur bei Stufenwechsel; axe ohne Befund | `vitest run`, Browser-Probe mit Mock-Modell |

**Nachtrag 7a – Start und Abbruch (24.10.)**

- **Schnitt.** Paket 7 ist geteilt: 7a (dieser Nachtrag) – ein offener Lauf je Dokument, Start
  über die API (7.5), Abbruch, die Dokumentseite ohne Einheiten (Teil von 7.6); 7b – X3, X4 und das
  Budget mitten in X4 (7.1–7.4), fertige Einheiten auf der Dokumentseite. Grund: Steuerung und
  Stufen getrennt, der Nutzer wünschte das Abbruchmanagement gleich mit, kleinere Prüfrunden.
- **Ein offener Job je Dokument (Variante A).** `job.unique_key` (Migration 0018) mit
  partiellem Unique-Index über wartende und laufende Jobs; Schlüssel `extract.run:<Dokument>`
  (`app/pipeline/extraction.py`, damit die API die Pipeline nicht lädt). `enqueue(unique_key=…)`
  weicht per `ON CONFLICT` und meldet den offenen Job (`OpenJob`); ein Start daneben in einer
  anderen Anfrage wartet auf dessen Zeile und weicht dann. Die zweite Prüfung in X1 unter der
  Dokumentsperre bleibt als zweite Linie.
- **Start (7.5).** `POST /api/v1/documents` legt das Dokument an und startet seine Extraktion in
  einer Transaktion samt Zulassung (eine Abweisung nimmt das Dokument mit zurück).
  `POST /documents/{id}/extraction` ist idempotent wie der Umwandlungsstart: läuft eine, 200 mit
  ihr – auch wenn die Zulassung abweisen würde (sie zu verfolgen kostet nichts). Ebenso
  `POST /documents`: wird ein Dokument desselben Kontos aus demselben Eintrag und derselben
  Konvertierung gerade extrahiert, 200 mit diesem Dokument und seinem Job statt eines zweiten
  (`made: false`; Formular doppelt abgeschickt, Anfrage wiederholt) – die Dokumentseite sagt dann,
  dass es die schon laufende ist und die Wahl im Formular nicht übernommen wurde. Nach dem Ende
  dieser Extraktion darf ein weiteres Dokument entstehen (anderer Bereich, andere Länder); ein
  anderer Eintrag derselben Datei legt sein eigenes an, und ein bewusster Neustart eines anderen
  Dokuments ist kein doppeltes Absenden und läuft. Beides wird unter der Sperre der Zulassung
  nachgesehen, auch wo sie abweist: ein Start daneben in einer anderen Anfrage wird so gefunden
  (Review 7a B1/B3, Nachprüfung R1). Starten darf nur der Eigentümer (er wird belastet), und nur,
  solange er den Inhalt des Eintrags lesen darf wie bei der Anlage (403 `file_hidden`, auch wo er
  den Eintrag gar nicht mehr sieht); eine wartende oder laufende verfolgt er auch ohne. Wer das
  Dokument sieht, liest es und seine Läufe. Abweichungen: die Route gibt
  den Job selbst zurück, nicht `{job}`; das Dokument nennt seine letzte Extraktion als
  `extraction: {job_id, status}` (nicht `extraction_job`), die `job_id` nur für Eigentümer und
  Admins, die sie verfolgen dürfen – die Redaktion liest den Status.
- **Läufe lesen.** `GET /documents/{id}/runs`: ein Lauf ohne Ausgang „läuft“ nur, solange sein Job
  genau diesen Versuch fährt und seither kein Lauf desselben Jobs begann (ein `release` zählt den
  Versuch zurück, der nächste fährt dieselbe Nummer), sonst `abandoned`; keine neue Ausgangsart
  (Migration 0017 bleibt). Ein abgekoppelter Handler, der an die Lease stößt, beendet noch seinen
  eigenen Lauf `failed` (`LeaseLost`) – sein Lauf, keine Stufe.
- **Abbruch.** Vorhanden waren API (`POST /jobs/{id}/cancel`), Herzschlag und Sweep. Neu: Nach dem
  Abbruchwunsch wartet der Worker höchstens `CANCEL_WAIT_S` (5 s, bei kürzerer Lease ein Drittel
  von ihr) auf den Handler und schreibt dann `cancelled`; vorher wartete er ohne Frist, ein
  hängender Handler (Aufruf, der den Abbruch übergeht, langsames Aufräumen) hielt Job und
  Worker-Platz, bis die Lease ablief. Ebenso nach verlorener Lease. Der Handler läuft abgekoppelt
  aus; seine Schreibversuche scheitern an der Lease, und vor jeder Modellanfrage – auch jeder
  Wiederholung – prüft der Zähler sie bei der Reservierung (`LedgerMeter` mit dem Job,
  `check_lease`), so dass er nichts mehr fragt und kostet. Einen laufenden Job erreicht der
  Abbruch beim nächsten Herzschlag (alle `JOB_LEASE_S`/3, 20 s bei 60 s). Oberfläche: „Abbrechen“ an jedem
  Auftrag (JobProgress) mit Rückfrage, danach „Abbruch angefordert“, dazu die Laufzeit. Kein
  automatischer Abbruch nach Höchstdauer (Messpunkt Paket 11: wie lange ein echter Lauf dauert).
- **Oberfläche.** Start aus der fertigen Umwandlung (`ExtractionStart`: Bereich, Länder, das Land
  des Eintrags vorgewählt), Dokumentseite `/dokumente/:id` (`DocumentView` mit
  `DocumentExtraction` und `DocumentRuns`), Dokumente in der Quellansicht (`SourceDocuments`, nur
  bei einer PDF). Die Redaktion, die den Job nicht verfolgen darf, liest den Stand aus dem Dokument,
  das nachgefragt wird, bis die Extraktion weiterrückt; Start und Ende sagt eine eigene Region,
  für Verfolgende wie für Nachfragende. JobProgress bleibt leise; den Abbruchwunsch sagt es einmal
  – der Fokus auf seinem Hinweis liest ihn, wo der Fokus woanders ist, die Region. Gründe gescheiterter Läufe in eigenen
  Worten, sonst als englisches Zitat. Eine selbst abgebrochene Umwandlung heißt „abgebrochen“,
  nicht „gescheitert“. Bereichsnamen an `cv:EducationSectors`, Länder an `laender.ttl`,
  Laufzustände an `RunState` gebunden (tests/documentWords.test.ts). Der Hinweis „lief schon“
  nach dem Formular steht einmal (History-State, beim Lesen verbraucht) und wird angesagt.
- **Offen für 7b.** Den Grund des letzten Fehlschlags auf der Dokumentseite zeigen: heute steht nach
  dem Neuladen nur „Letzte Extraktion: Fehlgeschlagen“, der Grund wird nur angesagt, solange die
  Seite den Job verfolgt (Browser-Probe 7a); `extraction` trüge dazu den Code des Jobs.
  **Erledigt in 7b** (`extraction.error_code`, für alle Leser).

**Nachtrag 7b – X3, X4, Budget in X4, Arbeitspakete (24.10.)**

- **Dateien.** Statt `x3_frame.py`: `x3_stage.py` (Lauf), `x3_read.py` (Antwort), `prompts/x3.py`;
  X4 in `x4_statements.py` (Lauf, Parallelität), `x4_question.py` (Frage je Einheit), `x4_read.py`,
  `x4_unit.py` (Schreiben), `prompts/x4.py`. Gemeinsam: `statement_read.py` (Aussageobjekt beider
  Schemas), `prompts/statements.py` (Regeln, Unterarten mit Profilhinweisen), `unit_prefix.py`
  (Profiltext, Abschnitte, Auswahllisten), `unit_question.py` (Präfixplan), `lexicon_excerpt.py`,
  `ground.py` und `asking.py` (aus X1 herausgelöst).
- **Einheit atomar, einmal je Dokument.** Tabelle `extraction_unit` (Migration 0019); eine Einheit
  schreibt Aussagen, Befunde und ihre Markierung in einer Transaktion unter der Lease. An einem
  bestehenden Knoten nimmt sie erst die Baumsperre (wie jeder Schreiber eines Baums, Migration 0014;
  auch `append_statements` nimmt sie), dann die Markierung: ein zweiter Schreiber wartet an der
  Sperre und weicht an der Markierung (seine Aussagen kollidierten sonst an den Positionen); ohne
  Knoten (Dokument ohne Überschriften) legt sie einen eigenen Knoten an (`x4.unit_without_node`,
  Herkunft Regel). Gelöschte Läufe oder Knoten lassen die Markierung stehen (`ON DELETE SET NULL`).
  Rahmenteile tragen ihre Reihenfolge in `frame_part.position` (nicht in der Id).
  Positionen je Teil eines Knotens: Teil · 10 000 + i – die Reihenfolge bleibt, wann auch immer die
  Teile fertig werden; Paket 9 darf neu nummerieren.
- **Präfix.** X3 und X4 lesen dasselbe Dokument mit Profiltext (aus dem Speicher, mit den eigenen
  Bezeichnungen aus X1); X4 zusätzlich die Auswahllisten aus X3 und die Unterarten des Profils mit
  ihren Hinweisen (stehen fürs Cache vor dem Haltepunkt). X3 fragt immer einmal, auch ohne
  Rahmenabschnitt (Modelle und Operatoren können überall stehen). Folgezeilen eines Blocks stehen
  um zwei Leerzeichen eingerückt (keine Dokumentzeile steht, wo der Prompt seine Teile markiert);
  jede gelesene Antwort nimmt sie aus ihren Texten wieder heraus (`prefix.as_written`), daher
  `x1-profile/3`. Wortlaut des Dokuments in Profil und Auswahllisten (Titel, Bezeichnungen,
  Marker, Labels, Operatoren) steht dort einzeilig.
- **Abweichungen.** Herkunft der X4-Aussagen `cv:orig_model` (nicht `orig_source` wie im Beispiel
  `ohm-kette.ttl`); Werte aus dem Umfeld werden nicht gespeichert (Befund
  `x4.value_from_surroundings`), die Vererbung bleibt abgefragt (konzept §7) – statt
  `inherited`/`rule` aus 7.3. `budget_exhausted` ist ein Job-Fehlercode (`jobMessages.ts`),
  kein Abweisungscode (`refusals.ts`, so in 7.6 genannt). Codes der Rahmenteile bleiben Notationen
  wie gegeben. Neuer Fehlercode `prefix_too_long` (kein Fenster passt): in X3 und X4 vor dem Lauf –
  X4 zählt die Fenster aller offenen Pakete, bevor eines gefragt wird; kein Lauf, kein Paket gefragt.
- **Budget mitten in X4.** Reicht der Rest für die nächste Reservierung nicht, beginnt kein Paket
  mehr; die laufenden werden fertig und geschrieben; Lauf `budget_exhausted`, ein neuer Job fragt nur
  die offenen. Ein Paket mit Antwort außer Form oder für eine andere Einheit bleibt offen
  (`x4.unanswered`), Lauf gescheitert (`model_unanswered`). Parallelität
  `min(EXTRACT_CONCURRENCY, DB_POOL_MAX_SIZE − 1)` – jede Einheit hält eine Verbindung zugleich.
- **Oberfläche.** Abschnitt „Arbeitspakete“ (`DocumentUnits.vue`, `GET /documents/{id}/units`),
  neu gelesen bei jedem Fortschritt des verfolgten Jobs (`JobProgress` meldet `progress`); die
  Region der Extraktion sagt jeden Schrittwechsel einmal, nicht jede gezählte Einheit.
- **Grenzen.** Ein X3-Aufruf kann bei langen Operatorenlisten an der Ausgabegrenze scheitern; der
  Lexikonausschnitt findet Hinweise nur über Wort oder Muster im Text (Messpunkte Paket 11).
- **Offen für Paket 9.** Löscht die Redaktion den Knoten einer Einheit, während diese an der
  Baumsperre wartet, scheitert die Markierung am Fremdschlüssel (allgemeiner Fehler, Versuche bis zur
  Grenze) – wie bei einem vor X4 gelöschten Knoten; dann als eigener Fehlercode abbilden.

### Paket 8: X5 Prüfung mit SHACL und X6 Reparatur (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 8.1 | Wortlaut gegen Blöcke | `app/pipeline/anchors.py` + `anchor_passage.py` (aus der alten App, geteilt, auf Blöcke umgestellt, über `asyncio.to_thread`) | Fundart exact/whitespace/elided/normalized/fuzzy/notFound gegen genau die genannten Blöcke; Schwellen wie in der alten App | `pytest tests/pipeline/test_anchors.py` |
| 8.2 | Plausibilität | `app/pipeline/x5_checks.py` (Überschrift als Aussage, Mindestinhalt, Aussageart passt zum Knotentyp, Pflichtfelder, Summen von Stunden/Anteilen) | je Regel ein Positiv- und ein Negativfall | `pytest tests/pipeline/test_x5_checks.py` |
| 8.3 | Kern-RDF je Dokument | `app/exports/kern_rdf.py` (Dokument, Spezifikation, Knoten, Aussage, Fundstelle mit den Eigenschaften aus 4.2–4.4) | ein L1-Testdokument aus den Tabellen ergibt genau die erwarteten Tripel; Namensraum-Bindungen gesetzt | `pytest -m pg tests/exports/test_kern_rdf.py` |
| 8.4 | SHACL-Tor | `app/pipeline/shacl.py` (pyshacl wie `pruefe.py`, ohne Inferenz, in einem Prozess-Pool; pyshacl wird Laufzeitabhängigkeit) | fehlerhaftes Beispiel liefert die erwarteten Verstöße; Messung der Varianten (ganzes Modell 20–23 s je Beispiel gemessen; Fokusknoten des Dokuments; Teilmodell aus Kern und Bereichsprofil) und Wahl der schnellsten mit gleichen Befunden; Zeitgrenze `SHACL_TIMEOUT_S` | `pytest tests/pipeline/test_shacl.py`, Laufzeit < 5 s je Testdokument |
| 8.5 | X5 als Stufe | letzte Stufe von `extract.run` | Befunde als Zeilen; ein zweiter X5-Lauf ersetzt die Befunde desselben Laufs | `pytest -m pg tests/pipeline/test_x5.py` |
| 8.6 | X6 Reparatur | `app/pipeline/x6_repair.py`, Job `extract.repair` (nur Einheiten mit Befunden, 0–2 Aufrufe, Schema wie X4; Redaktionsänderungen unangetastet) | nur fehlerhafte Einheiten; bearbeitete Aussagen nie überschrieben; danach X5 erneut | `pytest -m pg tests/pipeline/test_x6_repair.py` |

**Nachtrag 8a – X5 Prüfung ohne Modell (25.10.)**

Paket 8 ist geteilt: 8a = 8.1–8.5 (X5), 8b = 8.6 (X6 Reparatur, dazu die Oberfläche für Befunde).

- **8.1 Dateien.** Statt `anchors.py`: `anchor_match.py` (Nadel, exact, whitespace, elided),
  `anchor_fuzzy.py` (Stellen seltener Wörter, difflib), `anchor_passage.py` (Passage straffen),
  `anchor_check.py` (`check_wording`), `db/anchors.py` (lesen, schreiben). Schwellen wie in der alten
  App, durch einen Test festgehalten; die Überschriftzeile der alten Suche entfällt (Blöcke statt
  Markdown). Ein Wortlaut über 2.000 Zeichen (`MAX_FUZZY`) wird nur exact/whitespace/elided gesucht.
- **8.1 Abweichungen von der alten Suche** (Review 8a). Ein Treffer Wort für Wort zerschneidet kein
  Wort – „Lernfeld 12“ enthält „Lernfeld 1“ nicht, auch nicht als Bruchstück einer Auslassung –, wo
  der Wortlaut an diesem Rand einen Buchstaben oder eine Ziffer hat. Normalisiert gilt auch ein am
  Zeilenende getrenntes Wort („Kompe-“ / „tenzen“) und ein zerlegt geschriebener Buchstabe (u +
  U+0308), wie `text_hash` sie liest (`domain.wording.unparted`); ein Zitat endet nach den Zeichen
  seines letzten Buchstabens. Ein mit dem Absatz genannter Überschriftblock ist eine Zeile wie jede:
  welcher Block Überschrift ist, sagen die Texte nicht, und ein Satz über einen Seitenumbruch beginnt
  im ersten Block. Der Wert eines unscharfen Zitats kann unter 0,8 liegen (das Fenster nie): es hält
  den ganzen Wortlaut und läuft über das Ausgelassene weiter.
- **8.1 Was geprüft wird.** Fundstellen ohne Fundart an Aussagen (Wortlaut `verbatim`) und an Knoten
  (Wortlaut `original_title`); Fundstellen von Rahmenteilen, Spezifikationen und dem Dokument haben
  keinen eigenen Wortlaut und bleiben ohne Fundart, ebenso der Knoten, den X4 einer Einheit ohne
  Überschrift gibt (`x4.unit_without_node`): er trägt den Titel des Dokuments, nicht den Wortlaut
  seiner Blöcke. Eine gesetzte Fundart überschreibt X5 nicht. Der
  Text einer Fundstelle sind die Texte ihrer Blöcke in Lesereihenfolge, mit Zeilenende verbunden;
  auf ihn beziehen sich `char_start`/`char_end`. `quote` ist der Text des Dokuments an der Stelle;
  über 20.000 Zeichen bleibt er leer, die Spanne bleibt.
- **8.1 Nicht gefunden.** `cv:match_notFound` lässt die Blöcke stehen: Sie sind die Behauptung des
  Modells. Der Befund `x5.wording_not_found` (Verstoß) wird aus den Fundstellen gelesen – notFound mit
  Blöcken –, findet sich also auch in einem späteren X5-Lauf wieder; von Hand angelegte Fundstellen
  ohne Block (9.4) ergeben keinen. Unscharfe Treffer an Aussagen meldet SHACL selbst
  (`StatementPlausibilityShape`, Warnung), X5 nicht doppelt; an Knotenüberschriften meldet sie
  niemand – deren Titel nimmt X2 aus den Blöcken selbst, unscharf werden sie erst durch eine
  Änderung (offen für 8b/Paket 9).
- **8.2 Regeln.** `x5.heading_as_statement` (Warnung), `x5.unit_without_statements` (Hinweis; ohne
  `checked_absent`), `x5.rule_bounds` (Warnung; min > max, Anteil außerhalb 0..1),
  `x5.retired_value` (Warnung; zurückgezogene Funktion, Knotentyp, Art, Unterart,
  Verbindlichkeit). Nicht
  in X5: „Aussageart passt zum Knotentyp“ (kein Vokabularprädikat nennt erlaubte Arten; Unterart zu
  Art und Knotentyp zu Funktion prüft SHACL), Pflichtfelder (SHACL) und Summen von Stunden und
  Anteilen (Arbeitsumfang erst L2/M3).
- **8.3 Export.** `exports/kern_rows.py` liest das Dokument in einem Snapshot – allein oder in einer
  Transaktion des Aufrufers mit Snapshot (repeatable read); in einer ohne verweigert es (die
  Verbindung des Pools nach ihrer ersten Abfrage); X5 liest Befunde und Graph zusammen in einem.
  `exports/kern_rdf.py` baut den Graphen. Jede Zeile ist `urn:uuid:<id>`, so bildet ein SHACL-Fokus
  direkt auf die Zeile ab. Ein Wurzelknoten hängt an der einzigen in `applies_to` genannten
  Spezifikation, sonst an der einzigen des Dokuments, sonst am Dokument. Ein Knoten trägt als
  `cur:checkedAbsent` die Andockpunkte, die alle seine Einheiten als fehlend geprüft haben (ein Teil
  eines Knotens bürgt nicht für einen anderen); die Profilformen lesen sie. `purposeText` ist
  `cur:purpose`, `codeText` `cur:code`; eine Region ist ihr aktives Konzept. Nicht exportiert in M1:
  Rahmenteile und ihre Fundstellen (L2), eigene Begriffe des Profils, Fundstellen von Dokument und
  Spezifikation, die Geltung (`applicability`) einer Spezifikation.
- **8.3 In M1 sichere Warnungen.** Der Export schreibt keinen Arbeitsumfang, keine Zeitspanne und
  keine Zerlegung (L2): ein `beruf:Lernfeld` ohne `checkedAbsent` für die Zeit warnt zweimal, ein
  `hs:Modul` ohne Leistungspunkte einmal, jedes Lernergebnis gibt den Hinweis der Zerlegung. Das sind
  Warnungen und Hinweise, keine Verstöße; X6 (8b) nimmt sie nicht als Anlass einer Reparatur.
- **8.4 Prozess.** Statt eines Prozess-Pools prüft ein Kindprozess je Dokument, über `core/child.py`
  (aus `conversion/runners.py` herausgelöst, verhaltensgleich: Frist, Abbruch, Lease-Verlust,
  `oom_score_adj`). Ein Thread hielte den GIL über die ganze Prüfung.
- **8.4 Varianten, gemessen** (Messskripte nicht im Repository; die Gleichheit mit V1 sichert
  `test_shacl.py` an allen sechs Beispielen und einem exportierten Dokument): V1 ganzes Modell wie
  `pruefe.py` 13,6–16,1 s je Beispiel; V2 mit den Zeilen
  des Dokuments als Fokus 1,6–4,0 s; V3 dazu ohne Lexika, Alignments und Migration 1,2–3,5 s;
  Befunde von V2 und V3 an allen sechs Beispielen gleich V1. An Export-förmigen Dokumenten wuchs
  V3 überlinear (202 Fokus 13,7 s, 802 57,5 s, 2.402 191,7 s): rdflib parst und übersetzt jede
  SPARQL-Abfrage je Fokusknoten neu. Gewählt: V3 mit Fokus und im Kindprozess gehaltenen
  Übersetzungen – 2,3 s, 8,5 s, 43,3 s. Die Abfrage 5 von `HsModuleShape` (Arbeitsumfang) wächst
  mit Arbeitsumfang-Daten weiter überlinear; der M1-Export schreibt keine, in M3 messen.
- **8.4 Frist und Befunde.** `SHACL_TIMEOUT_S` Standard 300 s (10–1800; das Ziel < 5 s gilt für
  die Testdokumente, ein langer Plan braucht länger). Nach der Frist: Befund `x5.shacl_timeout`
  (Verstoß, Tor zu), X5 endet trotzdem `done`. Regel `shacl.<Shape>`, Fokus die Zeile, sonst das
  Dokument mit `details.focus`; ohne Meldung steht der Name der Form.
- **8.5 Stufe.** `x5_stage.py`, Test `test_x5_stage.py`. Erst die Fundarten unter Lease und
  Baumsperre, dann Befunde und Laufende in einer Transaktion unter Lease und `lock_for_stage`
  (Superseded wie X1–X4). Ergebnis `{"anchors": {Fundart: n}, "findings": {Schwere: n},
  "shacl": "done"|"timeout"}`, Fortschritt `check_document`, Stufenwort „Prüfung“.
  „Ein zweiter X5-Lauf ersetzt die Befunde“ wandert nach 8b: In 8a läuft X5 je Dokument einmal
  (eine fertige Stufe wird übersprungen); erst die Reparatur startet X5 neu. Die Zahl der Fundarten
  im Ergebnis liest X5 aus den Fundstellen, wie sie stehen: ein Versuch nach einem gescheiterten, der
  die Fundarten schon schrieb, zählt sie auch.
- **Offen für Paket 9.** X5 liest den Wortlaut ohne Baumsperre und schreibt die Fundart unter ihr,
  nur wo noch keine steht. Ändert die Redaktion einen Wortlaut und setzt die Fundart zurück, während
  X5 ihn prüft, schriebe X5 die Fundart des alten Wortlauts: dann das Schreiben an den geprüften
  Wortlaut binden (oder an einen Stand der Zeile).

### Paket 9: Editor, Redaktion und Festschreiben (8 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 9.1 | Formularschema | `app/vocab/forms.py`, `GET /api/v1/profiles/{bereich}/form` (Felder und Kardinalität aus `cur-shapes.ttl`, Wertelisten, Knotentypen und Unterarten mit Label, Definition, Beispielen) | Feldliste für Knoten und Aussage stimmt mit den Shapes; nur aktive Werte | `pytest -m pg tests/api/test_forms.py` |
| 9.2 | Baum lesen | `GET /api/v1/documents/{id}/tree` | Sichtbarkeit; Zähler je Prüfstand | `pytest tests/api/test_tree.py` |
| 9.3 | Knoten bearbeiten | `POST/PATCH/DELETE /api/v1/nodes/{id}` mit `expected_revision` (409), Herkunft `human` bei Änderung | Revision steigt; 409 mit gespeichertem Stand; Schreibrechte Eigentümer/Redaktion | `pytest tests/api/test_node_editing.py` |
| 9.4 | Aussagen bearbeiten | `POST/PATCH/DELETE /api/v1/statements/{id}`, Fundstelle per Blockauswahl oder `notFound` mit Seite | wie 9.3; Aussage ohne Fundstelle abgewiesen (422) | `pytest tests/api/test_statement_editing.py` |
| 9.5 | Prüfstand | `POST /api/v1/documents/{id}/review` (einzeln und gesammelt, Rolle `redaktion`) | nur Redaktion; Zähler | `pytest tests/api/test_review.py` |
| 9.6 | Festschreiben | Migration `freeze` (Trigger), `POST …/freeze`, `POST …/draft-copy`, Werk setzen (`PATCH …/work`), IRI-Vergabe | Änderung an festgeschriebenen Daten scheitert in der Datenbank; Entwurfskopie mit neuer Revision, gleichen IRIs, Prüfstand übernommen; vorige Revision lesbar | `pytest -m pg tests/db/test_freeze.py tests/api/test_freeze.py` |
| 9.7 | Baum | `components/TreeView.vue`, `TreeNodeItem.vue`, `treeRows.ts` (aus der alten App, geteilt, auf Knoten + Aussagen umgestellt), Filter nach Prüfstand | ARIA-Baum, Pfeiltasten, eine Tabstopp-Stelle; axe ohne Befund | `vitest run` |
| 9.8 | Formulare | `components/NodeForm.vue`, `StatementForm.vue` (aus dem Formularschema; Muster `ContextEditor`), `nodeConflict.ts` + `NodeConflict.vue` (Kopie) | Feld je Schema-Eintrag; Pflicht in Text; Fehler am Feld mit `aria-describedby`; Konfliktauswahl je Feld; axe ohne Befund | `vitest run` |
| 9.9 | Quellenbeleg | `components/SourcePane.vue` (Blöcke der Seite neben dem Formular, genannte markiert, Blockauswahl als Fundstelle), `SourceQuote.vue` + `sourceAnchor.ts` (Kopie) | Fundart in Worten; Markierung nicht nur farbig; axe ohne Befund | `vitest run` |
| 9.10 | Festschreiben in der Oberfläche | `FreezeDialog.vue`, `FrozenNotice.vue` (aus `RunFreezeDialog.vue`/`FrozenRunNotice.vue`), Befunde je Knoten, Quelltyp, Lizenz und Abrufkette in der Dokumentansicht | Fokus auf „Abbrechen"; danach nur Lesen und „Als Entwurf kopieren" | `vitest run`, Browser-Probe |

### Paket 10: Lexikon aus der Länderrecherche mit Stichprobe (3 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 10.1 | Übernahme als TTL | `ontology/werkzeuge/importiere_recherche.py` (liest `recherche-ergebnisse/*.md`, schreibt `profile/laender/<bereich>-DE-XX.ttl`) | Stärke höchstens 0,7, `verified false`, Beleg E/S/A als Fundstelle; T2 → Überschriftenmuster mit Beispielen, T4 → `qz:`, T5 → `lvl:`; Korrekturen an Vorlisten-Hinweisen nur als Vorschlag (Kommentar), nicht als Änderung | `python -I ontology/pruefung/pruefe.py` OK, `pytest tests/lexicon/test_importer.py` |
| 10.2 | Prüfbericht | `ontology/werkzeuge/pruefe_recherche.py` erweitert (Zeilen je Datei, verschobene Spalten, Werte außerhalb, unbekannte Ziele, Anteil E) und Kollisionsbericht von `pruefe.py` | Bericht scheitert mit Exit-Code ≠ 0 bei verschobenen Spalten | `pytest tests/lexicon/test_report.py` |
| 10.3 | Stichprobe | Migration `cue_review`, `app/lexicon/sample.py` (geschichtet je Bereich und Land, fester Seed), `GET/POST /api/v1/lexicon/review` (Redaktion), `python -m app.lexicon.export_reviews` (schreibt `verified` und Stärke bis 0,9 in die TTL) | reproduzierbare Stichprobe; nur Redaktion; Hochstufung nur mit Fundstelle; Export ändert nur die betroffenen Hinweise | `pytest -m pg tests/lexicon/test_sample.py` |
| 10.4 | Neue Begriffe aus X1 | `newTerms` landen in derselben Prüfliste („neuer Hinweis / Dokumentbesonderheit / Fehler"); „neuer Hinweis" geht über den Export als ungeprüfter Hinweis in die TTL | Entscheidung je Begriff; nichts ohne Redaktion | `pytest -m pg tests/lexicon/test_new_terms.py` |
| 10.5 | Oberfläche | `views/LexiconReviewView.vue` | Zustände, Tastatur, axe | `vitest run` |

### Paket 11: Abnahme M1 (2 PT)

1. Fünf Lehrpläne mit Textebene, je Bereich einer, amtlich oder vom Träger veröffentlicht (für
   Kita und EB gibt es oft nichts Amtliches); Titel, Adresse und Größe werden vorher genannt,
   geladen erst nach Zusage, abgelegt nur im lokalen Objektspeicher (nicht im Repo).
2. Kostenschätzung je Dokument aus Blockzahl, Einheiten, Extraktionstiefe und Präfixlänge
   (gezählt), Zusage des Nutzers, dann echte Läufe mit seinem Schlüssel aus der Umgebung.
3. Zwei Worker parallel, ein Konto mit knapper Grenze: Summe in `llm_usage` gleich der Summe
   der Nutzungsangaben in den Rohantworten; die Grenze wird nicht überschritten.
4. Bericht je Dokument: Knoten, Aussagen, Fundarten, Befunde nach Schwere, Laufzeit, Token,
   Kosten; Stichprobe von 20 Aussagen je Dokument gegen das Original als erste Vorlage des
   Goldstandards. Präzision je Quelle und Kalibrierung folgen mit dem Goldstandard-Werkzeug in
   M4 (Gesamtplan §7.1.4–5).

## Abnahme M1

- Ein Lehrplan je Bereich läuft von der Quelle bis X5 durch; die Ergebnisse sind im Editor
  sichtbar, bearbeitbar, prüfbar und festschreibbar.
- X5-Befunde stehen als Zeilen in `validation_finding`; das SHACL-Tor nutzt die Shapes aus
  `ontology/` ohne Inferenz und bleibt unter der Zeitgrenze.
- Quote und Abrechnung stimmen unter parallelen Workern (Stresstest 5.5 und Abnahme 11.3).
- Saat: Kandidaten aus dem Vergleichsdatensatz und der Länderrecherche stehen im Register;
  der Prüfjob läuft erst nach Zusage des Nutzers, weil er 34 fremde Hosts anfragt.
- Alle Tests aus M0 und M1 grün; ruff, mypy, vue-tsc, eslint ohne Befund.

## Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| pdfplumber erkennt Überschriften und Tabellen schlechter als Docling | Gerüst stützt sich auf Verzeichnis, Muster und Lexikon; Paket 3b; Tabellen-Fixtures |
| Zwei Drittel der Saat sind HTML-Seiten (1.186 von 1.831 Zeilen, v. a. lehrplanplus.bayern.de, bildungsplaene-bw.de) | Prüfjob vermerkt den Typ; HTML-Konvertierung mit 3b; die Abnahme nutzt PDFs |
| Modell liefert Profilwerte außerhalb des aktiven Profils | Prüfung nach dem Aufruf, Befund statt Absturz; X6 repariert |
| Kosten echter Läufe | Obergrenze je Anfrage, Reservierung je Versuch, Schätzung vor jedem Lauf, Abnahme nur nach Zusage |
| SHACL-Laufzeit (ganzes Modell ~20 s je Dokument) | Prozess-Pool, Messung der Varianten in 8.4, Zeitgrenze |
| SSRF über URL-Import und Prüfjob | IP-Pinning, Weiterleitungen einzeln geprüft, `trust_env=False`; Egress-NetworkPolicy im Helm-Beispiel |
| ReDoS durch ungeprüfte Hinweis-Muster | `regex` mit Zeitgrenze; Muster nur aus geprüften TTL-Dateien |
| Länderrecherche ungeprüft | Übernahme nur als „nicht geprüft" mit Stärke ≤ 0,7; Hochstufung nur über die Stichprobe |
| Datenmenge `document_block` | Text je Block, Index nur auf (Konvertierung, Block-ID); Messung in der Abnahme |
| Umfang | Pakete mit eigenem Review; 3b getrennt |

## Offene Punkte

- Rechtestatus je Land: keine Recherche vorhanden; bis zur Lizenzprüfung gilt `unklar`
  (Gesamtplan §16, Frage 1).
- Download der Docling-, Layout- und OCR-Modelle: eigene Freigabe (Paket 3b).
- Quellenlose Entwürfe (Lehrplankommission) brauchen eine Änderung am Kern; nicht in M1.
