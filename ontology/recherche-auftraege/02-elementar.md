# Auftrag 02 – Länder-Steckbrief Elementarbildung

**Nutzung:** Einen Lauf je Land, also 16 Läufe. Ein Land je Lauf, weil die Pläne 100–500 Seiten haben, mehrere Länder 2024–2026 neue Fassungen eingeführt haben (BB, HH, BW, MV, ST, SH) und die vollständigen Bereichstitel im Wortlaut am Primärdokument geprüft werden sollen. Bei mehreren Ländern je Lauf verteilt sich die Recherchetiefe, und Belege aus Sekundärquellen nehmen zu.

`{LAND}` ersetzen (z. B. „Brandenburg (DE-BB)“) und anhängen:

- `vorlisten/elementar-ziele.csv`
- `vorlisten/elementar-DE-XX.csv` des Landes
- `vorlisten/elementar-DE.csv`
- `vorlisten/elementar-ohne-land.csv`

Pilot: ein Land mit neuer Fassung (z. B. BB 2024) und eines mit altersübergreifendem Plan (z. B. HE oder NW 0–10). Alles zwischen den Linien ist der Auftrag.

---

## Auftrag: Steckbrief der Bildungspläne für Kindertageseinrichtungen in {LAND}

**Hintergrund.** Wir extrahieren die Bildungspläne aller Länder für Kita, Kindertagespflege und Hort automatisch in ein gemeinsames Modell. Dafür brauchen wir für {LAND}:

- den Aufbau der Dokumente;
- die Bezeichnungen der Bildungsbereiche und Leitprinzipien;
- die Formen, in denen Ziele, Aufgaben der Fachkräfte und Reflexionsfragen stehen.

Es geht um die **Form**, nicht um pädagogische Inhalte. Angehängt sind unsere Zielbegriffe (`elementar-ziele.csv`) und die Hinweise, die wir für {LAND} schon haben (`elementar-DE-XX.csv`). Ein Teil davon ist ungeprüft, und Titel neuer Fassungen fehlen teils.

**Fragen.**

1. **Dokumente:**
   - der gültige Bildungsplan: genauer Titel, Herausgeber, Fassung, gültig seit, welche Fassung er ablöst;
   - Rechtsgrundlage und Verbindlichkeit (Gesetz, Verordnung, amtliche Empfehlung nach § 85 SGB VIII, Vereinbarung);
   - Begleitdokumente: U3-Handreichung, Sprachbildung, Übergang Kita–Grundschule, Qualitätsempfehlungen, Beobachtungsinstrumente;
   - ob der Plan altersübergreifend ist (0–10, 0–18) und welche Bildungsorte er nennt (Krippe, Kindergarten, Hort, Kindertagespflege, Grundschule);
   - ob alte und neue Fassung parallel im Umlauf sind und woran man sie unterscheidet (Titel, Jahr, Bereichsnamen).
2. **Gliederung:** Ebenenfolge wörtlich (z. B. „Teil II Bildungsziele → Bildungsbereich → Ziele / Anregungen / Fragen zur Reflexion“), Nummerierung (wörtliches Beispiel), Leitbild- oder Visionsüberschriften über mehreren Bereichen, Tabellen (z. B. Bereich × Dimension, Grundbedürfnisse × Felder) mit Spaltenköpfen.
3. **Bildungsbereiche:** die **vollständige Liste der Bereichstitel wörtlich**, in Dokumentreihenfolge, mit Nummer. Dazu je Bereich die Entsprechung im „Gemeinsamen Rahmen der Länder“ (2004, i. d. F. 2021/2022), laut den Feldern `elem:f-…` in `elementar-ziele.csv`. Bei neuer Fassung beide Listen (alt und neu).
4. **Prinzipien und Querschnitt:** Leitprinzipien, Leitmotive, Querschnittsthemen, Handlungsprinzipien – Titel wörtlich.
5. **Aussageformen:**
   - Ziele für das Kind (Satzanfang wörtlich, z. B. „Das Kind …“, „Kinder …“);
   - Aufgaben der Fachkräfte („Pädagogische Fachkräfte …“);
   - Reflexions- oder Erkundungsfragen, Impulse, Praxisbeispiele, Qualitätsansprüche (Nummerierung, z. B. „QA1“);
   - Entwicklungsangaben mit Altersbezug;
   - ob Ziele als verbindlich ausgewiesen sind.
