# Detailplan M1: Quellen und Extraktion L1

Stand 22.10.2026, Entwurf zur Freigabe. Teil des [Gesamtplans](2026-10-21-gesamtplan.md),
Abschnitt 12 (M1, 40–55 PT). Ziel: Lehrpläne aus dem Quellregister über Konvertierung (X0) und
Extraktion (X1–X4) mit Prüfung (X5) und Reparatur (X6) als L1-Daten nach Curriculum-Kern 1.0
erfassen, mit Abrechnung, schemagetriebenem Editor, Redaktion und Festschreiben.
Voraussetzung: M0 einschließlich Paket D (Downloads am 22.10.2026 freigegeben).

## Arbeitsweise

- Wie in M0: je Paket Schritt 0 `/better-coding-workflow` laden (bei Oberfläche zusätzlich
  `/better-coding-frontend`); jede Aufgabe beginnt mit dem roten Test; nach jedem Paket
  `/better-coding-review` mit frischen Prüfern in Scheiben, Befunde mit
  `/better-coding-workflow` beheben, Korrekturen gezielt gegenprüfen lassen (Rückschritte),
  dann `/better-coding-verify` und `main` per Fast-Forward. Kein Push ohne Auftrag.
- **Kein echtes Sprachmodell in Tests:** Modellaufrufe laufen gegen `FunctionModel` bzw. einen
  httpx2-Mock-Transport hinter `build_model`. Echte Läufe nur in der Abnahme (Paket 11), nach
  Kostenschätzung und Zusage des Nutzers; der Schlüssel kommt aus seiner Umgebung, nie in
  Dateien oder Ausgaben.
- **Downloads:** `python-multipart`, `pdfplumber`, `pdfminer.six` und `pypdfium2` liegen im
  lokalen uv-Cache (offline installierbar). Docling, EasyOCR und DOCX-Unterstützung (grob 1 GB
  mit Modellen) erst nach eigener Freigabe (Paket 3b). Die fünf Abnahme-PDFs werden vor dem
  Laden einzeln mit Titel, Adresse und Größe genannt.
- Dateien über 300 Zeilen werden nach Zuständigkeit geteilt; die alte App liefert geprüfte
  Bausteine als Kopie mit ihren Tests (Gesamtplan §10), nie als Abhängigkeit.

## Festlegungen für M1

- **Ontologie als Quelle:** Pflichtwerte (Aussageart, Adressat, Funktion, Herkunft,
  Prüfstand, Fundart, Stufe, Dokumenttyp, Bereich …) sind Fremdschlüssel auf
  `vocab_concept.iri`; neue Schreibzugriffe prüfen `retired_in IS NULL`. Profilwerte
  (Knotentyp, Unterart, Dokumenttyp) müssen außerdem zum aktiven Profil passen
  (`skos:broader` auf den Kernwert). Ausgabeschemas der LLM-Stufen sind die Dateien in
  `ontology/schemas/`, eingelesen als `pydantic_ai.StructuredDict`; nichts davon wird im Code
  abgeschrieben.
- **Was der Kern nicht kennt, regelt die App** (Gesamtplan §7): Rechtestatus (`amtlich`,
  `offen_lizenziert`, `geschuetzt`, `unklar`, Standard `unklar`) und Quelltyp (`amtlich`,
  `archiv`, `spiegel`, `sekundaer`) als CHECK-Listen an Quelle und Dokument; Prüfstand an
  Knoten und Aussagen mit den Werten aus `cv:ReviewStatuses` (`proposed`, `confirmed`,
  `rejected`); Festschreiben als Zustand des Dokuments.
- **Tabellen nach Kern-L1**, jede adressierbare Zeile über `entity (id, kind)`:
  `source`, `source_file`, `acquisition`, `access_note`, `conversion`, `document_block`,
  `work`, `document`, `specification`, `document_specification`, `node`, `statement`,
  `statement_addressee`, `anchor`, `anchor_block`, `extraction_run`, `validation_finding`,
  `terminology_profile`, `lexical_cue`, `cue_review`, `llm_usage`, `conversion_usage`,
  `quota`, `usage_reservation`. Tiefe eines Knotens wird aus `parent_id` abgeleitet, nicht
  gespeichert.
- **Block-IDs** `p<Seite>-b<Block>` (Muster aus `cur-shapes.ttl`), Seite physisch und 1-basiert;
  gedruckte Seitenzahl separat, wenn erkennbar. Der Dokumenttext für die Prompts ist der
  Blocktext mit vorangestellter Block-ID je Block.
