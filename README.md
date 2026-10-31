# Kompetenzkartierer-AI

Lehrpläne aller Bildungsbereiche nach Curriculum-Kern 1.0 erfassen (Extraktion oder Formular),
an Kompetenz-, Niveau- und Normdatenschemata andocken, Kanten bilden und daraus die
Anwendungsfälle einer Wissenslandkarte bedienen. Zustandslos und clusterfähig.

- Plan: [`docs/plans/2026-10-21-gesamtplan.md`](docs/plans/2026-10-21-gesamtplan.md),
  aktueller Meilenstein [`docs/plans/2026-10-22-m0-fundament.md`](docs/plans/2026-10-22-m0-fundament.md)
- Ontologie (Kern 1.0, Profile, Vokabulare, Prüfregeln): [`ontology/`](ontology/)

## Entwicklung

Backend (Python 3.13, uv):

```bash
cd backend
uv sync --frozen
.venv/Scripts/python.exe -m pytest
```

`uv.lock` legt alle Versionen für jede Plattform fest, mit Prüfsummen. Wer eine Abhängigkeit
ändert, sperrt neu (`uv lock`) und schreibt den Export für das Image neu:
`uv export --frozen --no-dev --format requirements-txt -o ../deploy/requirements-api.txt`
(ein Test vergleicht beide).

Datenbank-Tests (Marker `pg`) brauchen einen PostgreSQL-Server nur für Tests, etwa diesen
Container (Daten nur im Arbeitsspeicher, Port nur lokal):

```bash
docker run -d --name kka-test-pg -e POSTGRES_USER=kka -e POSTGRES_PASSWORD=kka-test -e POSTGRES_DB=kka -p 127.0.0.1:55432:5432 --tmpfs /var/lib/postgresql/data pgvector/pgvector:pg17
```

Dann legt jeder Test eine eigene Datenbank an und entfernt sie wieder:

```bash
KKA_TEST_DATABASE_URL=postgresql://kka:kka-test@127.0.0.1:55432/kka .venv/Scripts/python.exe -m pytest
```

Ohne `KKA_TEST_DATABASE_URL` werden die Datenbank-Tests übersprungen; mit `KKA_REQUIRE_PG=1`
(oder in CI) scheitern sie stattdessen.

Die S3-Tests (Marker `s3`) laufen gegen einen MinIO-Container nur für Tests (Chainguard-Build,
weil MinIO seit Oktober 2025 keine Community-Images mehr veröffentlicht; Zugangsdaten erfunden,
Daten nur im Arbeitsspeicher). Unter Git Bash vorher `export MSYS_NO_PATHCONV=1`, sonst werden
`/data` und `server /data` zu Windows-Pfaden:

```bash
docker run -d --name kka-test-minio -e MINIO_ROOT_USER=kka-test -e MINIO_ROOT_PASSWORD=kka-test-secret -p 127.0.0.1:59000:9000 --tmpfs /data:rw,uid=65532,gid=65532 cgr.dev/chainguard/minio@sha256:fe57367a6bfc78779367b86ad0cdd3d5df32965b7cb3c000c94032f138627c41 server /data
KKA_TEST_S3_URL=http://127.0.0.1:59000 KKA_TEST_S3_ACCESS_KEY=kka-test KKA_TEST_S3_SECRET_KEY=kka-test-secret .venv/Scripts/python.exe -m pytest -m s3
```

Ohne `KKA_TEST_S3_URL` werden sie übersprungen; mit `KKA_REQUIRE_S3=1` (oder in CI) scheitern sie.

Frontend (Vite, Vue 3, TypeScript; Node 22.22 oder 24.15 und neuer):

```bash
cd frontend
npm ci
npm run dev
```

`npm run dev` dient unter `http://localhost:5173` und reicht `/api` an das Backend auf Port
8000 weiter. `npm test` startet die Tests, `npm run lint` ESLint, `npm run build` prüft die
Typen und baut nach `dist/`, mit den Lizenzen der Schriften und Bibliotheken in
`dist/licenses.txt`.

## Betrieb

`python -m app.db.migrate` wendet die Migrationen an (einmal je Release, nie aus API
oder Worker), `python -m app.vocab.load` lädt die Vokabulare und das Lexikon (die
Terminologieprofile der Bereiche mit ihren Erkennungshinweisen, auch aus Unterordnern wie
`profile/laender/`) aus `ONTOLOGY_DIR` (Standard: `ontology/` dieses Repositorys), `python -m app.serve` startet die API auf `PUBLIC_PORT` und
`INTERNAL_PORT` (`/health`, `/ready`, `/metrics`), `python -m app.jobs.worker` den Worker
(`WORKER_KINDS` beschränkt ihn auf Job-Arten, kommagetrennt). Beide starten nur mit einem
nutzbaren Objektspeicher (lokal etwa `STORAGE_DIR=../data/store`). Der Worker bedient
`/health` und `/metrics` ebenfalls auf `INTERNAL_PORT`; im Cluster hat jeder Pod seinen eigenen.
Läuft ein Worker neben der API auf demselben Rechner, braucht er ein eigenes `INTERNAL_PORT`
(etwa `INTERNAL_PORT=9001`): Sonst startet der zweite Prozess nicht, oder beide teilen sich den
Port still (Windows).

Anmeldung: Es gibt nur API-Tokens (`kka_…`), die ein Admin ausgibt; die Datenbank hält ihren
HMAC unter `API_KEY_PEPPER` (Geheimnis, mindestens 32 Zeichen, auch als Datei über
`API_KEY_PEPPER_FILE`). Ohne Pepper startet die API nicht; ein neuer Pepper macht alle Tokens
ungültig.

- Saat des Quellregisters: `python -m app.sources.seed` legt die 1.498 Kandidaten des
  Vergleichsdatensatzes an (`data/seed/vergleichsdatensatz/`, auch im API-Image), ohne Konto
  und ungeprüft, dazu 353 Zugangsnotizen zu gesperrten Portalen und Umwegen (je Land, Schulform
  und Fach; eine Notiz ohne Fach gilt für alle Fächer; die Einzelansicht eines Eintrags nennt
  sie). Ein zweiter Lauf ändert nichts. Vorher muss das Vokabular geladen sein. In Compose:
  `docker compose -f deploy/docker-compose.yml run --rm migrate python -m app.sources.seed`.
