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
oder Worker), `python -m app.vocab.load` lädt die Vokabulare aus `ONTOLOGY_DIR` (Standard:
`ontology/` dieses Repositorys), `python -m app.serve` startet die API auf `PUBLIC_PORT` und
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

- Erster Admin: `python -m app.bootstrap NAME` gibt das Token einmal auf stdout aus. Interaktiv
  ausführen (`docker compose run`, `kubectl exec -it`), nicht als Job, dessen Ausgabe ein
  Log-System sammelt. Exit-Code 0: angelegt; 2: es gibt schon einen Admin, der sich anmelden
  kann; 1: Fehler. Weitere Konten und Tokens legt ein Admin über `/api/v1/accounts` an.
- `PUBLIC_ACCESS` (`off` | `lookup` | `search`, Standard `off`): was Besucher ohne Token dürfen.
  Das Sprachmodell braucht immer ein Token.
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