- **Job-Arten:** `source.fetch`, `source.check`, `source.convert`, `extract.run` (X1–X4,
  danach X5), `extract.repair` (X6). Handler bekommen ihre Abhängigkeiten über einen
  `JobContext` (Pool, Speicher, Settings, Modellfabrik) aus einer Fabrik
  `make_handlers(context)`; keine Modul-Globalen. Fortschritt schreibt der Handler in eine neue
  Spalte `job.progress` (Code + Parameter), lease-geprüft.
- **Sichtbarkeit in SQL:** Einträge ohne Eigentümer (Saat, Recherche) sehen alle Konten;
  hochgeladene Quellen und Dokumente sieht das Eigentümerkonto sowie `redaktion` und `admin`.
  Öffentlicher Zugang folgt in M5. Gefiltert wird in der Abfrage, nie nach dem Laden.
- **Kosten:** `llm_usage` je Aufruf (Eingabe, davon Cache, Ausgabe, Anfragen, unbeantwortete
  Anfragen), `conversion_usage` je Konvertierung (Seiten, Engine, abrechenbar). Grenzen je
  Konto in `quota` (Token, Seiten; `NULL` = unbegrenzt, Seitengrenze nur für abrechenbare
  Engines; pdfplumber ist nicht abrechenbar). Vor jedem Modellaufruf reserviert der Job in
  einer Transaktion mit `SELECT … FROM quota … FOR UPDATE` die Obergrenze des Aufrufs
  (gezählte Eingabe-Token + `LLM_MAX_OUTPUT_TOKENS`); nach dem Aufruf ersetzt die Buchung die
  Reservierung. Damit überschreitet auch ein Konto mit parallelen Workern seine Grenze nicht.
- **IRIs** nach konzept §11 mit Basis `IRI_BASE` (Standard die w3id-Platzhalter des Kerns);
  fehlende Codes vergibt die Pipeline aus der Position (`code_assigned`). `text_hash` nach
  konzept §11 (NFC, Kleinschreibung, Leerraum, Trennstriche, ohne führende Nummer).
- **Festschreiben:** `document.frozen_at`/`frozen_by`; ein Trigger weist jede Änderung an
  Knoten, Aussagen und Fundstellen eines festgeschriebenen Dokuments ab. „Als Entwurf
  kopieren" legt eine neue Fassung an (`supersedes`), mit neuen IDs und IRIs.
- **Lesekontext** nach konzept §13.1: ein gecachter Präfix je Dokument (Blocktext, Dokumentprofil
  aus X1, Auswahllisten aus X3), dahinter `CachePoint`, danach der Auftrag je Einheit. Zu
  lange Dokumente: Präfix aus Titelei, Inhaltsverzeichnis, Rahmenteilen und dem Abschnitt der
  Einheit samt Nachbarn; die Grenze misst `count_tokens`.
- **Rohantworten** jedes Modellaufrufs liegen im Objektspeicher unter
  `runs/<run-id>/<stufe>/<n>.json`; `extraction_run` verweist darauf.

## Pakete

Reihenfolge: zuerst der schmalste durchgehende Schnitt (Upload → Register → Konvertierung →
Blockansicht), dann Daten und Abrechnung, dann die Stufen, dann Editor und Lexikon. Pakete 2
und 10 hängen nur an Paket 1 bzw. 4 und können parallel laufen.