- Zweite Saat aus der eigenen Länderrecherche: `python -m app.sources.research_t1` legt die
  668 Dokumente der T1-Tabellen an (`ontology/recherche-ergebnisse/`, auch im API-Image), mit
  Bildungsbereich je Auftrag, Beleg E/S und gekennzeichneten Archiv-, Spiegel- und
  Sekundärquellen (nach Host oder Vermerk; ein Vermerk gilt für jeden Eintrag derselben
  Adresse). Danach meldet der Befehl, wie viele Adressen nur der Vergleichsdatensatz
  kennt, nur die Recherche oder beide. Ein zweiter Lauf ändert nichts. Vorher muss das
  Vokabular geladen sein (alle fünf Bildungsbereiche, sonst Exit-Code 1). In Compose:
  `docker compose -f deploy/docker-compose.yml run --rm migrate python -m app.sources.research_t1`.
- Prüfung der Saat: `POST /api/v1/sources/checks` (nur Admin) startet den Job `source.check`.
  Er fragt jede Adresse der Einträge ohne Konto und ohne Datei einmal ab – nach beiden Saaten
  rund 1.800 Adressen auf über 140 Hosts – und streamt und hasht den Inhalt, ohne ihn zu
  speichern. Jede Adresse, auch jedes Weiterleitungsziel, prüft er zuerst gegen die robots.txt
  ihres Hosts und fragt jeden Host höchstens alle `CHECK_HOST_INTERVAL_S` Sekunden, über alle
  Worker. Nichts wird umgangen: kein anderer User-Agent, kein Archiv oder Spiegel statt der
  Adresse. Ausgänge und Registerstand: 2xx erreichbar; 4xx (auch 403), 5xx, keine Antwort, die
  es geben kann, und ein Verbot laut robots.txt nicht erreichbar; 429 und 503 („später“)
  lassen den Eintrag ungeprüft und halten den Host für die verlangte Zeit (`Retry-After`,
  höchstens ein Tag) zurück; 502, 504, Zeitüberschreitung und Verbindungsabbruch gelten als
  vorübergehend nicht erreichbar. Diese beiden fragt eine spätere Prüfung erneut, und der Host
  wartet bis dahin: seine übrigen Adressen und jede Weiterleitung zu ihm. Ebenso wartet ein
  Host, dessen Name gerade nicht aufgelöst wird oder dessen robots.txt gerade nicht zu haben
  ist; seine Adressen bleiben ungeprüft. Ein Weiterleitungsziel über 2.000 Zeichen wird nicht
  gefragt; die Adresse, die dorthin führt, gilt als nicht erreichbar (endgültig, ohne Status).
  Ein neuer Start prüft nur, was noch offen ist; ein
  Kandidat, der später mit einer schon geprüften Adresse dazukommt, übernimmt deren Ergebnis.
  Ein zweiter Start, solange einer wartet oder läuft, gibt 409 `check_running` mit der Job-ID.
  Der Lauf dauert Stunden (allein ein Host trägt 400 Adressen) und belegt einen Worker; dafür
  einen eigenen Worker mit `WORKER_KINDS=source.check` vorsehen.
- Konvertierung (X0): `POST /api/v1/sources/{id}/conversions` startet für die Datei eines
  Eintrags den Job `source.convert` (202) oder gibt die vorhandene Konvertierung zurück (200,
  eine gescheiterte startet neu). `GET …/conversion` nennt Stand, Seiten, gedruckte Seiten und
  Befunde, `GET …/conversion/blocks?page=N` die Blöcke einer Seite (`p<Seite>-b<Block>`,
  Tabellenzellen `T<n>:r<i>c<j>`). Wer die Datei eines Eintrags lesen darf (Eigentümer,
  Redaktion, Admin; Einträge ohne Konto nach `THIRD_PARTY_MARKDOWN`), darf sie umwandeln lassen
  und die Blöcke lesen. Die Konvertierung gehört zur Datei (gleiche SHA-256), nicht zum Eintrag:
  Ein Konto, das dieselbe Datei hochlädt, findet die vorhandene und erfährt so, dass die Datei
  schon hier war – der Preis dafür, jede Datei nur einmal umzuwandeln. Die Job-ID nennt die
  Antwort nur dem Konto, das den Job gestartet hat, und Admins. Bisher nur PDFs mit Textebene
  (pdfplumber): ein Scan endet mit `needs_ocr` (OCR folgt mit Docling), mehr als
  `MAX_PDF_PAGES` (800) Seiten mit `too_many_pages`, eine Seite mit mehr als 100.000 Zeichen
  mit `too_dense`, länger als `CONVERT_TIMEOUT_S` (900 s) mit `timed_out`. Die Umwandlung läuft
  in einem eigenen Kindprozess, den Abbruch, Frist und Lease-Verlust beenden; dafür eigene
  Worker mit `WORKER_KINDS=source.convert` vorsehen, ein Job je Pod.
- Formular: `GET /api/v1/profiles/{bereich}/form` (jedes Konto; `bereich` wie `school`) nennt die
  Felder eines Knotens und einer Aussage mit Art, Pflicht, Mehrfachwert und Höchstlänge und je
  Auswahlliste die aktiven Werte des Profils, nach Label geordnet – Knotentypen und Unterarten mit
  Label, weiteren Namen, Definition, Anmerkung, Abgrenzung und Beispielen; kein aktives Profil: 404
  `unknown_sector`. Die Felder sind nicht laxer als die SHACL-Formen des Kerns (Test).
