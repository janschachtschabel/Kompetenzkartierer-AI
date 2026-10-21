# Detailplan M0: Fundament

Stand 22.10.2026. Teil des [Gesamtplans](2026-10-21-gesamtplan.md), Abschnitt 13. Ziel: ein
lauffähiges, clusterfähiges Gerüst nach den Betriebsvorgaben, auf dem M1 die Extraktion
aufbaut. Keine Fachlogik außer dem Vokabular-Lader.

## Arbeitsweise

- Je Paket: Schritt 0 `/better-coding-workflow` laden; jede Aufgabe beginnt mit dem roten Test
  (Lauf zeigt den Fehlschlag), dann die kleinste Umsetzung, dann der grüne Lauf.
- Nach jedem Paket: `/better-coding-review` über den Diff des Pakets; Befunde mit
  `/better-coding-workflow` beheben; danach `/better-coding-verify` mit Befehl und Ausgabe.
- Commits lokal im neuen Repository, eine Aufgabe je Commit (Conventional Commits, englisch);
  kein Push ohne Auftrag.
- Python 3.13 über uv. Ohne Netz ließ sich nur eine Windows-Auflösung bauen
  (`requirements-dev-win.txt`, `uv pip compile --offline`); 3.12 scheiterte, weil der Cache
  fast nur cp313-Wheels hat. Der universelle `uv.lock` folgt mit der Download-Freigabe in
  Paket D. Tests gegen PostgreSQL in
  einem eigenen Container `kka-test-pg` aus dem lokal vorhandenen Image
  `pgvector/pgvector:pg17`, Port 55432, Daten in tmpfs.
- Downloads nur nach Freigabe. Noch nicht lokal vorhanden: Image `python:3.13-slim`,
  `nginxinc/nginx-unprivileged`, `minio/minio`, Python-Paket `boto3`. Sie werden erst in
  Paket D gebraucht.

## Festlegungen für M0

- Paket `app` unter `backend/`; Einstieg `python -m app.serve` (API) und
  `python -m app.jobs.worker` (Worker).
- **Ein uvicorn-Prozess je Pod**, der zwei Sockets bedient: öffentlich `PUBLIC_PORT` (8000),
  intern `INTERNAL_PORT` (9000). Skaliert wird über Replicas, nicht über Worker-Prozesse; die
  schwere Arbeit läuft im Worker. Damit entfällt der Multiprozess-Sammler für Metriken.
- Interne Pfade `/health`, `/ready`, `/metrics` antworten am öffentlichen Port mit 404 und
  stehen nicht in der OpenAPI-Spec (Muster `InternalOnly` aus compendious).
- Migrationen als versionierte SQL-Dateien, angewendet von `python -m app.db.migrate` unter
  `pg_advisory_lock`; API und Worker migrieren nie selbst, sie prüfen nur den Stand
  (`/ready` meldet 503 bei fehlender Migration).
- Job-Warteschlange in PostgreSQL mit `FOR UPDATE SKIP LOCKED`, Spur je Konto, Lease mit
  Lebenszeichen.
- Auth: Tokens, die ein Admin vergibt (HMAC-SHA-256 mit Pepper); Rollen `admin`,
  `redaktion`, `nutzer`; `PUBLIC_ACCESS` = `off` | `lookup` | `search`; Endpunkte mit
  Sprachmodell verlangen immer ein Token.
- LLM-Einstellungen nach der alten App ohne B-API: `OPENAI_BASE_URL`, `OPENAI_MODEL`
  (`gpt-6-luna`), `OPENAI_REASONING_EFFORT`, `OPENAI_TEXT_VERBOSITY`, `LLM_PROVIDER`
  (`openai` | `openai-compatible`), `LLM_CONTEXT_TOKENS`.

## Paket A: Gerüst und Betriebsseite

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| A0 | Ontologie übernehmen | `ontology/` (Kopie von `ergebnis/`: `ontologie/`, `vokabulare/`, `profile/`, `schemas/`, `werkzeuge/`, `pruefung/`, `beispiele/`, `README.md`, `konzept.md`) | – | `python -I ontology/pruefung/pruefe.py` meldet `OK` |
| A1 | Projektgerüst | `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/__init__.py`, `.gitignore`, `README.md` | `tests/test_version.py`: `app.__version__` gleich der Paketversion | `uv run pytest -q`, `ruff check`, `mypy app` |
| A2 | Settings | `app/core/settings.py` | Standardwerte; `*_FILE` hat Vorrang; fehlendes Pflichtfeld nennt den Namen, keinen Wert; nur erfundene Werte | `pytest tests/core/test_settings.py` |
| A3 | Zwei Ports, interne Pfade | `app/serve.py`, `app/api/app.py` (`create_app`), `app/api/internal.py`, `app/api/paths.py` | interner Pfad am öffentlichen Port 404, auch mit Schrägstrich am Ende und unter einem Root-Pfad; am internen Port 200; nicht in `/openapi.json` | Tests mit ASGI-Scope je Port |
| A4 | OpenAPI-Metadaten | `app/api/app.py` | Titel, Kurzbeschreibung, Beschreibung, Version, Tags vorhanden | Test liest `/openapi.json` |
| A5 | Logging | `app/core/logging.py` | `LOG_FORMAT=json` ergibt eine JSON-Zeile mit `time`, `level`, `logger`, `request_id`, `trace_id`, `message`; ungültiges `LOG_LEVEL` beim Start abgewiesen | Tests mit Capture |
| A6 | Tracing und Request-Log | `app/core/tracing.py`, `app/api/request_log.py` | `x-client-trace-id` und B3 übernommen, ungültige Werte verworfen; `X-Request-ID` an jeder Antwort; eine Logzeile je Anfrage ohne Query-Werte | Tests über den TestClient |
| A7 | Metriken | `app/core/metrics.py`, `/metrics` in `app/api/internal.py` | HTTP-Zähler und -Dauer nach Route-Vorlage (nicht nach roher URL); `/metrics` nur intern | Test liest die Ausgabe |

