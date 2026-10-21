# Auftrag 06 – Querschnittsrahmen, Abschlüsse, Niveaus und Schularten (alle Länder)

**Nutzung:** Ein Lauf für alle 16 Länder. Bei zu viel Stoff zwei Läufe: A Querschnitt, B Abschlüsse/Niveaus/Schularten. Anhängen: `vorlisten/schule-ziele.csv`. Die Ergebnisse speisen die gemeinsamen Vokabulare `qz:` (Querschnitt), `lvl:` (Niveau) und die Schularten des Profils `schul:`. Alles zwischen den Linien ist der Auftrag.

---

## Auftrag: Querschnittsrahmen, Abschlüsse, Niveaus und Schularten der 16 Länder

**Hintergrund.** Wir verknüpfen Lehrpläne aller Länder über gemeinsame Querschnittsziele (BNE, Medienbildung, Demokratie, Berufliche Orientierung …) und Niveausysteme. Dafür brauchen wir je Land die amtlichen Rahmen und ihre Markierungen in den Fachplänen, die Bezeichnungen der Abschlüsse und Kursniveaus und die Schularten.

**A. Querschnitt (je Land):**

1. Welche **fachübergreifenden Rahmen** gelten? Medienkompetenzrahmen, BNE-Orientierungsrahmen, Leitperspektiven, Aufgabengebiete, übergreifende Themen, Verbraucherbildung, Berufs- und Studienorientierung, Demokratiebildung, Sprachbildung. Gefragt sind Titel, Fassung und Gültigkeit.
2. Wie sind die Rahmen **gegliedert**: Kompetenzbereiche mit Nummern und Titeln wörtlich, z. B. „1 Bedienen und Anwenden“?
3. Wie werden sie **in Fachplänen markiert**: Kürzel, Symbole, Randspalten, Klammern? Gibt es die Legende wörtlich?
4. Welchem **KMK-Rahmen** entsprechen sie? Gemeint sind „Bildung in der digitalen Welt“ (2016/2021) und der Orientierungsrahmen Globale Entwicklung bzw. BNE.

**B. Abschlüsse und Niveaus (je Land):**

1. **Bezeichnungen der Schulabschlüsse** wörtlich: erster Abschluss, erweiterter erster Abschluss, mittlerer Abschluss, Fachhochschulreife, allgemeine Hochschulreife. Mit Rechtsgrundlage.
2. **Differenzierungs- und Kursniveaus** in der Sekundarstufe I (z. B. G/E-Kurs, G/M/E, grundlegendes/erweitertes Niveau, Fettdruck für E-Kurs) und in der Oberstufe (grundlegendes/erhöhtes Anforderungsniveau, Leistungs-/Grundkurs). Gesucht ist, wie sie in Lehrplänen dargestellt sind.
3. **Weitere Stufensysteme** in Lehrplänen: Niveaustufen, Erwartungsniveaus, Mindest- und Regelanforderungen. Gilt ein System nur für einen Kompetenzbereich, steht dieser in `kompetenzbereich`. Skalen für Noten und für Arbeits- und Sozialverhalten erhebt Auftrag 07.

**C. Schularten (je Land):** alle Schularten wörtlich, mit Stufen und Entsprechung in den KIM-Schularten (s02 Grundschule, s03 Hauptschule, s04 Realschule, s05 Gesamtschule, s06 Förderschule, s07 Oberschule, s08 Gymnasium, s09 Gemeinschaftsschule, s10 Sekundarschule, s11 Berufsfachschule, s12 Berufsschule, s13 Fachoberschule, s14 berufliches Gymnasium, s15 Privat-/Ersatzschule, s16 Abendgymnasium) oder „keine“.

**Ausgabe.** Kurze Übersicht der Besonderheiten. Dann CSV-Codeblöcke (Semikolon, Spaltennamen exakt so):

- **T4 Querschnitt:** `land;rahmen_titel_woertlich;fassung_datum;bereich_nr;bereich_titel_woertlich;kuerzel_oder_symbol;markierung_wo;entspricht_kmk;entspricht;url;beleg`
- **T5 Niveau:** `land;system;stufen_in_reihenfolge_woertlich;bezug;kompetenzbereich;ziel_id;schularten_stufen;darstellung_in_lehrplaenen;rechtsgrundlage;fundstelle;beleg`
- **T6 Schularten:** `land;bezeichnung_woertlich;stufen;kim_schulart;bemerkung;beleg`
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte:**

- **`entspricht`:** BNE | Medienbildung/Digitale Welt | Demokratie | Berufliche Orientierung | Verbraucherbildung | Gesundheit | Vielfalt/Inklusion | Sprachbildung | Interkulturalität | Werte | Europa | Mobilität | sonstiges
- **`bezug`:** abschluss | kompetenzstufe | erwartungsniveau | kursniveau | anforderungsbereich | bewertung | verhalten | entwicklung
- **`beleg`:** E (Primärdokument mit Seite) | S (Sekundärquelle) | A (Annahme)

**Regeln.** Primärquellen; Titel, Bereichsnamen und Kürzel wörtlich; keine Kompetenzbeschreibungen abschreiben; nichts ergänzen, was nicht belegt ist; Lücken in T7.

---