### Paket 1: Quellregister und Upload (4 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 1.1 | Speicher in die App | `app/core/settings.py` (`storage_backend` fs\|s3, `storage_dir`), `app/core/storage.py` (`open_storage(settings)`), `app/api/app.py` (`app.state.storage`) | Settings-Standard; `open_storage` liefert das Dateisystem; `create_app` hängt den Speicher an | `pytest tests/core/test_storage.py tests/api/test_app.py` |
| 1.2 | Job-Kontext und Fortschritt | `app/jobs/context.py` (`JobContext`, `make_handlers`), Migration `0005_job_progress.sql` (`job.progress jsonb`), `app/jobs/queue.py` (`report_progress(conn, job, code, params)`) | Handler bekommt Pool und Speicher aus dem Kontext; Fortschritt nur mit gültiger Lease; Worker-Einstieg baut den Kontext | `pytest -m pg tests/jobs/` |
| 1.3 | Job-Abfrage | `app/api/jobs.py` (`GET /api/v1/jobs/{id}`, `POST /api/v1/jobs/{id}/cancel`) | fremde Jobs 404; Status, Fortschritt, Fehlercode; Abbruch nur durch die Spur | `pytest tests/api/test_jobs.py` + Wächter `test_auth_surface`, `test_openapi` |
| 1.4 | Dateiprüfung | `app/sources/filetype.py`, `app/sources/archives.py` (Kopie `filetype.py` der alten App mit Tests) | Magic Bytes PDF; ZIP-Regeln (5.000 Teile, 256 MiB, 100× je Teil > 1 MiB); unbekannter Typ abgewiesen | `pytest tests/sources/test_filetype.py` |
| 1.5 | Tabellen Register | Migration `0006_sources.sql`: `source`, `source_file` (SHA-256 eindeutig), `acquisition` | Rechtestatus- und Quelltyp-Listen greifen; gleiche Datei zweimal → eine `source_file`; `entity.kind` passt | `pytest -m pg tests/db/test_sources_schema.py` + `test_db_checks` |
| 1.6 | Upload | `app/api/sources.py` (`POST /api/v1/sources`, multipart, Lesen in 1-MiB-Stücken, 50 MB je Datei → 413), `app/db/sources.py`, Abhängigkeit `python-multipart` | PDF landet im Speicher unter `sources/<sha256>`; 413 und 415 mit eigenem Code; Konto nötig; Audit-Zeile | `pytest tests/api/test_sources_upload.py` |
| 1.7 | URL-Import | `app/sources/url_fetch.py` (Kopie `url_import.py` + `http_body.py`), Job `source.fetch` | nur http/https; private, Loopback- und Link-Local-Adressen abgewiesen, auch nach Weiterleitung; Größengrenze nach Entpacken; Ergebnis als `acquisition`-Zeile | `pytest tests/sources/test_url_fetch.py tests/jobs/test_source_fetch.py` (Mock-Transport, kein Netz) |
| 1.8 | Register lesen und pflegen | `GET /api/v1/sources` (Seiten, Filter Status/Land/Herkunft/Text), `GET /api/v1/sources/{id}`, `PATCH /api/v1/sources/{id}` (Redaktion: Rechtestatus mit Beleg, Quelltyp, Lizenz, Titel, Land, Bereich), `GET /api/v1/sources/{id}/file` | Sichtbarkeit in SQL (fremder Upload 404); `nutzer` darf den Rechtestatus nicht setzen (403) | `pytest tests/api/test_sources.py` |
| 1.9 | Oberfläche Register | `frontend/src/views/SourcesView.vue`, `components/UploadPanel.vue`, `components/JobProgress.vue` (angepasst aus der alten App samt Tests), `api/sources.ts`, `api/jobs.ts`, Katalogtexte | Liste mit Lade-, Leer-, Fehlerzustand; Upload mit `role="status"`; URL-Formular; Job-Fortschritt mit Backoff 1→8 s und Stopp bei 401/404; axe ohne Befund | `vitest run`, Browser-Probe |

### Paket 2: Saat aus dem Vergleichsdatensatz und Prüfjob (3 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 2.1 | Daten ins Repository | `data/seed/vergleichsdatensatz/{lehrplan_dokumente_de,umgehungshinweise_de}.csv` (CC0, Stand v62.493) mit `README.md` (Herkunft, Lizenz, Prüfsummen) | Prüfsummen im Test gleich denen im README | `pytest tests/sources/test_seed_files.py` |
| 2.2 | Saat-Import | `app/sources/seed.py`, Einstieg `python -m app.sources.seed` | Kandidaten mit Herkunft `vergleichsdatensatz-v62.493`, Status `unchecked`; ESA-Ableitungen und „kanonisch" ausgelassen; `URL=lokal` nimmt `URL_Original`; zweiter Lauf ändert nichts; Titel, Themen, Knotenzahlen werden nicht übernommen | `pytest -m pg tests/sources/test_seed.py` |
| 2.3 | Zugangsnotizen | Migration `0007_access_notes.sql`, Import aus `umgehungshinweise_de.csv` | Kategorie, Land, Hinweis, URL; Abruf eines Portals mit Sperre wird nicht umgangen | `pytest -m pg tests/sources/test_access_notes.py` |
| 2.4 | Länderrecherche T1 als zweite Saat | `app/sources/research_t1.py` (liest die T1-Blöcke aus `ontology/recherche-ergebnisse/*.md`) | Herkunft `laenderrecherche`, Beleg E/S übernommen; Abgleichbericht: URL nur in Saat, nur in Recherche, in beiden | `pytest -m pg tests/sources/test_research_t1.py` |
| 2.5 | Prüfjob | Job `source.check` (ein Abruf je URL: erreichbar, Typ, Größe, SHA-256, Datum; höchstens ein Abruf je Host alle 2 s; keine Umgehung von Sperren) | Mock-Transport: 200/404/403/Weiterleitung/Zeitüberschreitung ergeben die richtigen Status; Abbruch hält an | `pytest tests/jobs/test_source_check.py` |
| 2.6 | Oberfläche | Filter „Kandidaten" und Prüfstart im Register, Zugangsnotiz je Eintrag | Zustände und Tastatur wie Paket 1 | `vitest run` |