## Paket B: Datenbank

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| B1 | Pool und Migrationsläufer | `app/db/pool.py`, `app/db/migrate.py`, `migrations/0001_schema_migration.sql` | zwei Läufe parallel wenden jede Datei genau einmal an; neuere DB als Code wird abgewiesen; Prüfsumme einer schon angewendeten Datei darf sich nicht ändern | `pytest -m pg tests/db/` |
| B2 | Grundtabellen | `migrations/0002_core.sql` | `entity`, `account`, `role_grant`, `api_key`, `job`, `llm_usage`, `conversion_usage`, `quota`, `audit_log`; Erweiterungen `vector`, `pg_trgm`, `unaccent`; Fremdschlüssel und Eindeutigkeit greifen | `pytest -m pg` |
| B3 | Bereitschaft | `app/api/internal.py` | `/ready` 503 ohne Datenbank oder bei fehlender Migration, 200 sonst | Test mit gestoppter bzw. leerer DB |
| B4 | Vokabular-Lader | `app/vocab/loader.py`, `migrations/0003_vocab.sql`, Einstieg `python -m app.vocab.load` | Zahl der Schemata und Stufen in `lvl:` gleich der TTL (24 und 135); zweiter Lauf ändert nichts; geänderte TTL ergibt neuen Stand | `pytest -m pg tests/vocab/` |

## Paket C: Jobs, Auth, LLM, Speicher

| # | Aufgabe | Dateien | Test zuerst | Nachweis |
|---|---|---|---|---|
| C1 | Warteschlange | `app/jobs/queue.py` | anlegen, holen mit `SKIP LOCKED` und Spur je Konto (abwechselnd), Lease verlängern, abgelaufene Lease freigeben, Abbruch per Markierung, begrenzte Wiederholung | `pytest -m pg tests/jobs/` |
| C2 | Worker | `app/jobs/worker.py` | zwei Worker verarbeiten 50 Jobs ohne Doppelausführung; ein Worker ohne Lebenszeichen verliert die Lease, ein anderer übernimmt; abgebrochene Jobs laufen nicht | Stresstest mit zwei Prozessen |
| C3 | Auth | `app/core/auth.py`, `app/api/deps.py`, `app/api/accounts.py` (Admin legt Konto und Token an) | ohne Token 401 bei `off`; `lookup` öffnet nur Lesepfade; LLM-Pfad ohne Token 401; falsche Rolle 403; gesperrtes Konto 401; Limit für Fehlversuche | `pytest -m pg tests/core/test_auth.py` |
| C4 | LLM-Einstellungen | `app/llm/settings.py`, `app/llm/client.py` | Standardwerte; unbekannter Anbieter beim Start abgewiesen; Wertelisten gegen die Typen der Bibliothek; Basis-URL wird für Responses- und Chat-API genutzt (Mock-Transport); Schlüssel nie in Log oder Fehler | `pytest tests/llm/` |
| C5 | Objektspeicher | `app/core/storage.py` | Dateisystem: schreiben, lesen, löschen, Pfad-Ausbruch abgewiesen; S3 folgt in D | `pytest tests/core/test_storage.py` |

## Paket D: Images, Compose, CI, Übergabe (Downloads nötig)

| # | Aufgabe | Dateien | Nachweis |
|---|---|---|---|
| D1 | API-Image | `deploy/api.Dockerfile`, `.dockerignore` | Image läuft als 10001, HEALTHCHECK am internen Port, keine Daten; Größe gemessen |
| D2 | Compose | `deploy/docker-compose.yml` | api ×2, worker ×2, migrate, postgres, minio, valkey optional; `/ready` 200; Migration genau einmal |
| D3 | S3-Speicher | `app/core/storage.py` | Integrationstest gegen MinIO (Marker `s3`) |
| D4 | CI | `.github/workflows/ci.yml` | Ontologie-Prüfung, ruff, mypy, Tests mit PostgreSQL-Dienst, Image-Build; grüner Lauf erst nach Push |
| D5 | Übergabe-Gerüst | `docs/uebergabe/anforderungen.md`, `konfiguration.md` (aus den Settings erzeugt, Test vergleicht), `deploy/helm-values.example.yaml` | Test: jede Einstellung steht in `konfiguration.md` |

## Paket E: Frontend-Rahmen

| # | Aufgabe | Dateien | Nachweis |
|---|---|---|---|
| E1 | Gerüst | `frontend/` (Vite, Vue 3, TypeScript), `npm ci --offline` | `vitest run` grün |
| E2 | Übernahme Querschnitt | `src/style.css`, `src/i18n/`, `src/api/http.ts`, Zustände, Dialoge | statische Schutztests (Texte, Katalog, Tokens, Kontrast) grün |
| E3 | Startseite | Anmeldung mit Token, Navigation je Rolle, öffentlicher Modus | axe ohne Befund |

## Abnahme M0

Wie im Gesamtplan §14: Compose startet alles, Migration genau einmal, interne Pfade nur
intern, Trace-ID in den Logs von api und worker, 50 Jobs auf zwei Workern je genau einmal,
Image als Nutzer 10001 ohne Daten, Vokabular-Zahlen gleich denen von `pruefe.py`.