6. **Kompetenzmodell:** ob ein Basiskompetenz- oder Dimensionsmodell erklärt wird (z. B. Ich-/Sozial-/Sach-/lernmethodische Kompetenz; personale/soziale/sachliche Dimension) und wie es im Dokument erscheint (Kapitel, Tabellenkopf, Randmarke).
7. **Abgleich mit der Vorliste:** jeder Eintrag aus `elementar-DE-XX.csv` bestätigt, korrigiert oder nicht gefunden (mit `hinweis_id`).

**Ausgabe.** Zuerst eine Zusammenfassung von höchstens einer Seite mit den Besonderheiten des Landes. Dann die Tabellen als CSV-Codeblöcke (Semikolon, Spaltennamen exakt so, eine Tabelle je Block).

- **T1 Dokumente:** `land;dokumenttitel_woertlich;kurzbezeichnung;dokumentart;herausgeber;fassung_datum;gueltig_ab;abgeloest_durch_oder_gueltig_bis;status;rechtsform;verbindlichkeit;bildungsorte_altersbereich;url;beleg`
- **T2 Gliederung:** `land;beispieldokument;ebene_1;ebene_2;ebene_3;ebene_4;nummerierung_beispiele;tabellen_spaltenkoepfe;fundstelle;beleg`
- **T3 Begriffe:** `land;begriff_woertlich;fundort;funktion;ziel_id;rolle;erkennungsmerkmal;beispiel_woertlich;fundstelle;gilt_fuer;plangeneration_oder_gueltig_ab;abgrenzung_verwechslung;abgleich_vorliste;hinweis_id;beleg`
  - Bereichstitel stehen hier mit `funktion` = `gliederung:area` und `ziel_id` = Feld `elem:f-…`.
  - Prinzipien mit `funktion` = `gliederung:crossCutting` und `ziel_id` = `elem:p-…` oder `neu`.
- **T4 Querschnitt:** `land;prinzip_oder_thema_woertlich;entspricht;fundstelle;beleg`
- **T5 Kompetenzmodell:** `land;modell_bezeichnung;dimensionen_in_reihenfolge;darstellung;fundstelle;beleg`
- **T6 Bildungsorte:** `land;bezeichnung_woertlich;entspricht;bemerkung;beleg` (`entspricht` = Krippe | Kindergarten | Kita | Kindertagespflege | Hort | Grundschule)
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte:**

- **`fundort`:** titel | inhaltsverzeichnis | ueberschrift | tabellenkopf | fliesstext | kasten
- **`funktion`:** `dokumenttyp`, `gliederung:grouping|area|subunit|crossCutting|frame|nonCurricular`, `aussage:developmentGoal|learningOutcome|content|mandate|standard|guidance|reference`, `kontext` (Alltagssituation), `zeit` (Alter), `sonstiges`
- **`rolle`:**
  - `pref`: die übliche Bezeichnung;
  - `alt`: echtes Synonym;
  - `cue`: Hinweis, kein Synonym;
  - `negative`: sieht ähnlich aus, ist aber etwas anderes;
  - `homonym`: mehrdeutig, Regel in `abgrenzung_verwechslung`
- **`abgleich_vorliste`:** bestaetigt | korrigiert | neu | nicht_gefunden
- **`entspricht` (T4):** Kinderrechte/Partizipation | Inklusion/Vielfalt | Kinderschutz | BNE | Geschlechtersensibilität | Übergänge | Zusammenarbeit mit Familien | Sprachbildung | Gesundheit | Medienbildung | sonstiges
- **`beleg`:**
  - `E`: am Primärdokument geprüft, mit URL und Seite;
  - `S`: nur Sekundärquelle;
  - `A`: Annahme, ausdrücklich als solche

**Regeln.**

- Primärquellen bevorzugen: Ministerium, oberste Landesjugendbehörde, Landesinstitut, Amtsblatt.
- Titel und Begriffe **wörtlich**, auch Schreibvarianten. Beispiele höchstens ein Satz bzw. 25 Wörter; keine längeren Passagen.
- Jede Zeile mit Fundstelle (URL + Seite oder Abschnitt).
- Nichts ergänzen, was nicht belegt ist; „nicht gefunden“ und Widersprüche gehören in T7.

---