### Paket 3: Konvertierung X0 mit Block-IDs (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 3.1 | Engine-Schnittstelle | `app/conversion/base.py` (`Block(id, page, kind, text, bbox, font_size, bold, italic, cells)`, `Conversion(blocks, pages, printed_pages)`, Register), Kopie `text_layer.py`, `table_md.py` | Block-ID-Muster; Register nennt angebotene Engines | `pytest tests/conversion/test_base.py` |
| 3.2 | pdfplumber-Blöcke | `app/conversion/pdfplumber_blocks.py`, Abhängigkeiten `pdfplumber`, `pdfminer.six`, `pypdfium2` (offline) | Zeilen zu Blöcken nach Abstand und Schriftwechsel; fett/kursiv aus dem Schriftnamen; Tabellen als ein Block mit Zellen `T<n>:r<i>c<j>`; Lesereihenfolge; Testdateien aus `tools/_fixture_pdfs` der alten App | `pytest tests/conversion/test_pdfplumber_blocks.py` |
| 3.3 | Rand und Symbole | `app/conversion/page_edges.py` (aus `repeated_blocks.py`), `app/conversion/symbols.py` | Kopf-/Fußzeilen markiert statt gelöscht; gedruckte Seitenzahl erkannt; U+F0DA → ➔, U+F0DE → ⇒ und die übrigen PUA-Zeichen der Tabelle | `pytest tests/conversion/test_page_edges.py tests/conversion/test_symbols.py` |
| 3.4 | Kindprozess | `app/conversion/runners.py` (Kopie, ohne globale Settings) | Frist und Abbruch beenden den Prozess; Ergebnis als JSON zurück; Linux-Teile nur unter POSIX | `pytest tests/conversion/test_runners.py` |
| 3.5 | Tabellen und Job | Migration `0008_conversion.sql` (`conversion`, `document_block`, `conversion_usage`), Job `source.convert` | Seitengrenze `MAX_PDF_PAGES` (800); leere Ausgabe ist ein Fehler; Blöcke und Markdown gespeichert; `conversion_usage` je Lauf, Wiederholung bucht nicht doppelt | `pytest -m pg tests/jobs/test_source_convert.py` |
| 3.6 | API und Oberfläche | `POST /api/v1/source-files/{id}/conversions`, `GET /api/v1/conversions/{id}`, `GET …/blocks?page=`; `views/ConversionView.vue` (Seiten mit Blöcken, Block-ID sichtbar, Tabellen als Tabellen) | Fortschritt, Fehler mit Grund, Blockansicht per Tastatur seitenweise | `pytest tests/api/test_conversions.py`, `vitest run` |

**Paket 3b (nach Download-Freigabe):** Docling mit EasyOCR (CPU) und DOCX hinter derselben
Schnittstelle; Blöcke aus `iterate_items()`/`prov` mit BBox; Auswahl der Engine je
Konvertierung. Bis dahin: Dateien ohne Textebene werden mit dem Code `needs_ocr` abgewiesen.

### Paket 4: L1-Datenmodell, Profile und Lexikon laden (4 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 4.1 | Vokabular nachschlagen | `app/vocab/lookup.py` (`concept(conn, iri)`, `by_notation(conn, scheme, notation)`, `profile_concepts(conn, sector)` für Knotentypen, Unterarten, Dokumenttypen mit Kernwert) | zurückgezogene Begriffe nicht neu wählbar; Zahlen je Profil wie in der TTL (schul 10/13/8 …) | `pytest -m pg tests/vocab/test_lookup.py` |
| 4.2 | L1-Tabellen | Migration `0009_l1.sql`: `work`, `document`, `specification`, `document_specification`, `node`, `statement`, `statement_addressee`, `anchor`, `anchor_block`, `extraction_run` | Fremdschlüssel auf `vocab_concept`; Baum ohne Zyklen (Trigger); Aussage nur an Knoten; Block-ID-Muster; Unterart passt zur Art | `pytest -m pg tests/db/test_l1_schema.py` |
| 4.3 | Domänenregeln | `app/domain/l1.py` (ohne Framework-Importe): `text_hash`, IRI-Bildung, Code-Vergabe aus Position, Prüfung Profilwert ↔ Kernwert | Beispiele aus konzept §11; Importtest: `domain` importiert nichts aus `api`, `db`, `jobs` | `pytest tests/domain/` |
| 4.4 | Repository L1 | `app/db/documents.py`, `app/db/nodes.py` (Einfügen eines ganzen Teilbaums in einer Transaktion, Lesen als Baum) | Teilbaum atomar; Sichtbarkeit in SQL | `pytest -m pg tests/db/test_documents.py` |
| 4.5 | Lexikon laden | Migration `0010_lexicon.sql` (`terminology_profile`, `lexical_cue` mit allen Feldern aus konzept §12.1), `app/vocab/lexicon.py`, Erweiterung von `python -m app.vocab.load` | 1.267 Hinweise aus `profile/` (112/375/34/239/55/21/395/36); Muster kompilieren; zweiter Lauf unverändert; Stand an `vocab_release` | `pytest -m pg tests/vocab/test_lexicon.py` |
| 4.6 | Aktives Profil | `app/domain/lexicon.py` (`active_cues(cues, region, document_type, plan_generation)`) nach konzept §12.2 und §12.4 | spezifischer gewinnt; geprüft vor ungeprüft; Gleichstand → beide mit Regeltext; Homonym mit `alsoMapsTo` | `pytest tests/domain/test_lexicon.py` |

