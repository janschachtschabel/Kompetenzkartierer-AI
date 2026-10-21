# Auftrag 07 – Noten- und Verhaltensskalen aus dem Zeugnisrecht (je vier Länder)

**Nutzung:** Vier Läufe zu je vier Ländern: A BW, BY, BE, BB · B HB, HH, HE, MV · C NI, NW, RP, SL · D SN, ST, SH, TH. Lauf D prüft zusätzlich den Wortlaut der „Modi der Weltaneignung“ im Thüringer Bildungsplan bis 18 Jahre (Frage 4). Anhängen: `vorlisten/schule-ziele.csv`. Die Ergebnisse speisen die Niveau-Arten `grading` (Noten, Notenpunkte), `conduct` (Arbeits- und Sozialverhalten) und `development` (Entwicklungsstufen) in `lvl:`. Alles zwischen den Linien ist der Auftrag; `XX` durch die vier Länderkürzel ersetzen.

---

## Auftrag: Noten- und Verhaltensskalen der Länder XX

**Hintergrund.** Wir beschreiben Niveaus nicht nur kognitiv. Für das Arbeits- und Sozialverhalten gibt es in der Schule eigene Skalen. Sie stehen meist nicht im Lehrplan, sondern in Schul-, Zeugnis- und Prüfungsordnungen. Wir brauchen sie je Land wörtlich, mit Rechtsgrundlage, damit wir sie als eigene Skalen anlegen und nie mit Lernzielen vermischen.

**Fragen je Land:**

1. **Notenstufen:** Gelten die sechs Notenstufen „sehr gut“ bis „ungenügend“ (KMK-Beschluss vom 03.10.1968)? Wo stehen sie im Landesrecht, mit Paragraf und Fassung? Welche Abweichungen gibt es: Tendenzen (+/−), Notenpunkte 0–15 in der Oberstufe, Punkte oder Noten an beruflichen Schulen? Ab welcher Jahrgangsstufe gibt es Noten, und was steht vorher auf dem Zeugnis (Bericht, Lernentwicklungsbericht)?
2. **Arbeits- und Sozialverhalten:** Gibt es Kopfnoten oder eine Bewertung von Arbeits- und Sozialverhalten? Wenn ja:
   - Bereiche wörtlich (z. B. Betragen, Fleiß, Mitarbeit, Ordnung, Arbeitsverhalten, Sozialverhalten);
   - Stufen wörtlich in Reihenfolge;
   - Form: Note, Stufenwort, Ankreuzraster oder freier Text;
   - Jahrgänge und Schularten;
   - ob die Bewertung auf dem Abschluss- oder Abgangszeugnis steht;
   - Rechtsgrundlage mit Paragraf und Fassung. Gab es in den letzten Jahren eine Abschaffung oder Wiedereinführung, mit Datum?
3. **Überfachliche Kompetenzen im Zeugnis:** Gibt es amtliche Raster oder Ankreuzbögen mit Stufen für überfachliche Kompetenzen (z. B. im Lernentwicklungsbericht der Gemeinschaftsschule)? Bereiche und Stufen wörtlich.
4. **Nur Lauf D (TH):** „Modi der Weltaneignung“ im Thüringer Bildungsplan bis 18 Jahre: Modi wörtlich in Dokumentreihenfolge, mit Seite. Beschreibt der Plan sie als Stufenfolge (eine baut auf der anderen auf) oder als nebeneinander stehende Weisen? Gibt es einen Bezug zu Alter oder Entwicklungsphase?

**Ausgabe.** Zuerst eine kurze Zusammenfassung je Land. Dann die Tabellen als CSV-Codeblöcke (Semikolon, Spaltennamen exakt so, eine Tabelle je Block):

- **T1 Rechtsgrundlagen:** `land;norm_titel_woertlich;kurzbezeichnung;fassung_datum;gilt_fuer_schularten_stufen;paragrafen;url;beleg`
- **T2 Skalen:** `land;skala_art;bereich_woertlich;stufen_in_reihenfolge_woertlich;form;jahrgaenge_schularten;auf_abschlusszeugnis;ziel_id;rechtsgrundlage_paragraf;fundstelle;beleg`
- **T8 Modi (nur Lauf D):** `land;modus_woertlich;position;beschreibung_kurz;altersbezug;als_stufenfolge;fundstelle;beleg`
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte:**

- **`skala_art`:** notenstufen | notenpunkte | verhalten | ueberfachlich | entwicklung | sonstiges
- **`form`:** note | stufenwort | ankreuzraster | text | punkte
- **`auf_abschlusszeugnis`:** ja | nein | unklar
- **`als_stufenfolge`:** ja | nein | unklar
- **`ziel_id`:** für Notenstufen die Stufen `lvl:grade-1` … `lvl:grade-6`, für Notenpunkte die Stufen `lvl:points-00` … `lvl:points-15` (so stehen sie in der Zielliste); für Verhaltens-, überfachliche und Entwicklungsskalen `neu`.
- **`beleg`:** E (Primärdokument mit Seite oder Paragraf) | S (Sekundärquelle) | A (Annahme)

**Regeln.** Primärquellen: Schulgesetz, Schul-, Zeugnis- und Prüfungsordnungen, Amtsblätter, Zeugnisvordrucke der Ministerien. Landesrechtsportale liefern oft keinen Text, weil die Seite per Script aufgebaut wird. Dann helfen Amtsblatt-PDFs, Landtagsdrucksachen und die Bildungsserver; der Beleg ist dann S, wenn der Normtext selbst nicht gelesen wurde. Keine Anmeldungen und keine Formulare. Bereichs- und Stufenbezeichnungen wörtlich; keine Bewertungstexte über Schülerinnen und Schüler abschreiben; nichts ergänzen, was nicht belegt ist; Lücken in T7.

---