- Dokumente: `POST /api/v1/documents` (`source_id`, `conversion_id`, `sector`, `regions`) legt aus der
  fertigen Umwandlung eines Eintrags ein Dokument an und startet seine Extraktion (202 mit Dokument und
  Job), als Modelljob zugelassen (403 `no_budget`, 429 `too_many_jobs` / `too_many_starts`). `POST
  /api/v1/documents/{id}/extraction` startet sie neu, nur durch den Eigentümer (403 `not_owner`) und solange
  er den Inhalt des Eintrags lesen darf (403 `file_hidden`), nicht für ein festgeschriebenes Dokument (409
  `frozen`) und keine Entwurfskopie (409 `not_extractable`; wie die Reparatur); `GET
  /api/v1/documents?source_id=…`, `/documents/{id}`, `/documents/{id}/runs`, `/documents/{id}/units`,
  `/documents/{id}/findings` lesen sie (`units` und `findings` nur, wer auch den Inhalt des Eintrags lesen
  darf, sonst 403 `file_hidden` – ihre Pfade und Befunde nennen Titel und Wortlaut; jedes Dokument mit `issuer`, `edition`, `work` – Id, Titel, Land,
  Kurztitel, IRI –, `iri`, `revision`, `frozen_at` und `copy_of`, der Revision, die eine Entwurfskopie
  kopiert; die Job-ID nur für Eigentümer und Admins, den Fehlercode des letzten Jobs,
  `extraction.error_code`, alle Leser; `units`: die Arbeitspakete mit Stand `done` samt Zahl der Aussagen,
  `open`, `frame` oder `none`, vor X2 leer; `findings`: die Befunde der Stufen, Verstöße zuerst, je mit Art,
  Wortlaut oder Titel der Zeile, die sie betreffen (gekürzt mit „…“), dem Arbeitspaket, das sie nennen, und
  der Sprache der Meldung, wo die Stufe sie kennt (`message_lang`: „de“ für die deutschen Meldungen der
  SHACL-Formen, sonst Englisch) – höchstens 500, die Zahlen je Schwere über alle). Je Dokument wartet oder
  läuft höchstens ein Extraktionsjob (`job.unique_key`, Migration 0018): ein Start dabei gibt den laufenden
  zurück (200); ebenso ein neues Dokument desselben Eintrags und derselben Konvertierung, solange eines des
  Kontos daraus extrahiert wird – dann 200 mit diesem (`made: false`).
- Reparatur: `POST /api/v1/documents/{id}/repair` startet den Job `extract.repair` (X6, dann X5
  erneut) – nur durch den Eigentümer und solange er den Inhalt lesen darf, wie ein Neustart,
  sobald X5 das Dokument geprüft hat (409 `not_checked`) und Befunde eines Arbeitspakets eine
  Reparatur verlangen (409 `nothing_to_repair`), zugelassen als Modelljob. Er teilt den
  Schlüssel der Extraktion: Ein Start, während eine Extraktion oder Reparatur wartet oder läuft,
  gibt diese zurück (200), in beide Richtungen. `findings` nennt dem Eigentümer nach X5 in
  `repairable` die Pakete, die eine Reparatur fragen würde; `extraction.kind` sagt jedem Leser,
  welcher Art der letzte Job ist.
- Baum: `GET /api/v1/documents/{id}/tree` liest die Knoten und Aussagen eines Dokuments, wie der Editor sie
  zeigt (wer das Dokument lesen darf, in einem Snapshot): je Zeile die Felder des Formulars unter dessen
  Schlüsseln, Herkunft, Prüfstand, Revision, `iri` (sobald das Dokument festgeschrieben wurde, sonst `null`;
  in einer Entwurfskopie tragen die übernommenen Zeilen ihre schon, neue erst nach dem Festschreiben) und
  Fundstellen (Seiten, gedruckte Seite, Zitat, Fundart, Wert, Blöcke in Dokumentreihenfolge), je Aussage
  `by_hand` (von Hand angelegt: `DELETE` löscht sie; aus einem Lauf: sie wird verworfen), je Knoten die
  Zahl der Befunde je Schwere an ihm, seinen Fundstellen, seinen Aussagen und deren Fundstellen (nicht an
  seinen Kindern), dazu die Zahl der Knoten und Aussagen je Prüfstand. `editable`: Eigentümer und
  Redaktion/Admin dürfen jetzt bearbeiten, `reviewable`: Redaktion/Admin dürfen den Prüfstand setzen –
  beides nicht, solange ein Job des Dokuments wartet oder läuft, nicht, bevor X4 jedes Arbeitspaket gelesen
  hat (eine Entwurfskopie gilt als gelesen), und nicht, sobald es festgeschrieben ist; `closed` nennt dann den
  Grund für alle Leser (`frozen` vor `job_open` vor `not_extracted`, sonst `null`). Lesen darf den Baum, wer
  das Dokument lesen darf (sonst 404 `no_document`) und den Inhalt des Eintrags (sonst 403 `file_hidden`):
  die Aussagen sind dieser Inhalt in den Worten des Dokuments. In der Oberfläche
  zeigt die Seite „Baum“ des Dokuments (`/dokumente/{id}/baum`, verlinkt von der Dokumentseite) den Baum mit
  Filter nach Prüfstand, daneben die gewählte Zeile mit Feldern und Fundstellen und unter ihr die Seite der
  Quelle mit den genannten Blöcken als „Beleg“; Zeile und Seite stehen in der Adresse (`?zeile=…&seite=…`).
  Ist der Baum offen (`editable`), steht die gewählte Zeile im Formular ihres Bildungsbereichs: Speichern
  sendet nur geänderte Felder mit der gelesenen Revision und liest den Baum neu; hat inzwischen jemand die
  Zeile geändert, übernimmt es dessen Felder und legt die von beiden geänderten zur Wahl vor („Meins
  behalten“ / „Gespeichertes nehmen“); ein Fehler steht am Feld; schließt sich der Baum (Job, festgeschrieben,
  X4) beim Speichern oder beim Neulesen, bleibt der Entwurf zum Abschreiben stehen. Sonst sagt die Seite,
  warum sie nur liest. Ein ungespeicherter Entwurf fragt nach, bevor eine andere Zeile oder eine andere Seite
  der App ihn verdrängt (eine andere Seite der Quelle nicht); der Browser fragt vor dem Schließen. Bei einer
  Aussage im offenen Baum sind die Blöcke der gezeigten Quellenseite Schalter: „Gewählte Blöcke als Fundstelle
  übernehmen“ legt sie als eine Fundstelle in den Entwurf, „Seite N als ‚nicht gefunden‘ übernehmen“ die
  Seite; der Entwurf listet seine Fundstellen mit „Entfernen“, und Speichern sendet sie – alle – nur, wenn
  sie sich geändert haben. Ein gewählter Knoten bietet „Unterknoten anlegen“ und „Aussage anlegen“, der Baum
  „Knoten anlegen“ (oberste Ebene); eine neue Aussage braucht eine Fundstelle; ein offener Entwurf fragt vorher
  nach; angelegt, wird der Baum neu gelesen und die neue Zeile gewählt. „Löschen“ (Knoten, mit Zahl der
  Unterknoten und Aussagen; eine von Hand angelegte Aussage, mit ihren Fundstellen) und „Verwerfen“ (die
  Aussage eines Laufs, die verworfen im Baum bleibt; einer schon verworfenen bietet die Seite es nicht mehr an)
  fragen vorher nach. Die Redaktion setzt in der gewählten Zeile ihren „Prüfstand“ („Vorgeschlagen“,
  „Bestätigt“, „Verworfen“, der gesetzte gedrückt); danach wird der Baum neu gelesen, eine inzwischen
  geänderte Zeile gesagt. „Erneut prüfen“ neben „Knoten anlegen“ startet die Prüfung (X5) und folgt ihr bis
  zum Ende; folgen dürfen ihr Eigentümer und Admins – die übrige Redaktion liest den Baum neu, wenn sie fertig
  ist.