### Paket 5: Modellschicht und Abrechnung (4 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 5.1 | Aufrufschicht | `app/llm/calls.py` (aus `llm.py` der alten App: `StructuredDict` aus `ontology/schemas/`, `CachePoint` hinter dem Präfix, Zählung gesendeter Anfragen, Warten bei 429/5xx mit Retry-After), `app/llm/budget.py` (Kopie `budget.py`, tiktoken) | Mock-Transport: Haltepunkt sitzt hinter dem Präfix; Ausgabe gegen das Schema; Nutzung auch bei Fehlschlag lesbar; Schlüssel in keiner Logzeile | `pytest tests/llm/` |
| 5.2 | Rohantworten | `app/llm/raw.py` (Ablage `runs/<run>/<stufe>/<n>.json`) | Ablage vor der Auswertung; Wiederholung überschreibt nicht | `pytest tests/llm/test_raw.py` |
| 5.3 | Tabellen Abrechnung | Migration `0011_usage.sql` (`llm_usage`, `quota`, `usage_reservation`) | Zahlen nicht negativ; Reservierung hängt an Job und Konto | `pytest -m pg tests/db/test_usage_schema.py` |
| 5.4 | Reservieren und Buchen | `app/usage/ledger.py` (`reserve(conn, account, tokens)`, `book(conn, reservation, usage)`, `release_stale(conn)` mit `requeue_expired`) | zwei Worker, 40 Jobs, Grenze für genau 12 Aufrufe → genau 12 Aufrufe; abgestürzter Job gibt seine Reservierung frei; Buchung ersetzt Reservierung in einer Transaktion | `pytest -m pg tests/usage/test_ledger.py` (Stresslauf) |
| 5.5 | Prüfung beim Start | `app/usage/admission.py` (Start eines Modelljobs nur mit Restbudget; volle Spur → 429 mit Retry-After) | 403 ohne Budget, 429 bei voller Spur; Admin unbegrenzt nur mit `NULL`-Grenze | `pytest tests/api/test_admission.py` |
| 5.6 | API | `PUT /api/v1/accounts/{id}/quota` (Admin), `GET /api/v1/me/usage` | Wächter für neue Routen; Audit-Zeile | `pytest tests/api/test_usage_api.py` |

### Paket 6: X1 Dokumentprofil, Gerüst und X2 Segmente (6 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 6.1 | Präfix | `app/pipeline/prefix.py` (Blocktext mit IDs, Dokumentprofil, Auswahllisten; Kürzung für lange Dokumente nach §13.1) | Präfix byte-gleich über alle Aufrufe eines Dokuments; Kürzung behält Titelei, Verzeichnis, Rahmenteile, Abschnitt + Nachbarn | `pytest tests/pipeline/test_prefix.py` |
| 6.2 | X1 Dokumentprofil | `app/pipeline/x1_profile.py`, Prompt `app/pipeline/prompts/x1.py` | FunctionModel liefert `x1-dokumentprofil`; Dokument, Spezifikationen, `termMappings`, `newTerms` gespeichert; Dokumenttyp gegen das aktive Profil geprüft; Profilwert außerhalb → Befund statt Absturz | `pytest -m pg tests/pipeline/test_x1_profile.py` |
| 6.3 | Gerüst deterministisch | `app/pipeline/skeleton.py` (Überschriften aus Schrift/Layout/Verzeichnis; Muster mit Stärke ≥ 0,9 typisieren ohne Modell) | Beispiele: „Lernfeld 5: …" → Lernfeld; „Inhaltsfeld 3" in NW → Inhaltsfeld; Negativbeispiele der Hinweise treffen nicht | `pytest tests/pipeline/test_skeleton.py` |
| 6.4 | X1 Gliederung | `app/pipeline/x1_outline.py` (nur unklare Überschriften an das Modell, `x1-gliederung`) | nur unklare gehen raus; Funktion = Kernwert des Knotentyps | `pytest -m pg tests/pipeline/test_x1_outline.py` |
| 6.5 | X2 Segmente | `app/pipeline/x2_segments.py` (Einheiten mit Blockbereich; über ~15 Seiten an Unterknoten teilen; nie an Tokengrenzen) | Einheiten decken alle Inhaltsblöcke genau einmal; Teilung an Unterknoten | `pytest tests/pipeline/test_x2_segments.py` |
| 6.6 | Lauf-Rahmen | `app/pipeline/run.py` (Job `extract.run`, Stufen nacheinander, `extraction_run` je Stufe, Fortschrittscodes, Wiederaufnahme ab der letzten fertigen Stufe) | Abbruch zwischen Stufen; Wiederholung macht keine fertige Stufe doppelt; Budget erschöpft → Code `budget_exhausted`, Teilergebnis bleibt | `pytest -m pg tests/pipeline/test_run.py` |

