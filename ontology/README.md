# Curriculum-Kern 1.0 (Entwurf) – Ergebnisordner

Ergebnis der Auswertung der Recherche-Ontologien in `docs/recherche/ontologien/`: ein gemeinsamer Kern für alle Bildungsbereiche, fünf Bereichsprofile, gemeinsame Vokabulare, SHACL, JSON-Schemas für die Extraktion, Beispiele und ein Prüfskript.

**Zuerst lesen:** [`konzept.md`](konzept.md).

## Inhalt

| Ordner | Inhalt |
|---|---|
| `ontologie/` | `cur-kern.ttl` (Kern), `cur-vokabular.ttl` (Kernvokabular `cv:`), `cur-shapes.ttl` (SHACL), `cur-alignments.ttl` (CTDL-ASN, CASE, ELM, schema.org/AMB, ESCO, PROV, OA, FWU, OEH/KIM), `migration.ttl` (Vorentwürfe → Kern) |
| `vokabulare/` | Länder, Niveausysteme, Kompetenzdimensionen, Querschnittsziele, Kontexte, Fächer (ISCED-F), Operatoren |
| `profile/` | `schule`, `elementar`, `beruf`, `hochschule`, `erwachsenenbildung` (+ generierte Lexika `*-lexikon*.ttl`), `profil-shapes.ttl` |
| `schemas/` | strikte JSON-Schemas der LLM-Stufen X1 (Dokumentprofil, Gerüst), X3, X4, N1, G1 – generiert |
| `beispiele/` | `ohm-kette` (Schule → Beruf → Hochschule), `elementar`, `erwachsenenbildung`, `kompetenzrahmen`; Negativsätze `fehlerhaft` (Violations) und `fehlerhaft-hinweise` (Warnungen). Alle Wortlaute fiktiv. |
| `pruefung/` | `pruefe.py` und Anwendungsfall-Abfragen `abfragen/q1…q6.rq` |
| `werkzeuge/` | Generatoren für Lexika und Schemas, Export der Vorlisten; `quellen/fwu-landesklassen.csv` (aus der FWU-Lehrplan-Ontologie abgeleitet) |
| `recherche-auftraege/` | kopierfertige Rechercheaufträge für Länder-Steckbriefe mit einheitlichem Ausgabeformat; `vorlisten/` = heutiges Lexikon je Bereich und Land zum Prüfen |

## Prüfen

Aus diesem Ordner, mit einem Python, das `rdflib` und `pyshacl` hat (im Repository das Backend-`.venv`, Abhängigkeitsgruppe `dev`):

```bash
../backend/.venv/Scripts/python.exe -I pruefung/pruefe.py
```

Ursprung: `docs/recherche/ontologien/ergebnis/` im Repository Kompetenzkartierer (alte App),
übernommen am 22.10.2026. Weitergeführt wird der Kern ab jetzt nur hier.

Das Skript braucht kein Netz. Es prüft:

- Parsen und undefinierte Terme;
- Labels, Schemata und Notationen;
- die Lexikonmuster gegen ihre eigenen Beispiele;
- JSON-Enums gegen die Vokabulare;
- SHACL ohne Inferenz: positive Beispiele konform, negative mit genau den erwarteten Befunden;
- die Anwendungsfall-Abfragen.

Exit-Code 0 = alles in Ordnung.

## Neu erzeugen

Generierte Dateien nie von Hand ändern, sondern Quelle oder Generator anpassen:

```bash
python -I werkzeuge/portiere_elementar_lexikon.py ../elementarbildung/extraktionshinweise-laender.ttl .
```

```bash
python -I werkzeuge/portiere_hochschul_lexikon.py ../hochschule/hco-lexicon.ttl .
```

```bash
python -I werkzeuge/erzeuge_schul_lexikon_fwu.py .
```

```bash
python -I werkzeuge/erzeuge_schemas.py .
```

## Namensräume und Lizenzen

- Alle IRIs unter `https://w3id.org/wlo/curriculum/…` sind **Platzhalter**; `w3id.org/wlo` ist nicht registriert.
- `https://w3id.org/wlo/curriculum/kern#` ist der Namensraum des alten Andock-Entwurfs und erscheint nur in `migration.ttl`.
- Lizenzvorschlag für Kern, Vokabulare und Profile: CC BY 4.0 (vor Veröffentlichung festzulegen).
- `profile/schule-lexikon-fwu.ttl` und `werkzeuge/quellen/fwu-landesklassen.csv` sind aus der FWU-Lehrplan-Ontologie abgeleitet und stehen unter **CC BY-SA 4.0**.
- Externe Wortlaute (Bildungspläne, Rahmen) sind nicht enthalten; die Beispiele sind fiktiv.
