# Auftrag 03 – Berufliche Schulen auf Landesebene (zweistufig)

**Nutzung:** Die Bundesebene (Ausbildungsordnungen, KMK-Rahmenlehrpläne, PflAPrV, Fortbildungsordnungen) ist schon erschlossen. Hier geht es um das, was die **Länder** ergänzen oder anders machen. Wie viel das ist, unterscheidet sich stark und ist vorab nicht bekannt: Manche Länder übernehmen die KMK-Rahmenlehrpläne fast unverändert, andere haben große eigene Lehrplanbestände (NRW-Bildungspläne fürs Berufskolleg, Landeslehrpläne in BW und BY). Deshalb zwei Stufen:

- **Stufe A – Überblick:** ein Lauf über alle 16 Länder. Er klärt die Übernahmepraxis und die eigenen Lehrplanbestände und empfiehlt je Land, ob ein Detaillauf nötig ist (Tabelle T8).
- **Stufe B – Detail:** ein Lauf je Land, nur für Länder mit Empfehlung „ja“. Erwartet sind 5–8.

**Anhänge:**

- **beide Stufen:** `vorlisten/beruf-ziele.csv`, `vorlisten/beruf-ohne-land.csv`
- **Stufe B zusätzlich:** die Länderliste des Landes, falls vorhanden (`vorlisten/beruf-DE-NW.csv`, `vorlisten/beruf-DE-SN.csv`), und die Zeilen des Landes aus den Ergebnissen von Stufe A

Alles zwischen den Linien ist jeweils der Auftrag.

---

## Auftrag A: Überblick berufliche Schulen der 16 Länder

**Hintergrund.** Wir extrahieren Lehrpläne der beruflichen Bildung automatisch in ein gemeinsames Modell. Die Bundesdokumente kennen wir (Ausbildungsordnung mit Ausbildungsrahmenplan, KMK-Rahmenlehrplan). Dieser Lauf soll für **alle 16 Länder** klären:

- wie die KMK-Rahmenlehrpläne übernommen werden;
- welche eigenen Lehrplandokumente es für berufliche Schulen gibt;
- in welchen Ländern sich eine vertiefte Erhebung lohnt.

Es geht um Dokumente und ihre Form, nicht um Inhalte.

**Je Land.**

1. **Übernahme der KMK-Rahmenlehrpläne:** durch Erlass, Verwaltungsvorschrift oder Bekanntmachung? Formel wörtlich, ein Beispiel mit Datum und Fundstelle. Werden die RLP unverändert übernommen oder durch Landeslehrpläne ersetzt bzw. ergänzt (z. B. Bündelungsfächer, eigene Fächer, Stundentafeln, berufsübergreifender Unterricht)?
2. **Eigene Lehrplanbestände je Bildungsgangfamilie:**
   - Berufsschule (über die RLP hinaus);
   - Berufsfachschule, Fachschule (Sozialpädagogik, Technik, Wirtschaft, Gesundheit), Fachoberschule/Berufsoberschule, berufliches Gymnasium, Ausbildungsvorbereitung;
   - je Familie: gibt es eigene Lehrpläne, wie heißen sie (Titelmuster wörtlich), wer gibt sie heraus, ungefähr wie viele, Portal-URL?
3. **Gliederungsprinzip je Familie** in einer Zeile: folgt es dem Lernfeldmuster der KMK, oder hat es eine eigene Struktur (z. B. „Handlungsfeld → Anforderungssituation“, „Fach → Lerngebiet“, Module)? Mit einem wörtlichen Beispiel einer Überschrift.
4. **Empfehlung Detaillauf:** „ja“, wenn mindestens eines gilt:
   - (a) die Berufsschule nutzt eigene Gliederungen über die RLP hinaus (Bündelungsfächer, eigene Fächer);
   - (b) landesrechtliche Bildungsgänge haben eine eigene, vom Lernfeldmuster abweichende Struktur;
   - (c) der Bestand ist so groß oder uneinheitlich, dass er sich nicht über ein Muster erschließen lässt.

   Sonst „nein“: Dann genügen die Angaben dieses Laufs.

**Ausgabe.** Zuerst eine Übersicht von höchstens einer Seite: welche Länder auffallen und warum. Dann die Tabellen als CSV-Codeblöcke (Semikolon, Spaltennamen exakt so):

- **T0 Übersicht:** `land;bildungsgangfamilie;eigene_landesdokumente;titelmuster_woertlich;herausgeber;anzahl_ungefaehr;gliederungsprinzip;ueberschrift_beispiel_woertlich;portal_url;beleg`
- **T1 Übernahme RLP:** `land;art_der_uebernahme;formel_woertlich;beispiel_dokument;datum;fundstelle;beleg`
- **T8 Empfehlung:** `land;detaillauf_empfohlen;kriterium;begruendung;schwerpunkte_fuer_detaillauf`
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte:**

- **`bildungsgangfamilie`:** berufsschule | berufsfachschule | fachschule | fos_bos | berufliches_gymnasium | ausbildungsvorbereitung | sonstige
- **`eigene_landesdokumente`:** ja | nein | teilweise
- **`gliederungsprinzip`:** lernfeld_kmk | eigenes_lernfeld | fach_lerngebiet | handlungsfeld_anforderungssituation | modul | sonstiges
- **`detaillauf_empfohlen`:** ja | nein
- **`kriterium`:** a | b | c (mehrere möglich, kommagetrennt)
- **`beleg`:** E (Primärdokument mit Seite) | S (Sekundärquelle) | A (Annahme)