### Paket 7: X3 Rahmenteile und X4 Aussagen (6 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 7.1 | X3 Rahmenteile | `app/pipeline/x3_frame.py`, Prompt `prompts/x3.py` | `x3-rahmenteile`: Kompetenz- und Niveaumodelle, Operatoren, Legende, Regeln, Rahmenaussagen gespeichert; einmal je Dokument | `pytest -m pg tests/pipeline/test_x3_frame.py` |
| 7.2 | X4 Auftrag | `app/pipeline/prompts/x4.py` (Einheit, Blockbereich, Titelpfad, aktiver Lexikonausschnitt nach §12.2) | Auftrag verschieden je Einheit, Präfix gleich; Lexikonausschnitt nur passende Geltung | `pytest tests/pipeline/test_x4_prompt.py` |
| 7.3 | X4 Aussagen | `app/pipeline/x4_statements.py` (parallel, höchstens `EXTRACT_CONCURRENCY` Aufrufe je Dokument) | Aussagen nur mit Block-IDs aus dem Bereich der Einheit; Werte aus dem Umfeld mit Herkunft `inherited`/`rule`, nicht als Wortlaut; Herkunft `model`, Prüfstand `proposed`; Einheit atomar gespeichert | `pytest -m pg tests/pipeline/test_x4_statements.py` |
| 7.4 | Anbindung Abrechnung | Reservierung vor jedem Aufruf (Paket 5) | Budgetende mitten in X4: fertige Einheiten bleiben, Rest offen, Lauf fortsetzbar | `pytest -m pg tests/pipeline/test_x4_budget.py` |
| 7.5 | Start über die API | `POST /api/v1/documents` (aus einer Konvertierung, Bereich, optional Land) → Dokument + Job `extract.run`; `GET /api/v1/documents/{id}/runs` | Konto und Budget nötig (401/403/429); fremde Konvertierung 404 | `pytest tests/api/test_documents.py` |
| 7.6 | Oberfläche Lauf | `views/DocumentView.vue` (Stufe, Fortschritt, Teilergebnis: fertige Einheiten erscheinen schon während des Laufs) | Zustände; `role="status"` nur bei Stufenwechsel | `vitest run`, Browser-Probe mit Mock-Modell |

### Paket 8: X5 Prüfung mit SHACL und X6 Reparatur (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 8.1 | Wortlaut gegen Blöcke | `app/pipeline/anchors.py` (Kopie `anchors.py` + `anchor_passage.py` der alten App mit Tests, auf Blöcke umgestellt) | Fundart exact/whitespace/elided/normalized/fuzzy/notFound gegen genau die genannten Blöcke; Schwellen wie in der alten App | `pytest tests/pipeline/test_anchors.py` |
| 8.2 | Plausibilität | `app/pipeline/x5_checks.py` (Überschrift als Aussage, Mindestinhalt, Aussageart passt zum Knotentyp, Pflichtfelder, Summen von Stunden/Anteilen) | je Regel ein Positiv- und ein Negativfall | `pytest tests/pipeline/test_x5_checks.py` |
| 8.3 | Kern-RDF je Dokument | `app/exports/kern_rdf.py` (Graph eines Dokuments nach `cur-kern.ttl`) | Beispiel `beispiele/ohm-kette` als Tabellen → RDF → isomorph zum Beispiel (soweit L1) | `pytest -m pg tests/exports/test_kern_rdf.py` |
| 8.4 | SHACL-Tor | `app/pipeline/shacl.py` (pyshacl wie `pruefe.py`: ohne Inferenz, Modell einmal je Prozess geladen; pyshacl wird Laufzeitabhängigkeit) | fehlerhaftes Beispiel liefert genau die erwarteten Verstöße; Laufzeit je Dokument gemessen | `pytest tests/pipeline/test_shacl.py` |
| 8.5 | Befunde | Migration `0012_findings.sql` (`validation_finding`: Lauf, Regel, Schwere, Fokus, Nachricht, Details), X5 als letzte Stufe von `extract.run` | Befunde als Zeilen; zweiter X5-Lauf ersetzt die Befunde desselben Laufs | `pytest -m pg tests/pipeline/test_x5.py` |
| 8.6 | X6 Reparatur | `app/pipeline/x6_repair.py`, Job `extract.repair` (nur Einheiten mit Befunden, 0–2 Aufrufe, Schema wie X4; Redaktionsänderungen bleiben unangetastet) | nur fehlerhafte Einheiten; bearbeitete Aussagen nie überschrieben; danach X5 erneut | `pytest -m pg tests/pipeline/test_x6_repair.py` |