- Blöcke des Dokuments: `GET /api/v1/documents/{id}/blocks?page=N` liest eine Seite der Konvertierung, aus
  der das Dokument gelesen wurde (Blöcke, fortlaufende Tabellen, gedruckte Seite, `pages`) – die Blöcke, die
  seine Fundstellen nennen, auch wenn die Datei des Eintrags seither neu geholt oder anders umgewandelt
  wurde. Lesen darf sie, wer das Dokument lesen darf (sonst 404 `no_document`) und den Inhalt des Eintrags
  (sonst 403 `file_hidden`); hinter der letzten Seite 404 `no_such_page`.
- Bearbeiten: `PATCH /api/v1/nodes/{id}` und `/statements/{id}` (`expected_revision`, `fields` unter
  den Schlüsseln des Formulars, ausgelassene bleiben; eine Aussage auch `anchors`, alle auf einmal:
  Blöcke der Konvertierung, die Seiten folgen aus ihnen, oder nur `page`, eine Seite der
  Konvertierung, wo kein Block sie hält),
  `POST /api/v1/documents/{id}/nodes` (`parent_id`, ans Ende der Geschwister) und
  `/nodes/{id}/statements` (ans Ende des Knotens, mindestens eine Fundstelle, sonst 422
  `anchor_missing`), `DELETE /api/v1/nodes/{id}` (samt Unterbaum und den Befunden darauf) und
  `/statements/{id}` (je `?expected_revision=`; die Aussage eines Laufs wird verworfen und bleibt,
  damit keine Reparatur sie neu vorschlägt, eine von Hand geschriebene gelöscht; die Antwort nennt
  `outcome` – `rejected` oder `deleted` – und die Revision danach, `null` nach dem Löschen) – durch
  Eigentümer und Redaktion/Admin. Eine Änderung macht die Zeile zum Vorschlag der Redaktion
  (`orig_human`, `rev_proposed`, Revision +1), ein neuer Titel oder Wortlaut lässt die Fundstellen mit Blöcken für
  X5 wieder ungeprüft, eine Änderung ohne geänderten Wert lässt die Zeile stehen; die Antwort ist die
  Zeile wie im Baum. Abgewiesen: 409 `stale_revision` (mit `details.current`, der Zeile, wie sie
  steht), `job_open` (solange ein Job des Dokuments wartet oder läuft; die Job-ID für Eigentümer und
  Admins), `not_extracted` (X4 hat noch nicht jedes Arbeitspaket gelesen: erst fortsetzen), `frozen`,
  `no_form`; 422 `invalid_field` (`details.field`, `details.problem`); 403 `file_hidden`, sobald der
  Inhalt des Eintrags nicht mehr der des Eigentümers ist – vor jeder anderen Prüfung, sodass auch eine
  veraltete Revision keine Zeile mehr zeigt (ebenso `GET …/findings`, deren Befunde Wortlaut und Titel
  nennen). Jede
  Änderung steht im Audit (`node.edit`, `node.add`, `node.drop`, `statement.edit`, `statement.add`,
  `statement.reject`, `statement.delete`).
- Prüfstand: `POST /api/v1/documents/{id}/review` (`status`: `proposed`, `confirmed` oder
  `rejected`; `items`: je `kind` – `node` oder `statement` –, `id` und gelesene `revision`, 1 bis
  2.000) setzt den Prüfstand vieler Zeilen auf einmal, nur durch Redaktion/Admin (sonst 403
  `not_editor`): alles oder nichts – steht eine Zeile anders oder nicht mehr da, 409 `stale_revision`
  mit `details.stale` (je Zeile `current`, die Revision jetzt oder `null`). Die Herkunft bleibt, die
  Revision zählt eins hoch, eine Zeile mit diesem Prüfstand bleibt, wie sie ist; die Antwort nennt die
  Revisionen danach. Eine Aussage zu oder von „verworfen“ ändert, was der Lehrplan sagt (Export und X5
  lassen verworfene aus) und schuldet X5 eine Prüfung; ein Knoten verworfen bleibt in beiden. Wie beim
  Bearbeiten nicht neben einem offenen Job, nicht vor X4 und nicht festgeschrieben; Audit `review.set`.
- Erneut prüfen: `POST /api/v1/documents/{id}/check` startet den Job `extract.check` (X5 erneut, ohne
  Modell) – durch Eigentümer und Redaktion/Admin, sobald X5 das Dokument einmal geprüft hat (sonst 409
  `not_checked`: die Extraktion fortsetzen) – eine Entwurfskopie sofort, sie bringt keine Läufe ihrer
  Vorlage mit –, nicht, sobald es festgeschrieben ist (409 `frozen`), und wie Extraktion und Reparatur nur,
  wer den Inhalt des Eintrags lesen darf (403 `file_hidden`). Kein Modelljob: weder Budget noch
  Startgrenzen lassen ihn zu. Er läuft in der Spur des Eigentümers wie jeder Job des Dokuments: folgen (`GET
  /api/v1/jobs/{id}`) und abbrechen dürfen Eigentümer und Admins, wer ihn startete, sieht ihn in der Antwort
  (202). Er teilt den Schlüssel der Extraktion; wartet oder läuft ein Job des Dokuments, kommt dieser zurück
  (200), wo der Aufrufer ihm folgen darf (Eigentümer, Admin), sonst 409 `job_open`. Audit `check.start`.
  Geschuldet ist die Prüfung, sobald eine Reparatur oder eine Bearbeitung (`document.edited_at`) nach dem
  Start des letzten fertigen X5 begann.