**Regeln.** Primärquellen (Kultusministerien, Landesinstitute wie QUA-LiS NRW oder ISB Bayern, Bildungsserver, Amtsblätter). Titel und Formeln wörtlich, Beispiele höchstens ein Satz. Nichts ergänzen, was nicht belegt ist; Lücken in T7.

---

## Auftrag B: Lehrplandokumente der beruflichen Schulen in {LAND} (Detail)

**Nutzung:** nur für Länder mit `detaillauf_empfohlen` = ja aus Auftrag A. `{LAND}` ersetzen; die Zeilen des Landes aus T0, T1 und T8 und die Schwerpunkte aus T8 mitgeben.

**Hintergrund.** Wir extrahieren Lehrpläne der beruflichen Bildung automatisch in ein gemeinsames Modell. Für {LAND} brauchen wir die eigenen Lehrplandokumente der beruflichen Schulen: wie sie aufgebaut sind und welche Begriffe, Nummerierungen und Zeitangaben sie verwenden. Es geht um die **Form**, nicht um Inhalte. Angehängt sind unsere Zielbegriffe (`beruf-ziele.csv`), die heutigen Hinweise und die Überblicksergebnisse für {LAND}.

**Fragen.**

1. **Dokumente** je Bildungsgangfamilie (Schwerpunkte laut Überblick zuerst): Titel, Herausgeber, Fassung, Gültigkeit, Rechtsform, Verbindlichkeit, URL. Sind Vorgänger- und Anhörungsfassungen im Umlauf?
2. **Gliederung:**
   - Ebenenfolge wörtlich je Dokumentart, z. B. „Bildungsgang → Fachbereich → Fach → Handlungsfeld → Anforderungssituation → Zielformulierungen“;
   - Nummerierung (wörtliche Beispiele);
   - Lage der Zeitrichtwerte (Stunden je Lernfeld/Fach/Schuljahr, Spannen, Einheit);
   - Tabellen und ihre Spaltenköpfe;
   - Stundentafeln.
3. **Begriffe:**
   - In welcher Bedeutung verwendet das Land Lernfeld, Lernsituation, Bündelungsfach, Anforderungssituation, Handlungsfeld, Lerngebiet, Lernbereich, Fach, Modul, Kompetenzbereich? Welche weiteren eigenen Begriffe gibt es?
   - Werden „Zielformulierung“, „Kernkompetenz“ und „Inhalte“ (kursiv?) so verwendet?
   - Didaktische Jahresplanung: Pflicht? Vorlage?
4. **Kompetenzmodell:** welches Modell die Landespläne erklären (KMK-Handlungskompetenz, DQR-Kategorien, eigenes) und wie es an den Zielen markiert ist.
5. **Verbindlichkeit und Geltung:**
   - Abweichungen und Ergänzungen gegenüber dem KMK-Rahmenlehrplan;
   - Geltung je Fachrichtung oder Schwerpunkt;
   - Wahl- und Differenzierungsbereiche.
6. **Abgleich mit der Vorliste:** jeder Eintrag mit Landesbezug bestätigt, korrigiert oder nicht gefunden (mit `hinweis_id`).

**Ausgabe.** Zuerst eine Zusammenfassung von höchstens einer Seite. Dann die Tabellen als CSV-Codeblöcke (Semikolon, Spaltennamen exakt so):

- **T1 Dokumente:** `land;dokumenttitel_woertlich;bildungsgang;dokumentart;herausgeber;fassung_datum;gueltig_ab;abgeloest_durch_oder_gueltig_bis;status;rechtsform;verbindlichkeit;uebernahme_kmk_rlp;url;beleg`
- **T2 Gliederung:** `land;dokumentart;beispieldokument;ebene_1;ebene_2;ebene_3;ebene_4;ebene_5;nummerierung_beispiele;zeitangaben_wo_wie;tabellen_spaltenkoepfe;fundstelle;beleg`
- **T3 Begriffe:** `land;begriff_woertlich;fundort;funktion;ziel_id;rolle;erkennungsmerkmal;beispiel_woertlich;fundstelle;gilt_fuer;plangeneration_oder_gueltig_ab;abgrenzung_verwechslung;abgleich_vorliste;hinweis_id;beleg`
- **T5 Kompetenzmodell:** `land;modell_bezeichnung;dimensionen;markierung_an_zielen;fundstelle;beleg`
- **T6 Bildungsgänge:** `land;bezeichnung_woertlich;schulform;abschluss;dauer;kim_schulart;beleg`
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte:**

- **`funktion`:** `dokumenttyp`, `gliederung:grouping|area|unit|subunit|crossCutting|frame`, `aussage:learningOutcome|content|developmentGoal|standard|mandate|guidance|reference`, `zeit`, `verbindlichkeit`, `lernort`, `sonstiges`
- **`rolle`:** pref | alt | cue | negative | homonym (Bedeutung wie in Auftrag 01)
- **`fundort`:** titel | inhaltsverzeichnis | ueberschrift | tabellenkopf | randspalte | fliesstext
- **`abgleich_vorliste`:** bestaetigt | korrigiert | neu | nicht_gefunden
- **`beleg`:** E | S | A

**Regeln.**

- Primärquellen bevorzugen.
- Begriffe wörtlich, Beispiele höchstens ein Satz.
- Stunden immer mit Einheit (Unterrichtsstunden ≠ Zeitstunden).
- Nichts ergänzen, was nicht belegt ist; Lücken in T7.

---