### Paket 9: Editor, Redaktion und Festschreiben (8 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 9.1 | Formularschema | `app/vocab/forms.py`, `GET /api/v1/profiles/{bereich}/form` (Felder, Kardinalität aus `cur-shapes.ttl`, Wertelisten, Knotentypen und Unterarten des Profils mit Label, Definition, Beispielen) | Feldliste für Knoten und Aussage stimmt mit den Shapes; Werte nur aktiv | `pytest -m pg tests/api/test_forms.py` |
| 9.2 | Bearbeiten | `GET /api/v1/documents/{id}/tree`, `POST/PATCH/DELETE /api/v1/nodes/{id}`, `…/statements/{id}` mit `expected_revision` (409 bei Konflikt), Herkunft `human` bei Änderung | Revision steigt; 409 mit gespeichertem Stand; Schreibrechte Eigentümer/Redaktion | `pytest tests/api/test_editing.py` |
| 9.3 | Von Hand anlegen | `POST /api/v1/documents` ohne Konvertierung (Formular), Aussagen ohne Fundstelle nur mit Kennzeichnung | SHACL-Warnung „ohne Fundstelle" statt Abweisung | `pytest tests/api/test_manual_documents.py` |
| 9.4 | Prüfstand | `POST /api/v1/documents/{id}/review` (Bestätigen/Ablehnen einzeln und gesammelt, Rolle `redaktion`) | nur Redaktion; Zähler je Prüfstand | `pytest tests/api/test_review.py` |
| 9.5 | Festschreiben | Migration `0013_freeze.sql` (Trigger), `POST …/freeze`, `POST …/draft-copy` | Änderung an festgeschriebenen Daten scheitert in der Datenbank; Kopie mit neuen IDs, `supersedes`, Prüfstand übernommen | `pytest -m pg tests/db/test_freeze.py tests/api/test_freeze.py` |
| 9.6 | Baum | `components/TreeView.vue`, `TreeNodeItem.vue`, `treeRows.ts` (aus der alten App mit Tests, auf Knoten + Aussagen umgestellt), Filter nach Prüfstand | ARIA-Baum, Pfeiltasten, eine Tabstopp-Stelle; axe ohne Befund | `vitest run` |
| 9.7 | Formulare | `components/NodeForm.vue`, `StatementForm.vue` (aus dem Formularschema; Muster `ContextEditor` der alten App), `nodeConflict.ts` + `NodeConflict.vue` (Kopie) | Feld je Schema-Eintrag; Pflicht in Text, nicht nur Farbe; Fehler am Feld mit `aria-describedby`; Konfliktauswahl je Feld | `vitest run` |
| 9.8 | Quellenbeleg | `components/SourcePane.vue` (Blöcke der Seite neben dem Formular, genannte Blöcke markiert), `SourceQuote.vue` + `sourceAnchor.ts` (Kopie) | Fundart in Worten; Markierung nicht nur farbig | `vitest run` |
| 9.9 | Festschreiben in der Oberfläche | `FreezeDialog.vue`, `FrozenNotice.vue` (aus der alten App), Befunde je Knoten | Fokus auf „Abbrechen"; nach dem Festschreiben nur Lesen und „Als Entwurf kopieren" | `vitest run`, Browser-Probe |