- Werk: `PATCH /api/v1/documents/{id}/work` setzt das Werk des Dokuments – ein vorhandenes (`work_id`) oder
  ein neues (`title`, `region` wie `DE-NW`, `short_title` als Slug wie `lp-physik`) –, nur durch
  Redaktion/Admin (sonst 403 `not_editor`); 404 `no_work` für ein Werk, das es nicht gibt. Metadaten: `PATCH
  /api/v1/documents/{id}` setzt `issuer`, `edition` und `title` (ausgelassene bleiben, `null` oder leerer
  Text leert) – durch Eigentümer und Redaktion/Admin, 422 `invalid_field` wie beim Bearbeiten; eine Änderung
  schuldet X5 eine Prüfung; erst wenn X4 fertig ist, wie jede Bearbeitung des Baums (409 `not_extracted`;
  vor X1 überschriebe eine Extraktion sie mit dem, was X1 liest), ein neues Werk mit speicherbarem Titel und
  einem Land des Regionenvokabulars (422 `invalid_field`). Beide nicht neben einem offenen Job und nicht
  festgeschrieben; hat das Dokument schon seine IRI (festgeschrieben oder Entwurfskopie), bleiben Werk,
  Herausgeber und Fassung, aus denen sie besteht (409 `named`). Audit `document.work` bzw. `document.edit`;
  die Antwort ist das Dokument.
- Festschreiben: `POST /api/v1/documents/{id}/freeze` (`accept_violations`, Standard `false`), nur
  Redaktion/Admin. Abgewiesen, der Reihe nach: festgeschrieben (409 `frozen`), offener Job (`job_open`), X4
  nicht fertig und keine Entwurfskopie (`not_extracted`), es fehlt Werk, dessen Land oder Kurztitel,
  Herausgeber oder Fassung, oder diese tragen keinen lateinischen Buchstaben und keine Ziffer, aus denen die
  IRI würde (`incomplete`, `details.missing`), keine `IRI_BASE` (`no_iri_base`), X5 lief nie (eine Kopie:
  vor ihrem Prüfjob), schuldet eine Prüfung oder eine Fundstelle ist ungeprüft (`check_owed`,
  `details.unchecked`; Fundstellen verworfener Aussagen zählen nicht), Verstöße unter den Befunden ohne
  `accept_violations` (`has_violations`, `details.violations`). Dann bekommen Werk
  (`…/work/<land>/<kurztitel>`), Dokument (`…/doc/<land des Werks>/<herausgeber>/<kurztitel des
  Werks>/<fassung>`), Knoten (Pfad ihrer Codes; ein Code wie „S 1“ zählt weiter, `s-<n>` gehört den
  Aussagen) und Aussagen (`<knoten>/s-<n>`, jede Nummer einmal, auch unter einem Knoten, der in einer Kopie
  neu am selben Pfad entstand) ihre IRIs; eine IRI, die ein anderes Werk oder Dokument hält – auch eines,
  das im selben Augenblick festgeschrieben wird –, weist ab (`iri_taken`, `details.iri`). Danach weist die
  Datenbank jede Änderung an den Zeilen des Dokuments ab, nur der Rechtestatus bleibt änderbar. Audit
  `document.freeze` mit Revision und angenommenen Verstößen; die Antwort ist das Dokument.
- Entwurfskopie: `POST /api/v1/documents/{id}/draft-copy` (nur Redaktion/Admin, 201 mit der Kopie)
  öffnet die nächste Revision eines festgeschriebenen Dokuments unter derselben IRI: alle Zeilen mit
  ihren IRIs, Herkunft, Prüfstand und Revisionen, ohne Läufe und Befunde – X5 schuldet ihr eine
  Prüfung (`POST …/check`). Bearbeiten und Festschreiben wie beim ersten Mal; die vorige Revision bleibt
  lesbar. Abgewiesen: kein festgeschriebenes Dokument (409 `not_frozen`), eine spätere Revision ist
  festgeschrieben (`not_latest`), ein Entwurf der IRI ist offen (`draft_open`, `details.document_id`),
  eine Zeile passt nicht mehr zum heutigen Vokabular, etwa ein Knotentyp, den eine spätere Ladung unter
  seiner Funktion herausnahm (`vocabulary_changed`, `details.check`: die Prüfung, an der sie scheitert).
  Audit `document.copy`.
  In der Oberfläche nennt die Dokumentseite unter „Werk und Fassung“ Herausgeber, Fassung, Werk, IRI und
  Revision; bis zum Festschreiben ändern Eigentümer und Redaktion dort Titel, Herausgeber und Fassung (mit
  IRI nur noch den Titel), und die Redaktion setzt das Werk – ein bekanntes aus den Dokumenten, die sie sieht,
  oder ein neues mit Titel, Land und Kurztitel. „Festschreiben“ (Redaktion) fragt vorher, mit den Folgen;
  nennen die Befunde Verstöße, fragt es noch einmal mit ihrer Zahl. Was der IRI fehlt, nennt es einzeln, eine
  ausstehende Prüfung mit dem Weg zum Baum. Festgeschrieben steht oben, wann und als welche Revision, dazu für
  die Redaktion „Als Entwurf kopieren“, das die Seite der Kopie öffnet; eine Entwurfskopie nennt ihre
  Vorlage. Extraktion und Reparatur bietet die Seite dort nicht mehr an.
- Abbrechen: `POST /api/v1/jobs/{id}/cancel` (Eigentümer des Jobs oder Admin, in der Oberfläche
  der Knopf „Abbrechen“ an jedem Auftrag). Ein wartender Job endet sofort, ein laufender beim
  nächsten Herzschlag seines Workers (alle `JOB_LEASE_S`/3); hält der Handler dann nicht an,
  endet der Job nach `CANCEL_WAIT_S` (5 s, bei kürzerer Lease einem Drittel von ihr) trotzdem
  `cancelled`. Was der Handler danach noch schreibt, findet seine Lease nicht mehr, und eine
  Modellanfrage – auch eine Wiederholung – reserviert er nicht mehr (`check_lease` im Zähler).
  Ein Worker, der gar nicht mehr schlägt,
  endet über die Prüfung abgelaufener Leases ebenso `cancelled`.
