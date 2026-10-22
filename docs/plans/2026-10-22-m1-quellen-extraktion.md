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
| 2.4 | Länderrecherche T1 als zweite Saat | `app/sources/research_t1.py` mit einem Spaltenleser je Auftrag (Schule, Elementar, Beruf, Hochschule, EB) | `provenance` `laenderrecherche`, Beleg E/S übernommen; Quelltyp aus dem Host oder dem Vermerk an der ersten Adresse (bis zum nächsten „\|", ohne weitere Adresse darin): 5 Archiv, 5 Spiegel, 2 Sekundärquelle; Abgleich: URL nur in Saat, nur in Recherche, in beiden; Zählung: 668 Dokumente aus 684 Zeilen (6 durch ein Semikolon verschoben, 9 ohne Adresse, 1 ohne Titel), 593 Adressen; 34 weitere Adressen in den URL-Feldern der Einträge gezählt, nicht übernommen (`further_address`); Abgleich 1.210 nur Saat, 525 nur Recherche, 68 in beiden | `pytest -m pg tests/sources/test_research_t1.py` |
| 2.5 | Prüfjob | Job `source.check`: ein Abruf je URL (Status, Typ, Größe, SHA-256, Datum), Inhalt nur gestreamt und gehasht, nicht gespeichert; `host_throttle` hält den Abstand je Host über alle Worker (`CHECK_HOST_INTERVAL_S`, 2 s); robots.txt beachtet; eigener User-Agent (`FETCH_USER_AGENT`); Stand je URL sofort gespeichert, ein wiederholter Job überspringt Geprüftes | Mock-Transport: 200/404/403/429/Weiterleitung/Zeitüberschreitung ergeben die richtigen Status; 403/429 werden vermerkt, nicht umgangen (kein anderer User-Agent, kein automatischer Wechsel auf Archiv oder Spiegel); HTML-Seiten bekommen den Typ `html` (konvertierbar erst mit 3b) | `pytest -m pg tests/jobs/test_source_check.py` |
| 2.6 | Oberfläche | Filter „Kandidaten", Prüfstart (Admin), Zugangsnotiz je Eintrag | Zustände, Tastatur, axe | `vitest run` |

### Paket 3: Konvertierung X0 mit Block-IDs (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 3.1 | Engine-Schnittstelle | `app/conversion/base.py` (`Block(id, page, kind, text, bbox, font_size, bold, italic, cells)`, `Conversion(blocks, pages, printed_pages)`, Register), Kopie `text_layer.py`, `table_md.py` | Block-ID-Muster; Register nennt angebotene Engines | `pytest tests/conversion/test_base.py` |
| 3.2 | pdfplumber-Blöcke | `app/conversion/pdfplumber_blocks.py`, Abhängigkeiten `pdfplumber`, `pdfminer.six`, `pypdfium2` | Zeilen zu Blöcken nach Abstand und Schriftwechsel; fett/kursiv aus dem Schriftnamen; Tabellen als ein Block mit Zellen `T<n>:r<i>c<j>`; Tabellen über Seiten zusammengeführt (gleiche Spaltenzahl, keine Kopfzeile); Lesereihenfolge; Testdateien aus `backend/tools/_fixture_pdfs` der alten App | `pytest tests/conversion/test_pdfplumber_blocks.py` |
| 3.3 | Rand, Symbole, Kodierung | `app/conversion/page_edges.py` (aus `repeated_blocks.py`), `app/conversion/symbols.py`, `app/conversion/encoding.py` | Kopf-/Fußzeilen markiert statt gelöscht; gedruckte Seitenzahl erkannt; U+F0DA → ➔ und U+F0DE → ⇒ (konzept §13.2); jedes andere Zeichen der Private Use Area bleibt stehen und wird gezählt (Befund `unmapped_symbol` mit Codepunkt); Anteil kaputter Zeichen (Ersetzungszeichen, doppelt kodiertes UTF-8) über einer Schwelle → Befund `encoding_suspect` | `pytest tests/conversion/` |
| 3.4 | Kindprozess | `app/conversion/runners.py` (Kopie, ohne globale Settings; Schlüssel als Argument) | Frist und Abbruch beenden den Prozess; Lease-Verlust beendet ihn; Ergebnis als JSON zurück; Linux-Teile nur unter POSIX | `pytest tests/conversion/test_runners.py` |
| 3.5 | Tabellen und Job | Migration `conversion` (`conversion`, `document_block`, `conversion_usage`), Job `source.convert`, `MAX_PDF_PAGES` (800) | leere Ausgabe ist ein Fehler; Datei ohne Textebene → `needs_ocr`; Blöcke und Markdown gespeichert; `conversion_usage` je Lauf, eine Wiederholung bucht nicht doppelt; Metriken Konvertierung/Seiten | `pytest -m pg tests/jobs/test_source_convert.py` |
| 3.6 | API und Oberfläche | `POST /api/v1/source-files/{id}/conversions` (202), `GET /api/v1/conversions/{id}`, `GET …/blocks?page=` (Sichtbarkeit nach `THIRD_PARTY_MARKDOWN`); `views/ConversionView.vue`, `refusals.ts` für `needs_ocr` | Fortschritt, Fehler mit Grund, Seiten per Tastatur; axe ohne Befund | `pytest tests/api/test_conversions.py`, `vitest run` |

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

### Paket 6: X1 Dokumentprofil, Gerüst und X2 Segmente (6 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 6.1 | Präfix | `app/pipeline/prefix.py` (Blocktext mit IDs, Dokumentprofil, Auswahllisten; Kürzung nach §13.1) | Präfix byte-gleich über alle X4-/X6-Aufrufe eines Dokuments; Kürzung behält Titelei, Verzeichnis, Rahmenteile, Abschnitt + Nachbarn | `pytest tests/pipeline/test_prefix.py` |
| 6.2 | X1 Dokumentprofil | `app/pipeline/x1_profile.py`, Prompt `app/pipeline/prompts/x1.py` | FunctionModel liefert `x1-dokumentprofil`; Dokument, Spezifikationen, Varianten, `document_profile` gespeichert; Werkvorschlag ohne Setzen; Profilwert außerhalb → `validation_finding` statt Absturz | `pytest -m pg tests/pipeline/test_x1_profile.py` |
| 6.3 | Gerüst deterministisch | `app/pipeline/skeleton.py` (Überschriften aus Schrift/Layout/Verzeichnis; Muster mit Stärke ≥ 0,9 typisieren ohne Modell, über `asyncio.to_thread`) | „Lernfeld 5: …" → Lernfeld; „Inhaltsfeld 3" in NW → Inhaltsfeld; Negativbeispiele der Hinweise treffen nicht | `pytest tests/pipeline/test_skeleton.py` |
| 6.4 | X1 Gliederung | `app/pipeline/x1_outline.py` (nur unklare Überschriften an das Modell, `x1-gliederung`) | nur unklare gehen raus; Funktion = Kernwert des Knotentyps | `pytest -m pg tests/pipeline/test_x1_outline.py` |
| 6.5 | X2 Segmente | `app/pipeline/x2_segments.py` (Einheiten mit Blockbereich; über ~15 Seiten an Unterknoten teilen; Extraktionstiefe skip/typed/full) | Einheiten decken alle Inhaltsblöcke genau einmal; `skip` erzeugt keinen Auftrag, `typed` keinen Aussagen-Auftrag | `pytest tests/pipeline/test_x2_segments.py` |
| 6.6 | Lauf-Rahmen | `app/pipeline/run.py` (Job `extract.run`, Stufen nacheinander, `extraction_run` je Stufe, Fortschrittscodes, Wiederaufnahme ab der letzten fertigen Stufe), Wächter Fortschrittscodes ↔ Frontend | Abbruch zwischen Stufen; keine fertige Stufe doppelt; Budget erschöpft → `budget_exhausted`, Teilergebnis bleibt | `pytest -m pg tests/pipeline/test_run.py` |

### Paket 7: X3 Rahmenteile und X4 Aussagen (6 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 7.1 | X3 Rahmenteile | `app/pipeline/x3_frame.py`, Prompt `prompts/x3.py` | `x3-rahmenteile` in `frame_part` (Modelle, Operatoren, Legende, Regeln) und Rahmenaussagen als Aussagen an einem Rahmenknoten; einmal je Dokument | `pytest -m pg tests/pipeline/test_x3_frame.py` |
| 7.2 | X4 Auftrag | `app/pipeline/prompts/x4.py` (Einheit, Blockbereich, Titelpfad, aktiver Lexikonausschnitt nach §12.2) | Auftrag verschieden je Einheit, Präfix gleich; nur passende Geltung im Ausschnitt | `pytest tests/pipeline/test_x4_prompt.py` |
| 7.3 | X4 Aussagen | `app/pipeline/x4_statements.py` (parallel, höchstens `EXTRACT_CONCURRENCY` Aufrufe je Dokument) | nur Block-IDs aus dem Bereich der Einheit; Werte aus dem Umfeld mit Herkunft `inherited`/`rule`, nicht als Wortlaut; Herkunft `model`, Prüfstand `proposed`; Einheit atomar | `pytest -m pg tests/pipeline/test_x4_statements.py` |
| 7.4 | Anbindung Abrechnung | Reservierung vor jedem Versuch (Paket 5) | Budgetende mitten in X4: fertige Einheiten bleiben, Rest offen, Lauf fortsetzbar | `pytest -m pg tests/pipeline/test_x4_budget.py` |
| 7.5 | Start über die API | `POST /api/v1/documents` (aus einer Konvertierung, Bereich, Land) → 202 mit Dokument und Job; `GET /api/v1/documents/{id}/runs` | Konto, Budget, Rate-Limit (401/403/429); fremde Konvertierung 404 | `pytest tests/api/test_documents.py` |
| 7.6 | Oberfläche Lauf | `views/DocumentView.vue` (Stufe, Fortschritt, fertige Einheiten schon während des Laufs), `refusals.ts` für `budget_exhausted` | Zustände; `role="status"` nur bei Stufenwechsel; axe ohne Befund | `vitest run`, Browser-Probe mit Mock-Modell |

### Paket 8: X5 Prüfung mit SHACL und X6 Reparatur (5 PT)

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| 8.1 | Wortlaut gegen Blöcke | `app/pipeline/anchors.py` + `anchor_passage.py` (aus der alten App, geteilt, auf Blöcke umgestellt, über `asyncio.to_thread`) | Fundart exact/whitespace/elided/normalized/fuzzy/notFound gegen genau die genannten Blöcke; Schwellen wie in der alten App | `pytest tests/pipeline/test_anchors.py` |
| 8.2 | Plausibilität | `app/pipeline/x5_checks.py` (Überschrift als Aussage, Mindestinhalt, Aussageart passt zum Knotentyp, Pflichtfelder, Summen von Stunden/Anteilen) | je Regel ein Positiv- und ein Negativfall | `pytest tests/pipeline/test_x5_checks.py` |
| 8.3 | Kern-RDF je Dokument | `app/exports/kern_rdf.py` (Dokument, Spezifikation, Knoten, Aussage, Fundstelle mit den Eigenschaften aus 4.2–4.4) | ein L1-Testdokument aus den Tabellen ergibt genau die erwarteten Tripel; Namensraum-Bindungen gesetzt | `pytest -m pg tests/exports/test_kern_rdf.py` |
| 8.4 | SHACL-Tor | `app/pipeline/shacl.py` (pyshacl wie `pruefe.py`, ohne Inferenz, in einem Prozess-Pool; pyshacl wird Laufzeitabhängigkeit) | fehlerhaftes Beispiel liefert die erwarteten Verstöße; Messung der Varianten (ganzes Modell 20–23 s je Beispiel gemessen; Fokusknoten des Dokuments; Teilmodell aus Kern und Bereichsprofil) und Wahl der schnellsten mit gleichen Befunden; Zeitgrenze `SHACL_TIMEOUT_S` | `pytest tests/pipeline/test_shacl.py`, Laufzeit < 5 s je Testdokument |
| 8.5 | X5 als Stufe | letzte Stufe von `extract.run` | Befunde als Zeilen; ein zweiter X5-Lauf ersetzt die Befunde desselben Laufs | `pytest -m pg tests/pipeline/test_x5.py` |
| 8.6 | X6 Reparatur | `app/pipeline/x6_repair.py`, Job `extract.repair` (nur Einheiten mit Befunden, 0–2 Aufrufe, Schema wie X4; Redaktionsänderungen unangetastet) | nur fehlerhafte Einheiten; bearbeitete Aussagen nie überschrieben; danach X5 erneut | `pytest -m pg tests/pipeline/test_x6_repair.py` |

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
