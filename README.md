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

Betrieb: `python -m app.db.migrate` wendet die Migrationen an (einmal je Release, nie aus API
oder Worker), `python -m app.vocab.load` lädt die Vokabulare aus `ONTOLOGY_DIR` (Standard:
`ontology/` dieses Repositorys), `python -m app.serve` startet die API auf `PUBLIC_PORT` und
`INTERNAL_PORT` (`/health`, `/ready`, `/metrics`).