- Extraktion (X1–X5): Der Job `extract.run` (`{"document_id": …}`) bestimmt für ein Dokument per
  Sprachmodell das Dokumentprofil (Titel, Typ, Geltung,
  Spezifikationen, eigene Begriffe), baut das Gerüst ohne Modell aus Verzeichnis, Layout und
  Lexikon, lässt nur die Überschriften ohne starkes Muster vom Modell einordnen und teilt den
  Text in Arbeitspakete (X2). X3 liest mit einer Anfrage die Rahmenteile – Kompetenz- und
  Niveaumodelle, Operatoren, Querschnittslegende und Regeln (Tabelle `frame_part`, Migration 0015) –
  und die Ziele und Aufträge der Rahmenabschnitte als Aussagen an deren Knoten. X4 liest je
  Arbeitspaket mit Aussagen eine Anfrage, hinter demselben Präfix (Dokument, Profil, Auswahllisten
  aus X3, Cache-Haltepunkt danach), wo das Dokument ins Kontextfenster passt, sonst hinter dem
  Fenster um den Abschnitt des Pakets, bis zu
  `EXTRACT_CONCURRENCY` (Standard 4, 1–16; nie mehr als `DB_POOL_MAX_SIZE` − 1) zugleich. Jedes
  Paket wird für sich geschrieben, sobald es beantwortet ist (`extraction_unit`, Migration 0019):
  Wortlautfelder nur, wenn sie in den Blöcken der Aussage stehen, Herkunft Modell, Prüfstand
  vorgeschlagen. X5 prüft ohne Modell: jeden noch ungeprüften Wortlaut (Aussage, Überschrift
  eines Knotens) gegen den Text der Blöcke seines Ankers – wörtlich, über Leerraum hinweg,
  normalisiert, mit Auslassung oder unscharf, wie die Ankersuche der alten App; die Fundart, bei
  unscharfen Treffern ihr Wert, der Text an der Stelle (`quote`) und die Zeichenspanne stehen dann
  am Anker –, die Plausibilität (Überschrift als Aussage, Arbeitspaket ohne Aussagen, Regelgrenzen,
  zurückgezogene Werte) und den Kern-Graphen des Dokuments gegen die SHACL-Formen des
  Curriculum-Kerns und der Profile, in einem eigenen Prozess mit der Frist `SHACL_TIMEOUT_S`
  (Standard 300 s, 10–1800). Die Befunde stehen in `validation_finding` (Verstoß, Warnung,
  Hinweis): ein Wortlaut, den seine Blöcke nicht enthalten, ist ein Verstoß, eine überschrittene
  Frist der Verstoß `x5.shacl_timeout`; X5 endet in beiden Fällen fertig. Ein neuer Start der
  Extraktion prüft ein Dokument, dessen X5 fertig ist, nicht erneut; das tut erst eine Reparatur,
  die Arbeitspakete neu schreibt, dann mit der geltenden Frist. Stirbt der Prüfprozess
  (Speichermangel) oder bricht
  er ab, scheitert der Lauf (`ShaclCrashed`), und der Job wird bis zu seiner Versuchsgrenze
  wiederholt (`handler_error`). Jede Stufe jedes Versuchs ist ein
  eigener Lauf (`extraction_run`); X1 bis X3 schreiben ihr Ergebnis auf einmal, X4 je Paket, X5
  erst die Anker, dann Befunde und Ende zusammen. Ein neuer Versuch oder ein neuer Job auf
  demselben Dokument macht nach der letzten fertigen Stufe weiter, in X4 mit den offenen Paketen;
  zwei gleichzeitige schreiben jede Stufe und jedes Paket einmal.
  Fortschritt: `extract_profile`, `extract_outline`, `extract_segments`, `extract_frame`,
  `extract_statements` (fertig/gesamt), `check_document`. Endet mit
  `budget_exhausted` (Budget aufgebraucht: in X4 beginnt kein Paket mehr, die laufenden werden
  fertig, Fertiges bleibt), `model_unanswered` (keine Antwort im Schema; in X4 bleiben nur solche
  Pakete offen), `model_not_configured` (kein `OPENAI_API_KEY` im Worker), `prefix_too_long`
  (nicht einmal ein Abschnitt passt neben Titelei und Rahmenteilen ins Kontextfenster),
  `document_gone` oder `document_has_tree` (Knoten oder Spezifikationen stehen schon, aber keine
  Extraktion schrieb sie). Der Worker startet auch ohne
  Schlüssel; das Modell entsteht beim ersten Job, der es braucht.
- Reparatur (X6): Der Job `extract.repair` (`{"document_id": …}`) fragt nur die Arbeitspakete
  erneut, deren Aussagen X5 oder das Lesen der Antwort beanstandet hat – ein Verstoß an einer
  Aussage, die X4 oder X6 schrieb und die seither niemand angefasst hat, oder eine Warnung oder ein
  Verstoß beim Lesen, der das Paket nennt (außer `*.pattern_timeout`) –, je Job einmal, je Paket
  höchstens zweimal (`extraction_unit.repairs`, Migration 0020). Hinweise, Warnungen der
  SHACL-Prüfung und die übrigen Befunde an Knoten oder am Dokument (etwa `x5.shacl_timeout`) sind
  kein Anlass. Die Frage ist die von X4 hinter demselben Präfix, dazu die Befunde in Worten – mit
  dem Block, Wert oder Schlüssel, der falsch war – und die Wortlaute, die die Redaktion hält oder
  verworfen hat (Promptversion `x6-repair/1`). Die Antwort ersetzt die unangetasteten Aussagen des
  Pakets; bestätigte, verworfene und von Hand geschriebene bleiben und kommen nicht doppelt, ein
  Verweis auf Inhalt geht dann auf die gehaltene Aussage. Eine Antwort außerhalb des Schemas lässt
  das Paket, wie es war, zählt aber als Reparatur (Warnung `x6.unanswered`), ebenso eine Antwort
  ohne Aussage für ein Paket, das welche hat (Warnung `x6.empty_answer`). Danach prüft X5 das
  Dokument erneut, seine Befunde ersetzen die des letzten X5 – auch wenn das Budget X6 beendet hat,
  bevor der Job mit `budget_exhausted` endet. Ein neuer Versuch fragt kein Paket, das der Job schon
  gefragt hat. Endet eine Reparatur, bevor X5 geprüft hat, was sie schrieb (abgebrochen, Versuche
  aufgebraucht), prüft die nächste Extraktion („Extraktion fortsetzen“) oder Reparatur das
  Dokument erneut. Ist nichts mehr zu reparieren, fragt der Job kein Modell. Fortschritt `repair_units` (fertig/gesamt); endet
  mit `document_not_checked`, wo X5 noch aussteht. In der Oberfläche bietet der Abschnitt
  „Befunde“ des Dokuments dem Eigentümer den Knopf „Reparieren“ an; ihr Stand steht unter
  „Extraktion“.
