# Auftrag 05 – Erwachsenen- und Weiterbildung

**Nutzung:**

- **Lauf A:** Landesrecht der 16 Länder.
- **Lauf B:** bundesweite Rahmendokumente – aktuelle Fassungen, Aufbau, Begriffe. Er kann allein laufen, wenn die Zeit knapp ist; die Länder unterscheiden sich in der EB vor allem rechtlich.

Anhängen:

- `vorlisten/erwachsenenbildung-ziele.csv`
- `vorlisten/erwachsenenbildung-ohne-land.csv`
- für Lauf A die `erwachsenenbildung-DE-*.csv`

Alles zwischen den Linien ist der Auftrag.

---

## Auftrag A: Landesrecht der Erwachsenen- und Weiterbildung (alle Länder)

**Je Land:**

1. **Weiterbildungs- bzw. Erwachsenenbildungsgesetz:** Titel, Fassung, Anerkennung von Trägern und Einrichtungen, Programmbereiche oder Pflichtangebote, Statistik- oder Berichtspflichten mit Programmbereichsgliederung.
2. **Bildungsfreistellung/Bildungsurlaub/Bildungszeit:** Gesetzesname, Bezeichnung im Gesetz, Anerkennungsverfahren für Veranstaltungen (Formel auf Kursausschreibungen wörtlich, z. B. „anerkannt nach …“), Ausnahmen (Länder ohne Gesetz).
3. **Landesprogramme** mit eigenen Curricula oder Rahmenvorgaben (Grundbildung/Alphabetisierung, Schulabschlüsse im zweiten Bildungsweg, Integration): Titel, Herausgeber, Aufbau.
4. **Abgleich:** die Länderhinweise der Vorliste (Bildungszeit, Bildungsurlaub, Arbeitnehmerweiterbildung, Bildungsfreistellung) bestätigen oder korrigieren.

**Ausgabe** als CSV-Codeblöcke (Semikolon):

- **T1 Dokumente:** `land;titel_woertlich;art;fassung_datum;gueltig_ab;inhalt_kurz;url;beleg`
- **T3 Begriffe:** `land;begriff_woertlich;fundort;funktion;ziel_id;rolle;erkennungsmerkmal;beispiel_woertlich;fundstelle;gilt_fuer;abgrenzung_verwechslung;abgleich_vorliste;hinweis_id;beleg`
- **T7 Lücken:** `land;thema;befund;quelle`

## Auftrag B: Bundesweite Rahmendokumente der EB – aktuelle Fassungen und Aufbau

**Dokumente:**

- BAMF: Rahmencurriculum für Integrationskurse Deutsch als Zweitsprache, Konzept für einen bundesweiten Integrationskurs, Curriculum Orientierungskurs, Rahmencurricula bzw. Konzept der Berufssprachkurse (Basis- und Spezialmodule), Alphabetisierungskurs-Konzept;
- DVV-Rahmencurricula Lesen, Schreiben, Rechnen (und Nachfolger), lea.-Kompetenzmodell (Alpha-Level);
- telc- bzw. Goethe-Prüfungsziele/Testhandbücher (nur Aufbau);
- GER mit Begleitband (deutsche Fassung);
- GRETA-Kompetenzmodell;
- DigComp 3.0 (deutsche Fassung, falls vorhanden).

**Je Dokument:**

- Titel, Herausgeber, Fassung, gültig seit, Vorgängerfassung;
- **Gliederung** wörtlich mit Nummerierungsbeispielen, z. B. die 12 Handlungsfelder und die übergreifenden Kommunikationsbereiche A–E des Integrationskurses mit Titeln wörtlich, Teilbereiche, sprachliche Handlungen;
- Tabellenspalten wörtlich (Lernziele, Aktivitäten, Niveau, Handlungsziele, Fokus …);
- Erklärung zur Niveauzuordnung wörtlich (z. B. Zuordnung zur niedrigsten möglichen Stufe);
- Umfangsangaben (UE, Minuten je UE, Kursabschnitte);
- Lizenz bzw. Nutzungsbedingungen der Deskriptoren.

**Ausgabe** als CSV-Codeblöcke (Semikolon):

- **T1 Dokumente:** `dokument_titel_woertlich;herausgeber;fassung_datum;gueltig_ab;vorgaenger;lizenz_nutzung;url;beleg`
- **T2 Gliederung:** `dokument;ebene_1;ebene_2;ebene_3;ebene_4;nummerierung_beispiele;tabellen_spaltenkoepfe;niveau_erklaerung_woertlich;umfang_angaben;fundstelle;beleg`
- **T3 Begriffe:** wie in Auftrag A, `land` = DE
- **T9 Listen:** `dokument;liste;nr;titel_woertlich;fundstelle;beleg` – die Handlungsfelder, Kommunikationsbereiche, Module und Alpha-Level, vollständig und wörtlich
- **T7 Lücken:** `land;thema;befund;quelle`

**CSV-Regeln (für die maschinelle Übernahme):**

- Das Semikolon trennt nur Spalten. **Innerhalb eines Feldes nie ein Semikolon**; mehrere Werte im selben Feld mit „ | “ trennen.
- Jede Zeile hat genau so viele Felder wie die Kopfzeile. Fehlt ein Wert, bleibt das Feld leer.
- Feste Werte genau so schreiben wie unten angegeben, ohne Umlaute (`bestaetigt`, nicht „bestätigt“).
- `ziel_id` nur mit einer `id` aus der angehängten Zielliste oder `neu`; keine IDs erfinden. Mehrere Ziele mit „ | “.

**Feste Werte und Regeln (A und B):**

- **`funktion`:** `dokumenttyp`, `gliederung:grouping|area|unit|subunit|crossCutting|frame`, `aussage:learningOutcome|developmentGoal|content|standard|guidance|reference`, `niveau`, `zeit`, `kontext`, `anerkennung`, `sonstiges`
- **`rolle`:** pref | alt | cue | negative | homonym
- **`beleg`:** E | S | A
- Primärquellen; Titel und Begriffe wörtlich; **keine Deskriptor- oder Kann-Beschreibungs-Listen abschreiben**, nur Titel, Struktur und je Typ ein kurzes Beispiel; Lücken in T7.

---
