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