- Prüfung nach der Redaktion (X5): Der Job `extract.check` (`{"document_id": …}`) prüft ein
  Dokument erneut, nachdem die Redaktion es geändert hat; seine Befunde ersetzen die des letzten
  X5. Verworfene Aussagen prüft X5 nicht und der Kern-Export enthält sie nicht. Fortschritt
  `check_document`; endet mit `document_not_checked`, wo X5 noch aussteht; ein neuer Versuch prüft
  nicht doppelt.
- Erster Admin: `python -m app.bootstrap NAME` gibt das Token einmal auf stdout aus. Interaktiv
  ausführen (`docker compose run`, `kubectl exec -it`), nicht als Job, dessen Ausgabe ein
  Log-System sammelt. Exit-Code 0: angelegt; 2: es gibt schon einen Admin, der sich anmelden
  kann; 1: Fehler. Weitere Konten und Tokens legt ein Admin über `/api/v1/accounts` an.
- `PUBLIC_ACCESS` (`off` | `lookup` | `search`, Standard `off`): was Besucher ohne Token dürfen.
  Das Sprachmodell braucht immer ein Token.
- `MAX_UPLOAD_MB` (Standard 50, höchstens 500): die größte Datei, die ein Upload oder ein
  URL-Import annimmt; größere weist der Upload mit 413 `file_too_large` ab, einen Body über
  `MAX_UPLOAD_MB` + 1 MiB schon vor dem Lesen mit 413 `content_too_large`. Ein DOCX darf
  entpackt höchstens 256 MiB in 5.000 Teilen halten (`archive_too_large`). Was ein Upload in
  `/tmp` und im Arbeitsspeicher braucht, steht in `docs/uebergabe/konfiguration.md`.
- `UPLOADS_PER_MINUTE`, `URL_IMPORTS_PER_MINUTE` und `CONVERSIONS_PER_MINUTE` (Standard je 20):
  Uploads, URL-Importe bzw. gestartete Konvertierungen je Konto und Minute, gezählt in
  PostgreSQL für alle Replicas; darüber 429 mit `Retry-After`. Eine Konvertierung, die wartet
  oder fertig ist, noch einmal anzufragen, startet und zählt nichts.
- `FETCH_USER_AGENT`: so stellen sich URL-Import und Prüfjob den Servern vor. Vorn steht das
  Produktkürzel, unter dem robots.txt uns kennt (`Kompetenzkartierer-AI`), dahinter, wo die
  Betreiber zu erreichen sind – hier den eigenen Kontakt eintragen (öffentliche Seite oder
  Postfach), denn der Standard nennt nur das Repository. Druckbares ASCII, ohne Leerzeichen am
  Ende. Der Prüfjob sendet fremden Hosts keine Trace-Header. `CHECK_HOST_INTERVAL_S`
  (Standard 2, mindestens 0,5): der kleinste Abstand zweier Anfragen des Prüfjobs an einen
  Host, über alle Worker.
- `THIRD_PARTY_MARKDOWN` (`hidden` | `accounts` | `public`, Standard `hidden`): wer außer
  Redaktion und Admin die Datei eines Registereintrags ohne Eigentümer (Saat, Recherche)
  bekommt, später auch seine Blöcke und sein Markdown: niemand, jedes Konto oder auch Besucher,
  diese nur bei `PUBLIC_ACCESS` ≠ `off`. Ein Upload bleibt bei seinem Konto.
- `FORWARDED_ALLOW_IPS` (Standard `127.0.0.1,::1`): Adressen oder Netze der Proxys, deren
  `X-Forwarded-For` die Client-Adresse nennt; nie `*`, sonst wählt jeder Client seine Adresse
  selbst und umgeht das Limit. Aus demselben Grund wird ein Netz `/0` abgewiesen, und ein Netz
  mit gesetzten Hostbits (`10.42.1.5/16`) ebenso, statt still erweitert zu werden.
- `AUTH_FAILURE_LIMIT` (Standard 10) Fehlversuche je IPv4-Adresse oder IPv6-/64 innerhalb
  `AUTH_FAILURE_WINDOW_S` (Standard 900 s), danach 429. Ein gültiges Token kommt immer durch.
- `DB_POOL_TIMEOUT_S` (Standard 5 s): so lange wartet eine Anfrage auf eine Verbindung, dann
  antwortet sie 503 mit `Retry-After`.

Worker: `JOB_LEASE_S` (Standard 60 s; ein Worker ohne Lebenszeichen verliert seinen Job danach),
`JOB_POLL_S` (Standard 1 s), `JOB_SHUTDOWN_GRACE_S` (Standard 20 s): Nach SIGTERM darf der
laufende Job so lange zu Ende laufen, dann geht er unverbraucht an den nächsten Worker zurück.
Mindestens 5 s unter der Frist des Deployments halten (Kubernetes: 30 s): Nach der Frist bekommt
der Handler noch bis zu 2 s zum Aufräumen, erst dann wird der Job zurückgegeben.

