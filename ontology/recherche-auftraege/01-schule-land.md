# Auftrag 01 – Länder-Steckbrief Schule

**Nutzung:** Einen Lauf je Land. `{LAND}` (z. B. „Nordrhein-Westfalen (DE-NW)“) ersetzen und anhängen:

- `vorlisten/schule-ziele.csv`
- `vorlisten/schule-DE-XX.csv` des Landes
- `vorlisten/schule-DE.csv`
- `vorlisten/schule-ohne-land.csv`

Pilot: NW und SN. Alles zwischen den Linien ist der Auftrag.

---

## Auftrag: Steckbrief der Lehrplandokumente allgemeinbildender Schulen in {LAND}

**Hintergrund.** Wir extrahieren Lehrpläne aller Länder automatisch in ein gemeinsames Modell. Dafür brauchen wir je Land ein genaues Bild davon, wie die Dokumente aufgebaut sind und welche Begriffe, Nummerierungen, Kürzel und Layoutsignale sie verwenden. Es geht um die **Form**, nicht um die Lerninhalte. Angehängt sind:

- die Liste unserer Zielbegriffe (`schule-ziele.csv`);
- die Begriffe, die wir für dieses Land schon kennen (`schule-DE-XX.csv`), für alle Länder (`schule-DE.csv`) und ohne Landesbezug (`schule-ohne-land.csv`). Sie sind teils ungeprüft, teils aus einer Ontologie abgeleitet, die nur einige Länder gut abdeckt.

**Umfang.**

- **Stufen und Schularten:** Primarstufe, Sekundarstufe I (alle Schularten des Landes) und gymnasiale Oberstufe.
- **Fächer exemplarisch:** Deutsch, Mathematik, eine Naturwissenschaft (Physik oder Biologie), ein gesellschaftswissenschaftliches Fach (Geschichte oder Politik/Sozialkunde), Sachunterricht.
- **Weitere Dokumente:** fachübergreifende Teile (Allgemeiner Teil, Grundsatzband, Rahmenplan Teil A/B), Querschnittsrahmen (Medienkompetenz, BNE, Berufsorientierung, Verbraucherbildung, Demokratiebildung), Operatorenlisten, sonderpädagogische Lehrpläne (nur auflisten, Aufbau an einem Beispiel).
- **Fassungen:** die gültigen Fassungen, auslaufende Vorgängerfassungen und laufende Anhörungsfassungen.

**Fragen.**

1. **Dokumente:** Welche Lehrplandokumente gibt es, unter welchem Titel, von wem, in welcher Fassung, seit wann gültig, wodurch abgelöst? Welche Rechtsform und Verbindlichkeit haben sie (Verordnung, Verwaltungsvorschrift, Erlass, Bekanntmachung; verbindlich oder orientierend)? Wo liegen sie (URL des Bildungsservers oder Ministeriums)?
2. **Gliederung:** Welche Ebenenfolge hat jede Dokumentart?
   - Bezeichnungen wörtlich, z. B. „Kompetenzbereich → Inhaltsfeld → Inhaltliche Schwerpunkte → Kompetenzerwartungen“.
   - Wie sind die Ebenen nummeriert (wörtliches Beispiel)?
   - Ist der Plan ein Baum oder eine Matrix (z. B. Kompetenzbereiche × Inhaltsfelder)?
   - Wo stehen Zeitangaben (Jahrgangsstufen, Doppeljahrgänge, Stundenrichtwerte), wo Niveauangaben?
   - Welche Tabellen mit welchen Spaltenköpfen gibt es (wörtlich)?
3. **Begriffe:** Welche Begriffe bezeichnen Dokumentarten, Gliederungsebenen und Aussagearten?
   - Zu den Aussagearten gehören Kompetenzerwartungen/Standards, Inhalte, Hinweise, Verweise, Bildungsziele und Aufträge an Lehrkräfte.
   - Gibt es typische Satzanfänge, Einleitungssätze, Klammern, Fettdruck oder Randspalten?
   - Welche Begriffe sind mehrdeutig oder werden in anderen Ländern anders verwendet?
4. **Querschnitt:** Welche Querschnittsziele oder Leitperspektiven gibt es, wie werden sie im Fachplan markiert (Kürzel, Symbole, Randspalte), und was bedeuten die Kürzel (Legende wörtlich)?
5. **Niveau:** Welche Niveau- oder Stufensysteme verwendet der Plan, und wie sind sie dargestellt? Beispiele: Niveaustufen, Erwartungsniveaus, Kursniveaus, Anforderungsbereiche, Abschlussbezug. Gilt ein System nur für einen Kompetenzbereich (z. B. Hörverstehen, Lesen), steht dieser in `kompetenzbereich`. Auch nicht-kognitive Skalen gehören dazu, wenn der Plan sie nennt: Stufen für Arbeits- und Sozialverhalten, Entwicklungsstufen, Noten oder Punkte in Bewertungsvorgaben.
6. **Schularten:** Wie heißen die Schularten im Land, und welcher KIM-Schulart entsprechen sie (s02 Grundschule … s16 Abendgymnasium)?
7. **Abgleich mit der Vorliste:** Ist jeder Eintrag aus `schule-DE-XX.csv` belegt, zu korrigieren oder nicht auffindbar? Das kommt in Spalte `abgleich_vorliste` von T3, mit `hinweis_id`.

