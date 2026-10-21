# Auftrag 04 – Hochschule: Landesrecht, Ordnungsbezeichnungen, Modulhandbuch-Felder

**Nutzung:**

- **Lauf A** (alle 16 Länder): Landesrecht und Bezeichnungen.
- **Lauf B** (optional): Stichprobe von Modulhandbüchern. Er zeigt die Spannweite der Feldnamen und Layouts, die in der Praxis stärker variieren als zwischen Ländern.

Anhängen:

- `vorlisten/hochschule-ziele.csv`
- `vorlisten/hochschule-ohne-land.csv` (Feldlexikon, 400 Einträge, überwiegend ungeprüft)
- `vorlisten/hochschule-DE-*.csv`

Alles zwischen den Linien ist der Auftrag.

---

## Auftrag A: Landesrecht und Ordnungsbezeichnungen für Studiengänge (alle Länder)

**Hintergrund.** Wir extrahieren Studien- und Prüfungsordnungen, Modulhandbücher und Studienverlaufspläne automatisch. Dafür brauchen wir je Land:

- welche Pflichtangaben für Modulbeschreibungen gelten;
- wie die Ordnungen typischerweise heißen;
- welche Sonderregeln die Struktur prägen (Anrechnung, Lehramt, Hochschularten).

**Je Land.**

1. **Studienakkreditierungsverordnung** des Landes (Umsetzung der Musterrechtsverordnung): Titel, Fassung, gültig ab. Ist die MRVO-Fassung 2024 schon umgesetzt, und wann? Welche Pflichtangaben für Modulbeschreibungen nennt § 7 bzw. die entsprechende Norm (wörtliche Aufzählung)? Gibt es Übergangsregeln?
2. **Hochschulgesetz:** Anrechnungsregeln (Obergrenze außerhochschulisch erworbener Kompetenzen, Wortlaut der Norm), Hochschularten (Universität, HAW/FH, Technische Hochschule, Duale Hochschule/Berufsakademie, Pädagogische Hochschule, Kunst-/Musikhochschule), Regelstudienzeiten.
3. **Ordnungsbezeichnungen:** übliche Titel und Kurzformen (z. B. SPO, FPSO, StuPO, APO, RPO, FSB, „Besonderer Teil“) und wie Rahmen- und Fachordnung zusammenspielen. Wo werden Ordnungen veröffentlicht (Amtliche Mitteilungen, Verkündungsblatt)? Mit welchen Bekanntmachungsformeln?
4. **Lehramt:** Rechtsgrundlagen (Lehrerbildungsgesetz, LPO, LZV, LABG …), Lehramtstypen, Begriffe (Unterrichtsfach, Bildungswissenschaften, Praxissemester).
5. **Abgleich:** Einträge der Vorliste mit Landesbezug bestätigen oder korrigieren (`hochschule-DE-*.csv`).

**Ausgabe.** Zusammenfassung von höchstens einer Seite, dann die Tabellen als CSV-Codeblöcke (Semikolon):

- **T1 Rechtsgrundlagen:** `land;norm_titel_woertlich;kurzbezeichnung;art;fassung_datum;gueltig_ab;mrvo_fassung_umgesetzt;pflichtangaben_modul_woertlich;anrechnung_obergrenze_woertlich;url;beleg`
- **T3 Begriffe:** `land;begriff_woertlich;fundort;funktion;ziel_id;rolle;erkennungsmerkmal;beispiel_woertlich;fundstelle;gilt_fuer;abgrenzung_verwechslung;abgleich_vorliste;hinweis_id;beleg`
- **T6 Hochschularten:** `land;bezeichnung_woertlich;entspricht;bemerkung;beleg` (`entspricht` = Universität | HAW | Duale Hochschule/BA | PH | Kunst/Musik | Verwaltung | Theologie)
- **T7 Lücken:** `land;thema;befund;quelle`

## Auftrag B (optional): Felder und Layout von Modulhandbüchern – Stichprobe

**Stichprobe:** 12 Modulhandbücher, geschichtet:

- 4 Universitäten, 4 HAW, 1 Duale Hochschule, 1 PH, 1 Kunst-/Musikhochschule, 1 weiterbildender Studiengang;
- mindestens 6 Länder;
- je ein englischsprachiges.

**Je Modulhandbuch:**

- **Feldnamen** des Modulsteckbriefs wörtlich, in Reihenfolge, mit Zuordnung zu `hochschule-ziele.csv` bzw. zu den Feldern der Vorliste (Lernergebnisse, Inhalte, Lehrformen, Voraussetzungen, Verwendbarkeit, LP-Vergabe, LP, Workload, Turnus, Dauer, Prüfungsform);
- Modulcode-Muster (wörtliche Beispiele);
- Tabellen- oder Fließtextlayout;
- wie Lehrveranstaltungen unter Modulen stehen;
- ob das MHB Anlage der Ordnung ist (Formel wörtlich).

**Ausgabe:**

- `T3 Begriffe` wie oben, mit `gilt_fuer` = Hochschulart und Hochschule.
- **T8 Modulhandbücher:** `hochschule;land;hochschulart;studiengang;mhb_titel;feldnamen_in_reihenfolge;modulcode_beispiele;layout;anlage_formel_woertlich;url;beleg`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte und Regeln (A und B):**

- **`funktion`:** `dokumenttyp`, `gliederung:grouping|area|unit|subunit|frame`, `feld` (Feld des Modulsteckbriefs), `aussage:learningOutcome|content|reference|guidance`, `regel`, `zeit`, `verbindlichkeit`, `sonstiges`
- **`rolle`:** pref | alt | cue | negative | homonym
- **`beleg`:** E | S | A
- Primärquellen (Landesrecht, amtliche Mitteilungen der Hochschulen). Begriffe wörtlich, Beispiele höchstens ein Satz. Keine Personennamen (Modulverantwortliche) übernehmen. Lücken in T7.

---