### Paket 10: Lexikon aus der Länderrecherche mit Stichprobe (3 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 10.1 | Import T3/T2/T4/T5 | `app/lexicon/research_import.py`, Einstieg `python -m app.lexicon.import_research` (liest `ontology/recherche-ergebnisse/*.md`) | Stärke höchstens 0,7, „nicht geprüft", Herkunft `recherche` mit Beleg E/S/A; T2 → Überschriftenmuster mit Beispielen, T4 → `qz:`, T5 → `lvl:`; Korrekturen an Vorlisten-Hinweisen nur als Vorschlag | `pytest -m pg tests/lexicon/test_research_import.py` |
| 10.2 | Prüfbericht | `python -m app.lexicon.report` (Zeilen je Datei, verschobene Spalten, Werte außerhalb, unbekannte Ziele, Anteil E, Kollisionen in überlappender Geltung) | Bericht wie `pruefe_recherche.py`, Kollisionen wie `pruefe.py` | `pytest tests/lexicon/test_report.py` |
| 10.3 | Stichprobe | Migration `0014_cue_review.sql`, `app/lexicon/sample.py` (geschichtet je Bereich und Land, fester Seed), `GET/POST /api/v1/lexicon/review` (Redaktion: bestätigt mit Fundstelle → `verified`, Stärke bis 0,9; abgelehnt → aus dem aktiven Profil) | Stichprobe reproduzierbar; nur Redaktion; Hochstufung nur mit Fundstelle | `pytest -m pg tests/lexicon/test_sample.py` |
| 10.4 | Neue Begriffe aus X1 | `newTerms` landen in derselben Prüfliste („neuer Hinweis / Dokumentbesonderheit / Fehler") | Entscheidung „neuer Hinweis" legt einen ungeprüften Hinweis an | `pytest -m pg tests/lexicon/test_new_terms.py` |
| 10.5 | Oberfläche | `views/LexiconReviewView.vue` | Zustände, Tastatur, axe | `vitest run` |

### Paket 11: Abnahme M1 (2 PT)

1. Fünf amtliche PDFs mit Textebene, je Bereich eines; Titel, Adresse und Größe werden vorher
   genannt, geladen erst nach Zusage, abgelegt nur im lokalen Objektspeicher (nicht im Repo).
2. Kostenschätzung je Dokument aus Blockzahl, Einheiten und Präfixlänge (Token gezählt), Zusage
   des Nutzers, dann echte Läufe mit seinem Schlüssel aus der Umgebung.
3. Zwei Worker parallel, ein Konto mit knapper Grenze: Summe in `llm_usage` gleich der Summe
   der Nutzungsangaben in den Rohantworten; die Grenze wird nicht überschritten.
4. Bericht je Dokument: Knoten, Aussagen, Fundarten, Befunde nach Schwere, Laufzeit, Token,
   Kosten; Stichprobe von 20 Aussagen je Dokument gegen das Original.

## Abnahme M1

- Ein Lehrplan je Bereich (Schule, Elementar, Beruf, Hochschule, Erwachsenenbildung) läuft von
  der Quelle bis X5 durch; die Ergebnisse sind im Editor sichtbar, bearbeitbar, prüfbar und
  festschreibbar.
- X5-Befunde stehen als Zeilen in `validation_finding`; das SHACL-Tor nutzt die Shapes aus
  `ontology/` ohne Inferenz.
- Quote und Abrechnung stimmen unter parallelen Workern (Stresstest 5.4 und Abnahme 11.3).
- Saat: Kandidaten aus dem Vergleichsdatensatz und der Länderrecherche stehen im Register,
  der Prüfjob hat jede URL einmal abgerufen (nur nach Zusage, weil Dritte angefragt werden).
- Alle Tests aus M0 und M1 grün; ruff, mypy, vue-tsc, eslint ohne Befund.

## Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| pdfplumber erkennt Überschriften und Tabellen schlechter als Docling | Gerüst stützt sich auf Verzeichnis, Muster und Lexikon; Docling als Paket 3b nach Freigabe; Fixture-PDFs mit Tabellenmaßen |
| Modell liefert Profilwerte außerhalb des aktiven Profils | Prüfung nach dem Aufruf, Befund statt Absturz; X6 repariert |
| Kosten echter Läufe | Schätzung vor jedem Lauf, Reservierung je Aufruf, Abnahme nur nach Zusage |
| SHACL-Laufzeit je Dokument | Modellgraph einmal je Prozess; Laufzeit in 8.4 gemessen, notfalls nur Formen der L1-Klassen |
| Länderrecherche ungeprüft | Import nur als „nicht geprüft" mit Stärke ≤ 0,7; Hochstufung nur über die Stichprobe |
| Umfang | Pakete mit eigenem Review; 3b und spätere Engines getrennt |

## Offene Punkte

- Rechtestatus je Land: keine Recherche vorhanden; bis zur Lizenzprüfung gilt `unklar`
  (Gesamtplan §16, Frage 1).
- Download Docling/EasyOCR: eigene Freigabe (Paket 3b).
- Der Prüfjob für die Saat-URLs fragt Dritte an (rund 1.500 Adressen); er läuft erst nach
  Zusage des Nutzers.