Sprachmodell (OpenAI-kompatibel): `OPENAI_API_KEY` (auch `OPENAI_API_KEY_FILE`; nur sichtbare
ASCII-Zeichen), `OPENAI_BASE_URL` (Standard `https://api.openai.com/v1`; `http(s)://Host[:Port][/Pfad]`
ohne Nutzer, Query oder Fragment, `http` für ein Gateway im Cluster), `OPENAI_MODEL` (Standard
`gpt-6-luna`), `LLM_PROVIDER` (`openai` spricht die Responses-API, `openai-compatible` Chat
Completions), `OPENAI_REASONING_EFFORT` und `OPENAI_TEXT_VERBOSITY` (Standard `low`). Nimmt das
Modell den Aufwand laut seinem Profil nicht an (gpt-6-luna kein `minimal`), starten API und
Worker nicht. Ohne Schlüssel starten beide, nur Aufrufe des Modells scheitern.
`LLM_MAX_OUTPUT_TOKENS` (Standard 16.000, mindestens 1.000) begrenzt die Ausgabe jeder Anfrage,
Reasoning eingeschlossen. Lässt sie im Kontextfenster neben den 17.000 Token, die eine Anfrage
außer dem Dokument braucht, keinen Platz, starten API und Worker nicht. Token zählt der Dienst
lokal mit tiktoken (`o200k_base`): Die Datei liegt mit ihrem SHA-256 in `backend/app/llm/` und
wird nie aus dem Netz geladen. Fehlt sie oder stimmt ihr Hash nicht, starten API und Worker nicht.

Kosten des Modells: Ein Konto ohne Quote darf nichts verbrauchen, auch ein Admin nicht.
- Ein Admin setzt die Quote mit `PUT /api/v1/accounts/{id}/quota`
  (`{"token_limit": …, "page_limit": …}`). Beide Grenzen müssen ausdrücklich genannt werden,
  `null` heißt unbegrenzt. Die Änderung wird als `account.quota` protokolliert.
- `GET /api/v1/me/usage` zeigt dem Konto Grenze, Verbrauch (davon geschätzt), Reserviertes und
  den Rest.
- Vor jeder Anfrage reserviert der Aufruf die gezählte Eingabe (plus 10 %) und
  `LLM_MAX_OUTPUT_TOKENS`. Danach ersetzt die gemeldete Nutzung die Reservierung. Als Verbrauch
  gebucht und als geschätzt gekennzeichnet wird die Reservierung einer gesendeten Anfrage ohne
  Antwort, einer Antwort ohne Nutzungsangabe und einer Antwort, die kein Modell lesen konnte. Die
  letzte lässt den Aufruf scheitern. Eine Anfrage, die nie hinausging (keine Verbindung), kostet
  nichts. In X4 hält ein Job bis zu `EXTRACT_CONCURRENCY` Reservierungen zugleich; reicht der Rest
  für die nächste nicht, beginnt kein Paket mehr.
- Bei 429, 5xx und einem nicht erreichten Anbieter wartet der Aufruf selbst, höchstens zweimal:
  so lange wie `Retry-After`, sonst 20 bzw. 40 s, nie länger als 60 s. Bei `insufficient_quota`
  wartet er nicht.
- Die Rohantworten legt er vor der Auswertung unter `runs/<Lauf>/<Stufe>/<n>.json` im
  Objektspeicher ab.
- Einen Modelljob darf ein Konto nur starten, solange es seine Grenze nicht verbraucht hat, sonst
  403 `no_budget`; was laufende Aufrufe reserviert halten, zählt dabei nicht. Höchstens
  `MAX_JOBS_IN_FLIGHT` (Standard 20) dürfen warten oder laufen, sonst 429 `too_many_jobs` mit
  `Retry-After: 60`. Höchstens `MODEL_STARTS_PER_MINUTE` (Standard 10) Starts je Minute, sonst 429
  `too_many_starts`.
- Modelljob ist `extract.run`. Endet ein Versuch eines Jobs (fertig, gescheitert, abgebrochen,
  zurückgegeben), bucht dieselbe Transaktion seine offenen Reservierungen als geschätzten
  Verbrauch. Starb ein Worker oder verlor er die Lease, bucht sie die Prüfung abgelaufener Leases:
  die Reservierungen jedes Jobs, der gerade nicht läuft.
- Metriken: `kka_llm_requests_total`, `kka_llm_tokens_total`, `kka_usage_reservations_total`.

Objektspeicher: `STORAGE_BACKEND` (`fs` | `s3`, Standard `fs`). Mit `fs` braucht der Speicher
`STORAGE_DIR` (für Entwicklung und einen einzelnen Knoten); im Cluster `s3` mit `S3_BUCKET`,
`S3_ENDPOINT_URL` (leer für AWS selbst), `S3_REGION` (Standard `us-east-1`) und den Schlüsseln
`S3_ACCESS_KEY`/`S3_SECRET_KEY` (beide oder keiner, auch als `*_FILE`; ohne sie nimmt boto3
seine Standardkette: `AWS_*`-Variablen, Web-Identity, die Rolle der Instanz). Wohin der Dienst
geht, sagt nur `S3_ENDPOINT_URL`: `AWS_ENDPOINT_URL` und ein `endpoint_url` in `~/.aws/config`
übergeht er. Beim Öffnen (beim Start von API und Worker) fragt der
Speicher einmal nach dem Bucket und bricht ab, wenn es ihn nicht gibt.
`python -m app.core.storage_bucket` legt den Bucket an, wo die Umgebung keinen mitbringt
(Compose).

### Compose

`deploy/docker-compose.yml` startet alles auf einem Rechner: PostgreSQL mit pgvector, MinIO
(Chainguard-Build), die einmaligen Schritte Bucket, Migration und Vokabular, je zwei API- und
Worker-Replicas und den Webserver davor. Vom Wurzelverzeichnis aus:

```bash
python deploy/make-secrets.py
(cd frontend && npm ci && npm run build)
docker compose -f deploy/docker-compose.yml up -d --build
```

Die App antwortet unter `http://127.0.0.1:18080`; sonst ist nichts am Host veröffentlicht. Der
Webserver reicht `/api` und die Spec an die API weiter (`deploy/nginx-api.conf`, nur in Compose
eingebunden); das Web-Image selbst antwortet dort mit 404, im Cluster routet der Ingress.
`deploy/make-secrets.py` schreibt die Geheimnisse als Dateien nach `deploy/secrets/` (nicht im
Repository, für alle Nutzer des Rechners lesbar, weil die Container unter anderen Nutzern
laufen; nur für Entwicklung). Ein vorhandenes Geheimnis bleibt stehen. Der erste Admin:
`docker compose -f deploy/docker-compose.yml run --rm migrate python -m app.bootstrap NAME`.
`down` hält die Daten, `down -v` löscht Datenbank und Objekte dieses Projekts (`kka`).
