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
uv venv --python 3.13 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev-win.txt
.venv/Scripts/python.exe -m pytest
```

`requirements-dev-win.txt` ist vorläufig: Es wurde ohne Netz für Windows aufgelöst. Sobald
Downloads möglich sind, ersetzt ein universeller `uv.lock` die Datei.

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

## Betrieb

`python -m app.db.migrate` wendet die Migrationen an (einmal je Release, nie aus API
oder Worker), `python -m app.vocab.load` lädt die Vokabulare aus `ONTOLOGY_DIR` (Standard:
`ontology/` dieses Repositorys), `python -m app.serve` startet die API auf `PUBLIC_PORT` und
`INTERNAL_PORT` (`/health`, `/ready`, `/metrics`), `python -m app.jobs.worker` den Worker.

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
  selbst und umgeht das Limit.
- `AUTH_FAILURE_LIMIT` (Standard 10) Fehlversuche je IPv4-Adresse oder IPv6-/64 innerhalb
  `AUTH_FAILURE_WINDOW_S` (Standard 900 s), danach 429. Ein gültiges Token kommt immer durch.
- `DB_POOL_TIMEOUT_S` (Standard 5 s): so lange wartet eine Anfrage auf eine Verbindung, dann
  antwortet sie 503 mit `Retry-After`.