**Ausgabe.** Zuerst eine Zusammenfassung von höchstens einer Seite mit den Besonderheiten des Landes. Dann die Tabellen als CSV-Codeblöcke (Semikolon, Spaltennamen exakt so, eine Tabelle je Block).

- **T1 Dokumente:** `land;dokumenttitel_woertlich;kurzbezeichnung;dokumentart;herausgeber;fassung_datum;gueltig_ab;abgeloest_durch_oder_gueltig_bis;status;rechtsform;verbindlichkeit;geltung_schularten_stufen;faecher_anzahl;url;beleg`
- **T2 Gliederung:** `land;dokumentart;beispieldokument;ebene_1;ebene_2;ebene_3;ebene_4;ebene_5;nummerierung_beispiele;baum_oder_matrix;zeitangaben_wo_wie;niveauangaben_wo_wie;tabellen_spaltenkoepfe;fundstelle;beleg`
- **T3 Begriffe:** `land;begriff_woertlich;fundort;funktion;ziel_id;rolle;erkennungsmerkmal;beispiel_woertlich;fundstelle;gilt_fuer;plangeneration_oder_gueltig_ab;abgrenzung_verwechslung;abgleich_vorliste;hinweis_id;beleg`
- **T4 Querschnitt:** `land;rahmen_titel;kuerzel_oder_symbol;bedeutung_woertlich;markierung_wo;entspricht;fundstelle;beleg`
- **T5 Niveau:** `land;system;stufen_in_reihenfolge;bezug;kompetenzbereich;ziel_id;verwendet_in;darstellung;fundstelle;beleg`
- **T6 Schularten:** `land;bezeichnung_woertlich;kim_schulart;bemerkung;beleg`
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte für die Spalten:**

- **`fundort`:** titel | inhaltsverzeichnis | ueberschrift | tabellenkopf | randspalte | fliesstext | kasten | kopfzeile
- **`bezug`** (T5): abschluss | kompetenzstufe | erwartungsniveau | kursniveau | anforderungsbereich | bewertung | verhalten | entwicklung
- **`funktion`:**
  - `dokumenttyp`
  - `gliederung:grouping`: ordnet nach Stufe/Phase/Teil
  - `gliederung:area`: Bereich ohne Zeitumfang
  - `gliederung:unit`: Einheit mit Zeit/Stunden
  - `gliederung:subunit`: Unterteilung
  - `gliederung:crossCutting`: Querschnittsteil
  - `gliederung:frame`: Rahmenteil wie Fachprofil oder Leitgedanken
  - `aussage:learningOutcome`: Erwartung, Standard des Landes
  - `aussage:developmentGoal`: Bildungsziel ohne Prüfanspruch
  - `aussage:content`: Inhalt, Fachbegriff
  - `aussage:standard`: Regelstandard, Bewertungskriterium
  - `aussage:mandate`: Auftrag an Lehrkräfte oder Schule
  - `aussage:guidance`: Hinweis, Anregung
  - `aussage:reference`: Verweis
  - `niveau`, `zeit`, `verbindlichkeit`, `querschnittsmarker`, `verweismarker`, `sonstiges`
- **`ziel_id`:** eine ID aus `schule-ziele.csv`, sonst `neu`
- **`rolle`:**
  - `pref`: die übliche Bezeichnung;
  - `alt`: echtes Synonym, überall gleichbedeutend;
  - `cue`: Hinweis, kein Synonym;
  - `negative`: sieht ähnlich aus, ist aber etwas anderes;
  - `homonym`: mehrdeutig, Regel in `abgrenzung_verwechslung`
- **`abgleich_vorliste`:** bestaetigt | korrigiert | neu | nicht_gefunden
- **`entspricht` (T4):** BNE | Medienbildung/Digitale Welt | Demokratie | Berufliche Orientierung | Verbraucherbildung | Gesundheit | Vielfalt/Inklusion | Sprachbildung | Interkulturalität | Werte | sonstiges
- **`beleg`:**
  - `E`: am Primärdokument geprüft, mit URL und Seite;
  - `S`: nur Sekundärquelle;
  - `A`: Annahme, ausdrücklich als solche

**Regeln.**

- Primärquellen bevorzugen (Ministerium, Landesinstitut, Bildungsserver, Amtsblatt). Sekundärquellen nur mit `beleg` = S.
- Begriffe, Überschriften und Spaltenköpfe **wörtlich**. Beispiele höchstens einen Satz bzw. 25 Wörter; keine längeren Passagen und keine ganzen Kompetenzlisten.
- Jede Zeile mit Fundstelle (URL + Seite oder Abschnitt).
- **Nichts ergänzen, was nicht belegt ist.** „Nicht gefunden“ und Widersprüche gehören in T7; sie sind ein gültiges Ergebnis.
- Unterschiede zwischen Schularten oder Plangenerationen ausdrücklich trennen (Spalten `gilt_fuer`, `plangeneration_oder_gueltig_ab`).
- Keine Lerninhalte bewerten oder zusammenfassen.

---
