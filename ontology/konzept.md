# Curriculum-Kern 1.0 – Konzept für Extraktion, Andocken und Bildungslandkarte

Stand: 19.10.2026 · Status: Entwurf zur Entscheidung · Ergebnis zu den Recherche-Ontologien in `docs/recherche/ontologien/`

---

## 0. Kurzfassung

Die App extrahiert Lehrpläne bereits gut. Was fehlt, ist ein **gemeinsames Modell**, an dem die Pläne aller Länder und Bildungsbereiche so andocken, dass Kanten zwischen ihnen entstehen können: gleiches Thema, gleiche Kompetenz, höhere Stufe, Lernortkooperation, Anrechnung. Die fünf Bereichsrecherchen (Elementar, Schule, Beruf, Hochschule, Erwachsenenbildung) haben unabhängig voneinander ähnliche Lösungen gefunden. Sie nutzen aber sechs verschiedene `cur:`-/`cc:`-Namensräume, widersprüchliche Begriffe und unterschiedliche Vorstellungen davon, was eine Aussage, ein Niveau oder eine Kante ist.

Dieses Konzept führt sie zu **einem Kern mit fünf Profilen** zusammen:

1. **Drei Schichten mit getrennter Herkunft.**
   - **L1 Extraktion:** Dokument, Spezifikation, Gliederung, wörtliche Aussage mit Fundstelle. Nur was im Text steht.
   - **L2 Analyse:** Zerlegung in Handlung × Gegenstand × Bedingung, Konzepte als Hubs, Niveau, Zeit. Neu ausführbar.
   - **L3 Graph:** Zuordnungen als eigene Knoten mit Kantenart, Herkunft, Prüfstand, Methode und Konfidenz. Kurzform-Tripel entstehen nur für Bestätigtes oder Amtliches.

   Die Schichten trennen, **was gespeichert wird und woher es stammt**, nicht, was das Modell beim Lesen sieht. Das Modell liest möglichst das ganze Dokument (wie heute in der App: Dokument als gecachter Präfix, der Auftrag je Einheit dahinter) und antwortet für eine Einheit. Gespeichert werden der Wortlaut und die Fundstelle; die Deutung kommt in L2.
2. **Acht Andockpunkte**, alle nach demselben Muster gebaut: Wortlaut-Eigenschaft + Norm-Eigenschaft + Hub + Vererbungsweg + Stufe. Die acht sind Inhalt und Thema, Kompetenz, Niveau, Fach/Feld, Zeit und Geltung, Querschnitt, Kontext und Adressat. Fehlt eine Angabe im Dokument, steht `cur:checkedAbsent` da; geraten wird nie.
3. **Länder und Dokumente sind Daten, keine Klassen.** Ein Lexikon (`cur:LexicalCue`) mit fünf Rollen (pref, alt, cue, negative, homonym) beschreibt, wie Begriffe erkannt werden. Jeder Hinweis trägt Muster, Stärke und Geltung (Land, Dokumenttyp, Plangeneration, Gültigkeit). Ins Prompt geht nur das aktive Profil eines Dokuments. Das Paket enthält 1 265 Hinweise.
4. **Standards sind auch Spezifikationen.** Bildungsstandards, GER, DigComp, lea. und GRETA werden einmal als `cur:CompetencyFramework` importiert: Kriterien-Knoten × niveaugebundene Standard-Aussagen. Curricula docken mit denselben Kanten und Regeln an wie an andere Curricula. Das ist das generische Andocksystem für Kompetenzraster.
5. **Die Pipeline ist zum größten Teil deterministisch.** Ein LLM arbeitet nur in X1, X3, X4 (X6 wiederholt X4 für Fehlerfälle), N1 und G1, jeweils mit einem strikten JSON-Schema. Dessen Enums werden aus dem Vokabular erzeugt. Das Modell liefert Block-IDs und Wortlaut, nie Seitenzahlen oder Konfidenzen.

**Empfehlung:** Den Kern neu aufsetzen und die Infrastruktur der App übernehmen: Konvertierung, Block-/Ankerlogik, Zitatprüfung, Jobs, Review-Oberfläche, Replay. Die bisherigen Profile und Prompts werden auf den Kern migriert, nicht weitergepflegt. Abwärtskompatibilität ist kein Ziel.

**Prüfstand des Pakets** (`pruefung/pruefe.py`, ohne Netz):

- 21 Modelldateien mit 25 011 Tripeln parsen fehlerfrei; kein verwendeter Term ist undefiniert.
- 161 Musterbeispiele der Lexikonhinweise treffen bzw. treffen nicht wie erwartet.
- Die Enums der sechs JSON-Schemas stimmen mit den Vokabularen überein (28 Enum-Felder geprüft).
- Vier Positivbeispiele sind SHACL-konform.
- Zwei Negativbeispiele lösen genau die 18 erwarteten Violations und 11 erwarteten Warnungen aus.
- Sechs Anwendungsfall-Abfragen finden auf den Beispielen Ergebnisse.

---

## 1. Ausgangslage und Grenzen des bisherigen Konzepts

Der Andock-Entwurf (`curricula-andocken/`) hat die richtigen Fragen gestellt: vier Ebenen, sechs Andockpunkte, Stufen 0–7, Kantenarten, Anwendungsfälle. Bei der Umsetzung in fünf Bereichen sind seine Grenzen sichtbar geworden.

| Grenze | Folge | Antwort im Kern 1.0 |
|---|---|---|
| Ein Dokument = ein Curriculum | 0–10-Pläne, Sammelverordnungen, Kita-Pläne mit Krippe/Hort, SPO + MHB + Verlaufsplan passen nicht | `cur:Specification` n:m zu `cur:Document`; Teile gelten über `cur:appliesTo` für mehrere Spezifikationen |
| Aussagetypen ohne Adressat | Fachkraft- und Lehrkraftaufträge docken als Kompetenzen an | Pflichtfeld `cur:addressee`; nur Lernende docken an Kompetenzkonzepte und an AMB `teaches` |
| Niveau als eine Skala | AFB, Bloom, DQR, GER, BE/BB A–H, G/M/E und Abschlüsse werden vermischt; das Ausbildungsjahr wird Niveau | n-äre `cur:LevelAssignment` mit Dimension, Relation und Ordnung; Zeit ist kein Niveau; DQR nur an der Qualifikation |
| Kanten als einfache Tripel | Keine Unterscheidung „vorgeschlagen“/„bestätigt“/„amtlich“, keine Methode, keine Konfidenz | `cur:Alignment` als Knoten; Herkunft × Prüfstand × Methode; Kurzform nur bei bestätigt/amtlich |
| `cur:folgtAuf` = Dokumentreihenfolge, gemappt auf CASE `precedes` | Falsche Lernpfade | `cur:position` (Dokument) ≠ `rel_precedes` (ausdrücklich didaktisch) ≠ `rel_requires` ≠ `rel_revisits` |
| `cur:breiter` closeMatch `ceasn:broadAlignment` | Richtung vertauscht | Kantenarten mit SKOS-Richtung; CTDL-Abbildung im Alignment-Modul geprüft |
| Länderbegriffe als altLabels | „Bildungsplan“ wird Synonym von „Lehrplan“, „Lernbereich“ bedeutet in SN, BY und NRW Verschiedenes | Lexikon mit Rollen, Geltung und Homonym-Regeln |
| Keine Rahmenteile | Die Hälfte eines Kita-Plans und Teile I–IV eines RLP haben keinen Platz | Funktion `frame` und `nonCurricular`, Extraktionstiefe je Knotentyp |
| Sechs Kern-Namensräume in den Recherchen | Nicht kombinierbar | Ein Kern `cur:`, ein Kernvokabular `cv:`, Migrationstabelle `ontologie/migration.ttl` |

---

## 2. Ziele und Anforderungen

**Langfristiges Ziel:** eine Bildungslandkarte für vier Anwendungsfälle.

1. **Themensuche über Bildungsbereiche.** Was lernt man zu einem Thema in Kita, Schule, Ausbildung, Studium und Weiterbildung?
2. **Lehrpläne vergleichen.** Land A mit Land B, Fassung alt mit Fassung neu, Rahmenlehrplan mit Ausbildungsrahmenplan.
3. **Inhalte mit Lehrplänen verknüpfen.** Lernressourcen (WLO, AMB) mit Kompetenzen und Aussagen verknüpfen.
4. **Lernpfade ermitteln.** Was baut worauf auf, was setzt was voraus, was ist anrechenbar?

**Anforderungen an die Ontologie:**

| Anforderung | Umsetzung |
|---|---|
| Top-down extrahierbar mit wenig Aufwand | Gerüst deterministisch (Inhaltsverzeichnis, Layout, Lexikon); LLM nur für Typ-Entscheidungen und Aussagen; Aussagen sind Blätter; das Modell liest das ganze Dokument (gecacht) und antwortet je Einheit |
| Anpassbar an Länder und Dokumente | Lexikon mit Geltung (Land, Dokumenttyp, Plangeneration, Träger, Fach); `cur:DocumentProfile` je Dokument (eigene Begriffe, Tabellenschema) |
| Einheitliche Andockpunkte schon bei der Extraktion | Acht Andockpunkte; die Wortlaut-Felder (Zeit, Niveau, Kontext, Querschnittsmarker, Verweis) füllt X4 gleich mit |
| Generisches Andocken von Kompetenzstandards | Rahmen als `cur:CompetencyFramework` im selben Modell; Kanten wie zwischen Curricula |
| Belegbarkeit | Jede Aussage hat eine Fundstelle (Block-ID, Seite, Zitat, Fundart); amtliche Kanten brauchen eine Fundstelle |
| Wiederholbarkeit | L2 und L3 sind neu ausführbar; Läufe (`cur:ExtractionRun`) mit Modell, Prompt- und Profilversion |
| Kein Raten | `cur:checkedAbsent` je Andockpunkt; `cv:kind_unclassified`; `cv:obl_unknown` |

---

## 3. Leitprinzipien

1. **Wortlaut ≠ Deutung ≠ Zuordnung.** Eine Aussage speichert den Text, wie er dasteht. Zerlegung, Konzepte und Niveau-Heuristiken sind L2, Kanten L3. Jede Schicht hat ihre eigene Herkunft. Das betrifft die Speicherung, nicht den Lesekontext: Auch eine L1-Antwort entsteht mit Blick auf das ganze Dokument (Abschnitt 13.1).
2. **Funktion vor Name.** Ein „Standard“ im Berliner Rahmenlehrplan ist eine Kompetenzerwartung, ein „Standard“ der KMK ist ein Regelstandard. Maßgeblich sind `cur:statementKind` und `cur:nodeFunction`, die Bezeichnung steht im Lexikon.
3. **Ein Knoten, viele Geltungen.** Gemeinsame Teile werden einmal angelegt und per `cur:appliesTo` geteilt. Module werden einmal beschrieben und per `cur:Placement` mehrfach verwendet.
4. **Aussagen sind Blätter.** Ein Inhalt unter einer Erwartung ist ein Geschwisterknoten mit `cur:targetsContent`, kein Kind.
5. **Fehlen ist eine Angabe.** `cur:checkedAbsent cv:dock_level` heißt „geprüft, nicht im Dokument“. Kein Tripel heißt „nicht untersucht“.
6. **Kanten sind Behauptungen mit Herkunft.** Modellvorschläge brauchen eine berechnete Konfidenz und sind nie amtlich. Amtliches braucht eine Fundstelle.
7. **Keine Umrechnung zwischen Systemen.** Unterrichtsstunden sind keine Zeitstunden, und ECTS sind keine Stunden. GER und DQR sind nicht gleichwertig, Jahrgang und Niveau auch nicht.
8. **Wenige, kleine Auswahllisten für das LLM.** Kein LLM-Enum hat mehr als zehn Werte. Profilwerte kommen als nummerierte Liste ins Prompt. Konfidenz berechnet die Pipeline.
9. **Profile erweitern, Kern bleibt stabil.** Profile legen Knotentypen, Unterarten, Dokumenttypen, Wertelisten, Lexikon und Warnregeln an. Neue Ebenen-Klassen und neue Andockpunkte legen sie nicht an. Braucht ein Bereich mehr, wird der Kern versioniert.
10. **SHACL ohne Inferenz.** Struktur ist eine Violation, Vollständigkeit eine Warnung, Arbeitsstand eine Info. Ontologie und Vokabulare stehen im Datengraph. RDFS-Inferenz würde über `rdfs:range` genau die geprüften Typen erzeugen.

---

## 4. Architektur

### 4.1 Schichten

```
L1 Extraktion   SourceFile ─containsDocument→ Document ─represents→ Specification (Curriculum | CompetencyFramework |
                                                                    QualificationSpecification | AssessmentSpecification)
                Document ─versionOf→ Work          CurriculumNode ─partOf→ Specification | Document | CurriculumNode
                Statement ─partOf→ CurriculumNode   Statement ─anchor→ SourceAnchor (Block-ID, Seite, Zitat, Fundart)
L2 Analyse      Decomposition ─decomposes→ Statement ; ─expresses→ CompetencyConcept ; ─mentions→ ContentConcept
                LevelAssignment, TimeSpan, Workload, ContextConcept, CrossCuttingObjective, CompetenceDimension
L3 Graph        Alignment (source, target, relation, origin, reviewStatus, method, confidence, anchor)
                → Kurzform-Tripel (cur:buildsOn, cur:correspondsTo …) nur bei confirmed/official
Lexikon         TerminologyProfile ─hasCue→ LexicalCue (Rolle, Art, Muster, Ziel, Geltung, Stärke)
                DocumentProfile (Termzuordnungen, Tabellenschemata) je Dokument
```

### 4.2 Dateien

| Datei | Inhalt | Umfang |
|---|---|---|
| `ontologie/cur-kern.ttl` | Klassen und Eigenschaften des Kerns, Andockpunkt-Annotationen | 70 Klassen, 252 Eigenschaften |
| `ontologie/cur-vokabular.ttl` | Kernvokabular `cv:` (Funktionen, Aussagearten, Adressaten, Verbindlichkeit, Niveau-Dimensionen, Zeit, Umfang, Herkunft, Kantenarten, Lexikon-Rollen, Stufen …) | 42 Schemata, 276 Konzepte |
| `ontologie/cur-shapes.ttl` | SHACL in drei Schichten | 75 NodeShapes |
| `ontologie/cur-alignments.ttl` | Abbildung auf CTDL-ASN, CASE, ELM 3.3, schema.org/AMB, ESCO, PROV, Web Annotation, FWU, OEH/KIM | 102 Tripel |
| `ontologie/migration.ttl` | Klassen der sechs Vorentwürfe → Kern | 152 Abbildungen |
| `vokabulare/laender.ttl` | `land:` DE + 16 Länder (Wikidata, FWU) | 17 |
| `vokabulare/niveaus.ttl` | `lvl:` 24 Niveausysteme (EQF, DQR, Abschlüsse, ISCED 2011, GER, Alpha-Level, BE/BB A–H, IQB, DigComp, Dreyfus, Erwartungs-/Kursniveaus und Anforderungsebenen, Noten und Notenpunkte, AFB, Bloom, SOLO, affektiv, psychomotorisch …) | 135 Stufen |
| `vokabulare/kompetenzdimensionen.ttl` | `kd:` Brückenschema (DQR/EQR) + 8 Kompetenzmodelle | 50 Dimensionen |
| `vokabulare/querschnitt.ttl` | `qz:` Hub + 9 Quellschemata (KMK Digitale Welt, MKR NRW, BW-Leitperspektiven, HH, BE/BB Teil B, SBBP 2021, EU-Schlüsselkompetenzen, MRVO § 11, EB) | 88 |
| `vokabulare/kontexte.ttl` | `ctx:` Situationen, Lebensbereiche, Lernorte, Rollen, Berufsbereiche (KldB) | 92 |
| `vokabulare/faecher.ttl` | `fld:` ISCED-F 2013 vollständig, gemappt auf KIM-ISCED und EU-ISCED-F, Brücken zu KIM-Schulfächern | 120 |
| `vokabulare/operatoren.ttl` | `op:` Operator-Lemmata + 3 Operatorenlisten (BW 2016, IQB 2022, Heuristik) | 116 |
| `profile/schule.ttl` (+ `schule-lexikon-fwu.ttl`) | `schul:` 10 Knotentypen, 13 Unterarten, 8 Dokumenttypen, 112 + 375 Hinweise | |
| `profile/elementar.ttl` (+ `elementar-lexikon.ttl`) | `elem:` 16 Knotentypen, 11 Unterarten, 9 Dokumenttypen, Feldvokabular Gemeinsamer Rahmen, 34 + 239 Hinweise | |
| `profile/beruf.ttl` | `beruf:` 25 Knotentypen, 10 Unterarten, 17 Dokumenttypen, 55 Hinweise | |
| `profile/hochschule.ttl` (+ `hochschule-lexikon.ttl`) | `hs:` 13 Knotentypen, 6 Unterarten, 21 Dokumenttypen, 19 Wertelisten, 21 + 395 Hinweise | |
| `profile/erwachsenenbildung.ttl` | `eb:` 14 Knotentypen, 12 Unterarten, 12 Dokumenttypen, 36 Hinweise | |
| `profile/profil-shapes.ttl` | Vollständigkeits- und Plausibilitätsregeln je Bereich (nur Warnung/Info) | 8 NodeShapes |
| `schemas/*.schema.json` | Strikte JSON-Schemas für X1 (zwei), X3, X4, N1, G1 | 6 |
| `beispiele/*.ttl` | Ohm-Kette, Elementar, Erwachsenenbildung, Kompetenzrahmen, zwei Negativsätze | 6 |
| `pruefung/pruefe.py`, `pruefung/abfragen/*.rq` | Prüfskript und Anwendungsfall-Abfragen | |
| `werkzeuge/*.py` | Generatoren: Elementar-Lexikon, Hochschul-Lexikon, FWU-Schullexikon, JSON-Schemas; Export der Vorlisten | 5 |
| `recherche-auftraege/` | Rechercheaufträge für Länder-Steckbriefe (Schule je Land, Elementar, Beruf, Hochschule, EB, Querschnitt/Niveau, Noten- und Verhaltensskalen) mit Vorlisten des heutigen Lexikons | 7 Aufträge, 65 Vorlisten |

### 4.3 Namensräume

| Präfix | IRI | Inhalt |
|---|---|---|
| `cur:` | `https://w3id.org/wlo/curriculum/core#` | Kern |
| `cv:` | `https://w3id.org/wlo/curriculum/vocab#` | Kernvokabular |
| `lvl:` `kd:` `qz:` `ctx:` `fld:` `op:` `land:` | `https://w3id.org/wlo/curriculum/{level,dimension,crosscutting,context,field,operator,region}/` | gemeinsame Vokabulare |
| `elem:` `schul:` `beruf:` `hs:` `eb:` | `https://w3id.org/wlo/curriculum/profile/{early-childhood,school,vocational,higher-education,adult-education}#` | Profile |
| `shs:` | `https://w3id.org/wlo/curriculum/shapes#` | Shapes |

`w3id.org/wlo/` ist **nicht registriert**; alle IRIs sind Platzhalter bis zur Registrierung (Alternative: `w3id.org/openeduhub/`, existiert bereits). Die IRIs sind englisch, die Labels deutsch und englisch, die Definitionen deutsch.

---

## 5. Kernmodell L1: Quelle, Geltung, Struktur, Aussage

### 5.1 Quelle

- **`cur:SourceFile`**: die Datei mit SHA-256. Ein Mitteilungsblatt kann mehrere Dokumente enthalten, ein Modulhandbuch über mehrere PDFs verteilt sein.
- **`cur:Document`**: eine Fassung. Dazu gehören Titel, Dokumenttyp aus einem Profil, Bildungsbereich(e), Land, Rechtsform (`cv:LegalForms`), Verbindlichkeit des Dokuments (`cv:DocumentBindings`), Lebenszyklus (`cv:Lifecycles`, z. B. Anhörungsfassung), Gültigkeit und Herausgeber.
- **`cur:Work`**: die Identität über alle Fassungen, ausdrücklich gesetzt und nicht aus Kopfdaten berechnet. Die App hat gezeigt, dass ein berechneter Werkschlüssel sich mit jeder Kopfkorrektur ändert.
- **Fassungen** stehen über `cur:supersedes`, `cur:amends` und `cur:appliesToCohort` in Beziehung. Eine Änderungssatzung *ändert*; erst die konsolidierte Fassung *ersetzt*. Dokumente erben über `cur:inheritsFrom` (Rahmen-PO → fachspezifische Bestimmungen).
- **`cur:SourceAnchor`**: Block-ID aus X0 (`p<Seite>-b<Block>`), PDF- und gedruckte Seite, Zitat am Anker und Fundart (`cv:MatchKinds`: exact, whitespace, elided, normalized, fuzzy, notFound). Bei Bedarf kommen Tabellenzelle, Abschnittspfad, Zeichenpositionen und `cur:textHash` dazu. **Unscharf gefundene Zitate sind kein Wortlautbeleg.** Diese Lehre aus der App ist jetzt eine Warnregel.
- **`cur:ExtractionRun`** (⊑ `prov:Activity`) hält Stufe, Modell, Prompt- und Profilversion fest. **`cur:ExtractionAssertion`** und **`cur:ConflictResolution`** gibt es nur für konfliktträchtige Felder (LP, Pflicht, Semester, Prüfungsform, Zeitrichtwert), wenn zwei Dokumente Verschiedenes sagen. Die Reihenfolge der Kriterien (`cv:ConflictCriteria`) ist Kohorte → Verbindlichkeit → Spezifität → Aktualität → Mensch.

### 5.2 Geltung

- **`cur:Specification`** mit genau einem von vier Untertypen:
  - `cur:Curriculum` (Lehrplan, Ausbildungsrahmenplan, Modulhandbuch, Bildungsplan, Kurskonzept)
  - `cur:CompetencyFramework` (Bildungsstandards, GER, DigComp, Raster)
  - `cur:QualificationSpecification` (Fortbildungsordnung, Zertifikatsordnung)
  - `cur:AssessmentSpecification` (Prüfungsteil einer Verordnung, Testhandbuch)
- **`cur:Programme`** (Studiengang, Bildungsgang), **`cur:Qualification`** (Abschluss; einziger Ort für DQR/EQR) und **`cur:Occupation`** (Beruf mit BIBB-Kennung, KldB, ESCO).
- **`cur:Variant`**: Fachrichtung, Schwerpunkt, Wahl- und Zusatzqualifikation, Studienrichtung, Kurszug, Teilcurriculum, Zielgruppenvariante, Einsatzgebiet (`cv:VariantKinds`).
- **`cur:ApplicabilityContext`**: Bildungsbereich, Formalität, Zeitraum, Niveau, Einrichtungsart, Zielgruppe. Mit `cur:alternativeContext` lassen sich ODER-Kontexte bilden.
- **`cur:Rule`** mit `SelectionRule` (min/max Anzahl und Umfang, Optionen, nicht kombinierbar), `PrerequisiteRule` (formal/empfohlen), `CompletionRule`, `RecognitionRule` (Höchstanteil, Verfahren) und `ProgressionRule`. Jede Regel hat Wortlaut und Fundstelle; die geparsten Werte stehen daneben.

**Entscheidungsregel Curriculum oder Facette** (aus EB-CO): Ein eigener Abschluss, eine eigene Prüfung oder ein eigener Umfang ergibt eine eigene Spezifikation. Unterscheiden sich nur Niveau, Zielgruppe oder Bildungsort, ist es eine Variante oder ein Geltungskontext. Wiederverwendung läuft immer über Referenz.

### 5.3 Struktur

**`cur:CurriculumNode`**: eine rekursive Gliederungseinheit mit genau einem Eigentümer (Spezifikation, Dokument oder Knoten) und genau einer **Kernfunktion** (`cv:NodeFunctions`):

| Funktion | Bedeutung | Beispiele |
|---|---|---|
| `grouping` | Ordnet nach Organisation, trägt Kontext | Doppeljahrgang 7/8, Phase, Alpha-Level, Abschnitt A des ARP, Leitbild (Kita) |
| `area` | Thematischer oder Kompetenzbereich ohne eigenen Zeitumfang | Inhaltsfeld, Kompetenzbereich, Bildungsbereich, Handlungsfeld, Studienbereich |
| `unit` | Abgeschlossene Einheit mit Zeit- oder Niveaubezug | Lernfeld, Berufsbildposition, Modul, Lernbereich mit Ustd. (SN), Kursabschnitt |
| `subunit` | Unterteilung | inhaltlicher Schwerpunkt, Lehrveranstaltung, sprachliche Handlung, Kompetenzeinheit K1 |
| `crossCutting` | Überfachliche Ziele | Leitperspektiven, Basiskompetenzen, Standardberufsbildpositionen, Fokus Landeskunde |
| `frame` | Curricular relevanter Rahmen | Allgemeiner Teil, Fachprofil, RLP Teile I–IV, §§ einer Ordnung, Kompetenzmodell, Operatorenliste |
| `nonCurricular` | Ohne Vorgaben | Vorwort, Verzeichnis, Impressum |

Dazu kommen:

- ein **Knotentyp** aus dem Profil (`cur:NodeType`, z. B. `schul:Inhaltsbereich`, `beruf:Lernfeld`, `hs:Modul`), mit genau einer Kernfunktion als `skos:broader`;
- die **Extraktionstiefe** (`full`, `typed`, `skip`) als stärkster Kostenhebel: Rahmenteile werden nur typisiert, Verzeichnisse übersprungen;
- Originaltitel wörtlich, `cur:code` wie im Dokument, `cur:position` als reine Dokumentreihenfolge;
- `cur:appliesTo` und `cur:scopeShare` (gemeinsam, spezifisch, ergänzend, alternativ), `cur:integrative` sowie `cur:inArea` für Matrixlayouts.

**`cur:Placement`** (aus HCO ComponentUse verallgemeinert) verwendet eine Einheit in einer Spezifikation oder Variante. Jede Verwendung hat eigene Verbindlichkeit, eigenes Fachsemester oder Ausbildungsjahr, eigenen Umfang im Kontext und eigenes Notengewicht. So wird ein Modul, das in drei Studiengängen vorkommt, einmal beschrieben und dreimal verwendet. Seine Aussagen und Andockpunkte hängen nur einmal am Modul, und Zählungen verdoppeln sich nicht.

**`cur:Assessment`** ist rekursiv aufgebaut (Prüfung → Teil → Bereich) mit Kern-Prüfungsart, Form aus dem Profil, Dauer, Gewicht und `cur:assesses`. Die Summe der Gewichte der direkten Teile darf 100 % nicht übersteigen.

### 5.4 Aussage

**`cur:Statement`**: ein wörtlicher Text mit Sprachangabe, genau einem Eigentümerknoten und mindestens einer Fundstelle. Pflicht sind außerdem eine **Aussageart** und mindestens ein **Adressat**. Der gemeinsame Einleitungssatz („Die Schülerinnen und Schüler …“) steht in `cur:leadIn`.

| Aussageart (`cv:StatementKinds`) | Bedeutung | Beispiele |
|---|---|---|
| `learningOutcome` | Prüf- oder beobachtbar, meist mit Operator | Kompetenzerwartung, Zielformulierung, FKF a), Modulziel, Kann-Beschreibung |
| `developmentGoal` | Haltung, Disposition, Erfahrung, Bildungsanspruch ohne Prüfanspruch | Kita-Bildungsziel, Bildungsauftrag RLP Teil II, „Ist sensibilisiert für …“ |
| `content` | Gegenstand ohne Handlung | Inhalte, Fachbegriffe, Wissensbestände, Redemittel |
| `standard` | Maßstab | KMK-Regelstandard, Rasterzelle, Prüfungsanforderung, Qualitätsanspruch (BE QA) |
| `mandate` | Auftrag an Lehrende, Fachkräfte, Einrichtung | „Pädagogische Fachkräfte …“, „Der Unterricht ermöglicht …“, pädagogischer Grundsatz |
| `guidance` | Nicht normativ | Hinweis, Anregung, Reflexionsfrage, Praxisbeispiel |
| `reference` | Verweis | BW P/I/F/L, SN „➔ GE, Kl. 8/9“, Importmodul, Spiralverweis |
| `unclassified` | Nicht sicher bestimmbar | „Kinder lernen …“; geht in die Prüfliste |

Die definierten Klassen `cur:LearningOutcome` bis `cur:Reference` (`owl:equivalentClass` über `statementKind hasValue`) dienen nur der Abfrage; die Extraktion schreibt die Art.

| Adressat (`cv:Addressees`) | Bedeutung |
|---|---|
| `learner` | Lernende (Kind, Schüler, Auszubildende, Studierende, Teilnehmende) – **nur diese docken an Kompetenzkonzepte und an AMB `teaches`** |
| `educator` | Lehrende, Fachkräfte, Ausbildende |
| `institution` | Schule, Kita, Betrieb, Träger, Hochschule |
| `family` | Eltern, Familie |
| `partner` | Kooperationspartner |
| `other` | sonstige |

**Verbindlichkeit je Aussage oder Verwendung** (`cv:Obligations`): binding, electiveRequired, elective, selectionPool, exemplary, recommended, informative, unknown. Sie ist getrennt von der Verbindlichkeit des Dokuments: ein orientierender Kita-Plan kann verbindliche Ziele enthalten (BW), ein amtliches Rahmencurriculum ein reiner Auswahlpool sein (BAMF).

Weitere Felder halten den Wortlaut für die späteren Andockpunkte fest:

- `cur:layoutMarker` (fett, kursiv, Klammer …);
- `cur:levelText`, `cur:timeText`, `cur:contextText`, `cur:crossCuttingMarker`, `cur:referenceMarker` mit `cur:citedCode` und `cur:resolutionStatus`;
- `cur:exampleText` und `cur:purpose` (Handlungsziel „Möchte …“);
- `cur:summarizes` für zusammenfassende Erwartungen, die nicht dedupliziert werden.

---

## 6. L2 Analyse: Zerlegung, Konzepte, Modelle

**`cur:Decomposition`**: eine Handlung je Zerlegung. Mehrere Operatoren ergeben mehrere Zerlegungen derselben Aussage. Die Teile:

| Teil | Wortlaut | Normiert |
|---|---|---|
| Handlung | `cur:actionText` (trennbare Verben als „wählen … aus“) | `cur:action` → `cur:OperatorLemma` |
| Gegenstand | `cur:objectText` | `cur:mentions` → `cur:ContentConcept` |
| Bedingung/Kontext | `cur:conditionText` | – |
| Qualität | `cur:qualityCriterion` | – |
| sonst | `elem:developmentQualifier` (Kita), `cur:autonomy`, `cur:knowledgeType`, `cur:competenceDimension` | |

Eine Zerlegung kann `cur:expresses` auf ein `cur:CompetencyConcept` setzen.

**Rückprobe:** Gegenstand und erster Teil der Handlung müssen im Wortlaut stehen. Sonst gibt es eine Warnung, denn das Modell hat dann paraphrasiert. In den EB-Goldbeispielen fielen genau solche Fälle auf („sensibilisiert sein“).

Zerlegt werden nur Lernergebnisse, Bildungsziele und Standards. **Kompetenzkonzepte nur für Lernende** (SHACL-Violation): Eine Fachkraft-Aussage wird nicht zu einem Kindziel umgeschrieben (ELEM-Fehler H.6 Nr. 8). Sie bekommt höchstens eine vorgeschlagene Kante `rel_supports` zu einem Kompetenzkonzept.

**Hubs** sind dokumentübergreifend und entstehen bottom-up: Kandidaten per Embedding, die Wahl trifft ein LLM aus einer nummerierten Liste. Externe Abbildungen hängen **nur an den Konzepten**, nie an der Aussage:

- **`cur:ContentConcept`**: Thema, Begriff, Gegenstand; gegen Wikidata und GND per Reconciliation.
- **`cur:CompetencyConcept`**: kontextfreie Kompetenz; gegen ESCO, DigComp und GER per Alignment, nie `exactMatch` von einer Aussage auf ESCO.
- **`cur:AreaConcept`**: deduplizierte Bereiche in Matrixlayouts (NW Kompetenzbereich × Inhaltsfeld; Basiskonzepte).

**Kompetenzmodelle** (`cur:CompetencyModel`) werden vom Dokument erklärt und in X3 gelesen. In X4 sind sie Auswahlliste. Jedes Modell ist über das **Brückenschema `kd:Bridge`** (DQR/EQR: Fachkompetenz {Wissen, Fertigkeiten}, personale Kompetenz {Sozialkompetenz, Selbstständigkeit}, Methodenkompetenz) vergleichbar. Mitgeliefert sind KMK-Handlungskompetenz, HQR 2017, Vier-Komponenten-Modell, Kita-Basiskompetenzen, Schul-Kompetenzarten, NaWi (S/E/K/B), Gesellschaftswissenschaften (SK/MK/UK/HK), FKF der Ausbildungsordnungen und GER-Aktivitäten.

**Querschnitt:** Ein Hub `qz:Hub` mit rund 35 Zielen. Die Länder- und Rahmenschemata hängen per SKOS daran: KMK Digitale Welt, MKR NRW, BW-Leitperspektiven, HH-Aufgabengebiete, BE/BB Teil B, Standardberufsbildpositionen 2021, EU-Schlüsselkompetenzen, MRVO § 11, EB-Querschnittsdimensionen, Kita-Prinzipien. Eine Frage wie „Wo wird BNE verankert?“ läuft über den Hub (Abfrage q4).

**Kontext** (`ctx:`): Situationen (Kita-Alltag, Spiel, Projekt, Experiment, Arbeitsauftrag), Lebensbereiche (12 Handlungsfelder Integrationskurs), Lernorte (Betrieb, Berufsschule, ÜBS, Praxiseinsatz, Hochschule, Kita, Hort …), Rollen/Zielgruppen und KldB-Berufsbereiche. Am Knotentyp steht `cur:impliesContext` (Handlungsfeld → Lebensbereich); der Wert wird vererbt und an der Aussage nur gesetzt, wenn er dort ausdrücklich steht.

---

## 7. Die acht Andockpunkte

Alle Andockpunkte folgen demselben Muster und sind maschinenlesbar in `cv:DockingPoints` beschrieben (Frage, Eigenschaften, Hub, Zielvokabular, Vererbung, Stufe). Die Eigenschaften im Kern tragen `cur:dockingPoint`.

| Andockpunkt | Frage | Wortlaut | Norm | Hub/Ziel | Vererbung | Stufe |
|---|---|---|---|---|---|---|
| **Inhalt und Thema** | Welches Thema, welcher Gegenstand? | `originalTitle` (Thema einer Einheit), `objectText` (Gegenstand) | `mentions` | `ContentConcept`, hierarchisch Thema → Begriff/Entität → Wikidata, GND, WLO-Themenbaum | – | N1, N2 |
| **Kompetenz** | Was soll jemand tun können? | `actionText` | `expresses`, `action`, `competenceDimension` | `CompetencyConcept` → ESCO, DigComp, GER, Bildungsstandards; Dimension über `kd:Bridge` | – | N1, N2 |
| **Niveau** | Wie anspruchsvoll, auf welcher Stufe? | `levelText` | `levelAssignment` | `LevelConcept` in `lvl:` | `partOf` | X1, X4, N1 |
| **Fach/Feld** | In welchem Fach, Beruf, Studienbereich? | `fieldText` | `field`, `occupation` | `fld:` (ISCED-F) + KIM-Schulfächer, Beruf (KldB/ESCO), `elem:Fields`, `eb:ProgramAreas` | `partOf` | X1 |
| **Zeit und Geltung** | Wann, wie lange, wo, wie verbindlich? | `timeText` | `timeSpan`, `workload`, `obligation`, `region` | `cv:TimeKinds`, `cv:WorkloadUnits`, `cv:Obligations`, `land:` | `partOf` | X1, X4 |
| **Querschnitt** | Welches überfachliche Ziel? | `crossCuttingMarker` | `contributesTo` | `qz:Hub` | – | X4, N1 |
| **Kontext** | Welche Situation, welcher Lernort, welche Rolle? | `contextText` | `context` | `ctx:` | `partOf` | X1, X4 |
| **Adressat** | Wer soll das tun oder können? | – | `addressee` | `cv:Addressees` (Filter für Kompetenz und AMB) | – | X4 |

**Thema ist Teil des Andockpunkts Inhalt**, mit eigener Körnung, nicht ein eigener Andockpunkt. Thema und Begriff liegen im selben Hub und unterscheiden sich nur in der Feinheit. Ein eigener Andockpunkt würde dieselbe Sache zweimal modellieren, und jedes Konzept müsste einem der beiden zugeschlagen werden. Gelöst ist es so:

- `cur:granularity` am Inhaltskonzept: `topic` („Elektrizität“, „Ernährung“), `concept` („Ohmsches Gesetz“), `entity` („Martin Luther“, „Rhein“). Begriffe hängen per `skos:broader` an Themen.
- **Zwei Andockstellen:** Das *Thema* einer Gliederungseinheit kommt aus ihrem Titel (`cur:mentions` am Knoten: Inhaltsfeld „Elektrizität“, Lernfeld, Modul). Der *Gegenstand* einer Aussage kommt aus der Zerlegung (`cur:mentions` an der Zerlegung oder an der Inhaltsaussage).
- **Die Themensuche** steigt beim Thema ein und folgt `skos:broader*` nach unten. So findet sie Einheiten, die das Thema im Titel tragen, und Aussagen, deren Gegenstand darunter liegt (Abfrage q1: Inhaltsfeld, Lernfeld und Modul zu „Elektrizität“ samt Aussagen zum Ohmschen Gesetz).
- **Themenschemata der Profile** (die Kita-Bildungsbereiche, ein späterer WLO-Themenbaum) werden per `broadMatch` angebunden, nicht kopiert.

**Regeln:**

- **Vererbung wird abgefragt, nicht materialisiert.** Fach, Zeit, Niveau und Kontext gelten für alles darunter (`cur:partOf+`), bis ein Knoten oder eine Aussage einen eigenen Wert setzt. Wird für den Export vererbt, trägt der Wert `cv:orig_inherited`.
- **Fehlwerte haben drei Formen.** `cur:checkedAbsent` heißt „nicht im Dokument“, kein Tripel heißt „nicht untersucht“, `unknown` heißt „unklar“.
- **Ein neuer Andockpunkt ist eine Kernversion**, keine Profilsache.

---

## 8. Niveau und Zeit

### 8.1 Niveau

Ein Niveau ist eine **n-äre Zuordnung** (`cur:LevelAssignment`) aus Stufe (`cur:level`, bei Spannen `cur:levelTo`), **Relation** (`cv:LevelRelations`: assigned, minimum, target, entry, range) und Herkunft. Die **Dimension** steht am Schema; bei Abweichung kann sie an der Zuordnung stehen. Gilt ein Niveau nur für einen **Kompetenzbereich** (GER je Fertigkeit, IQB-Stufen je Bereich, DigComp je Bereich), steht dieser als `cur:competenceDimension` an der Zuordnung.

| Dimension (`cv:LevelDimensions`) | Systeme in `lvl:` | Ordnung |
|---|---|---|
| `qualification` | EQF 1–8, DQR 1–8, Schulabschlüsse (ESA, EESA, MSA, Übergang, FHR, AHR), Hochschulgrade, Fortbildungsstufen (DQR 5/6/7) | kumulativ |
| `stage` | ISCED 2011 (0, 01, 02, 1–8) mit KIM-Bildungsstufen | kumulativ |
| `proficiency` | GER (Pre-A1–C2), Alpha-Level 1–6, BE/BB Niveaustufen A–H, IQB-Kompetenzstufen I–V, DigComp 3.0, Dreyfus/Benner (5) | kumulativ |
| `attainment` | Mindest-, Regel-, erhöhte, optimale Anforderungen (HH, Bildungsstandards); Anforderungsebenen ESA/MSA/Übergang (SH); BW G/M/E | kumulativ; G/M/E parallel |
| `course` | G-/E-/Z-Kurs (Sek I), grundlegendes/erhöhtes Anforderungsniveau (Sek II) | Sek I parallel, Sek II kumulativ |
| `taskDemand` | Anforderungsbereiche I–III | kumulativ |
| `development` | noch keins; ein System nur, wenn das Dokument den Verlauf ausdrücklich ordnet (Kandidat: TH „Modi der Weltaneignung“) | – |
| `grading` | Notenstufen 1–6, Notenpunkte 0–15 (Oberstufe, mit Zuordnung zu den Notenstufen); Hochschulnoten nicht | geordnet ohne Einschluss |
| `conduct` | noch keins; Kopfnoten bzw. Arbeits- und Sozialverhalten je Land folgen aus Recherche 07 | – |
| `cognitive` | Bloom/Anderson-Krathwohl (6), SOLO (5) | kumulativ |
| `affective` | Krathwohl/Bloom/Masia 1964 (5) | kumulativ |
| `psychomotor` | Dave 1970 (5) | kumulativ |

**Regeln** (meist als SHACL geprüft). Eine abweichende Dimension an der Zuordnung schaltet keine Regel ab: Es zählt die Dimension der Zuordnung und die des Schemas.

- **Keine Umrechnung zwischen Systemen.** Mappings zwischen Systemen sind SKOS mit Bedacht: DQR closeMatch EQF ja, GER nicht auf DQR.
- **DQR/EQR und Abschlüsse nur an Qualifikation, Spezifikation oder Geltungskontext**, nie an einer Aussage oder Zerlegung (Violation). Die amtliche Zuordnung der Schulabschlüsse (KMK 2017: ESA 2, MSA 3, FHR und AHR 4) steht als closeMatch. Anforderungsebenen an Aussagen (SH: ESA, MSA, Übergang) sind Erwartungsniveaus in `lvl:AttainmentTracks`, ohne DQR-Bezug. Kita, Grundschule und einzelne Lernziele haben kein DQR-Niveau; die Bildungsstufe kommt aus ISCED 2011.
- **Kompetenzbereich am Niveau** muss eine `cur:CompetenceDimension` sein (Violation).
- **AFB bezieht sich auf Aufgaben.** An einer Kompetenzerwartung ist er nur zulässig, wenn das Dokument ihn nennt (`cv:orig_source`); sonst gibt es eine Warnung.
- **Heuristiken** (Bloom, SOLO, affektiv, psychomotorisch) gibt es nur mit Herkunft rule, model oder human (Violation bei jeder anderen oder fehlender Herkunft). Nennt ein Dokument eine solche Stufe ausdrücklich, steht der Wortlaut in `cur:levelText`. Affektive Stufen dienen der Planung; sie stufen keine Haltungen von Lernenden ein.
- **Bewertungs- und Verhaltensstufen** (Noten, Notenpunkte, Kopfnoten) hängen nur an Prüfung, Prüfungsspezifikation, Regel (Bestehen, Zulassung, Anrechnung) oder Standard; an allem anderen ist es eine Violation, etwa an Lernergebnis, Knoten oder Zerlegung.
- **Entwicklungsstufen** nur, wenn das Dokument den Verlauf ausdrücklich ordnet. Beobachtungsinstrumente der Kita (Beller, Grenzsteine, Meilensteine, Perik/Sismik/Seldak) haben eigene Normen und sind keine Niveaus.
- **Bewusst nicht aufgenommen:** Webb's Depth of Knowledge (vier Stufen, entspricht weitgehend AFB I–III; kein deutsches Dokument nennt es) und Simpsons psychomotorische Stufen (andere Stufen als Dave; nicht mischen).
- **`rel_buildsOn`** innerhalb eines kumulativen Systems ist ableitbar (Raster), nicht in Systemen, die geordnet sind, aber nichts einschließen (`cv:ord_ordinal`: Noten, Verhaltensstufen). Über Systeme hinweg braucht es ein gemeinsames Inhaltskonzept, sonst gibt es eine Warnung.
- Die **Zuordnungsart** wird einmal je Dokument bestimmt (BAMF: Mindestniveau; DVV: zugewiesen) und dann deterministisch gesetzt.
- Kita-Texte haben fast nie ein Niveau. Entwicklungssignale („zunehmend selbstständig“) bleiben Wortlaut (`elem:developmentQualifier`).

**Vier Ebenen der Einordnung.** Für die Vernetzung über Bildungsbereiche hinweg greifen vier Ebenen ineinander. Keine davon ersetzt eine andere, und der DQR ist kein Rückgrat für Lernziele:

| Ebene | Frage | Im Modell |
|---|---|---|
| 1. Bildungsstufe und Qualifikation | Wo im Bildungssystem? | Bildungsstufe: ISCED 2011 (`stage`) am Curriculum oder Geltungskontext. Qualifikation: DQR/EQR, Abschlüsse, Hochschulgrade (`qualification`) nur an Qualifikation oder Spezifikation |
| 2. Kompetenzbereich | Was wird entwickelt? | `cur:competenceDimension` an Aussage, Knoten oder Niveau; Brückenschema `kd:Bridge` (Wissen, Fertigkeiten, Sozialkompetenz, Selbstständigkeit) mit den Bereichsmodellen (`kd:FourComponents`, `kd:KMKActionCompetence`, `kd:HQR`, `kd:DHBW`, Fachmodelle) |
| 3. Anforderung | Wie anspruchsvoll? | Stufen aus dem Dokument (`attainment`, `proficiency`, `course`), AFB an Aufgaben (`taskDemand`), Heuristiken (`cognitive`, `affective`, `psychomotor`), Wissensart (`cv:KnowledgeTypes`) |
| 4. Nachweis | Woran ist Erfolg erkennbar? | `cur:Assessment`, `cur:AssessmentSpecification`, Standards als Bewertungskriterien, Bewertungsstufen (`grading`, `conduct`) |

### 8.2 Zeit und Umfang

**Zeit ist kein Niveau.** `cur:TimeSpan` beschreibt die Lage:

- Zeitart (`cv:TimeKinds`): Alter in Monaten, Jahrgangsstufe, Ausbildungsjahr, Ausbildungsmonat, Semester, Studienjahr, Kursabschnitt, Phase;
- von/bis;
- Bezug (`cv:TimeRelations`): during, endOf, until, from.

`cur:Workload` beschreibt den Umfang:

- Wert, bei Spannen Wert bis;
- Einheit (`cv:WorkloadUnits`): Unterrichtsstunde, UE, Zeitstunde, Wochenstunde, ECTS, Tag, Woche, Monat, Semester, Jahr;
- Art (`cv:WorkloadKinds`): Richtwert, Unterrichtszeit, Kontaktzeit, Selbststudium, Gesamtaufwand, Leistungspunkte, Dauer;
- Empfehlung ja/nein; Minuten je Einheit nur aus dem Dokument.

**Summen nur innerhalb einer Einheit.** Profilwarnungen gibt es für 25–30 h je LP, Kontakt + Selbst = Gesamt, mehr als 40 LP Pflicht je Semester, Lernfeld-Zeitrichtwerte nicht durch 20 teilbar sowie Lernfeld ohne Zeitrichtwert oder Ausbildungsjahr.

---

## 9. Kanten (L3)

### 9.1 Zuordnung als Knoten

Eine Kante ist ein `cur:Alignment` nach dem Muster von CASE CFAssociation. Es hat:

- Quelle(n) (mehrere = gemeinsam) und genau ein Ziel;
- genau eine **Kantenart**, genau eine **Herkunft**, genau einen **Prüfstand** und genau eine **Methode**;
- Konfidenz, Begründung, Zielsystem und -version, Prüfer und Fundstelle.

| Herkunft (`cv:Origins`) | Bedeutung | Regel |
|---|---|---|
| `source` | steht im Dokument (Verweis, Spiralverweis) | – |
| `inherited` | vererbt | – |
| `rule` | deterministisch (Muster, Tabelle, gleiche Stufe im Raster) | – |
| `model` | vom Modell vorgeschlagen | braucht berechnete Konfidenz; nie mit Methode verbatim/officialList |
| `human` | von der Redaktion gesetzt | – |
| `official` | amtlich belegt (Entsprechungsliste, Anrechnungsordnung, wörtlich übernommene PflAPrV-Kompetenz) | braucht Fundstelle; einzig zulässig für `recognizedFor`/`qualifiesFor` |

**Prüfstand** (`cv:ReviewStatuses`): proposed, confirmed, rejected. **Methode** (`cv:Methods`): verbatim, pattern, table, lookup, inheritance, reconciliation, embedding, llmChoice, llmJudgement, manual, officialList.

**Kurzform-Tripel** (`cur:buildsOn`, `cur:correspondsTo`, `cur:concretizes` …) werden **nur materialisiert, wenn eine Zuordnung confirmed oder official ist**. Ausnahmen sind `contributesTo` (ausdrücklicher Querschnittsmarker) und `variantOf` (Struktur). Eine Warnregel meldet Kurzformen ohne Deckung. Abfragen für Lernpfade folgen nur Kurzformen; Vorschläge sieht die Redaktion.

### 9.2 Kantenarten

| Kantenart | Bedeutung | Wer setzt sie typisch | Export |
|---|---|---|---|
| `exactMatch` | gleiche Anforderung/gleicher Begriff | Regel (Lernfeldidentität), Redaktion | SKOS exactMatch · CTDL exactAlignment · CASE exactMatchOf |
| `closeMatch` | nahezu gleichwertig | Modell + Redaktion | SKOS closeMatch · CASE isRelatedTo |
| `broadMatch` / `narrowMatch` | Ziel ist breiter/enger | Modell | SKOS · CTDL broad/narrowAlignment (Ziel breiter = broad) |
| `relatedMatch` | verwandt | Modell | SKOS · CASE isRelatedTo |
| `majorOverlap` / `minorOverlap` | überlappt stark/schwach | Modell | CTDL major/minorAlignment |
| `requires` | setzt voraus | Dokument (Voraussetzung), Regel | CTDL prerequisiteAlignment |
| `buildsOn` | steigert (gleicher Inhalt, höhere Stufe) | Regel im Raster, Modell + Redaktion zwischen Bereichen | – |
| `precedes` | geht didaktisch voraus (nur ausdrücklich) | Dokument | CASE precedes |
| `revisits` | greift wieder auf (Spirale) | Dokument (DVV-Spiralverweis), Regel | – |
| `supports` | stützt (Auftrag → Kompetenz) | Modell | – |
| `concretizes` | konkretisiert (Lehrplan → Bildungsstandard) | Modell + Redaktion, Dokument | FWU LP_0000017 |
| `correspondsTo` | entspricht lernortübergreifend (RLP ↔ ARP) | amtlich (Entsprechungsliste) | – |
| `noCorrespondence` | amtlich ohne Entsprechung | amtlich | – |
| `crossSubject` | fachübergreifend (BW F, HH) | Dokument | CTDL crossSubjectReference |
| `contributesTo` | trägt bei zu (Querschnitt, Programmziel) | Dokument, Matrix, Modell | – |
| `derivedFrom` | übernommen aus (lea.-Item, § 66 vom Regelberuf) | Dokument, Regel | PROV wasDerivedFrom |
| `replaces` | ersetzt (Fassungswechsel) | Regel | CASE replacedBy (umgekehrte Richtung) |
| `variantOf` | Variante von | Struktur | – |
| `recognizedFor` / `qualifiesFor` | anrechenbar auf / berechtigt zu | **nur amtlich** | – |

**Lernpfade** setzen sich aus `requires`, `buildsOn`, `precedes` und `revisits` zusammen. **`cur:position` ist nie ein Lernpfad.** Die Abbildungen stehen in `ontologie/cur-alignments.ttl`. CASE hat keine RDF-Terme; die Assoziationstypen stehen dort als Literal.

---

## 10. Standards und Kompetenzrahmen generisch andocken

**Grundsatz: Standards sind auch Spezifikationen.** Ein Rahmen wird **einmal** als `cur:CompetencyFramework` importiert. Die Struktur ist dieselbe wie bei einem Curriculum:

- **Kriterien** (Rasterzeilen, Kompetenzbereiche, Skalen) sind `cur:CurriculumNode` mit dem bereichsneutralen Knotentyp `cv:nt_criterion` oder einem Profiltyp (KMK-Kompetenzbereich).
- **Zellen bzw. Deskriptoren** sind Aussagen der Art `standard` mit Niveauzuordnung.
- **Progression im Raster** ist eine regelbasierte `rel_buildsOn`-Kante (gleiches Kriterium, nächste Stufe, kumulatives System).
- **Andocken:** Curricula docken per `cur:Alignment` an Zellen, Kriterien oder an das Kompetenzkonzept des Rahmens an – mit denselben Herkunfts- und Prüfregeln wie zwischen Curricula. Die Landeserwartung ist `concretizes` des KMK-Regelstandards; die EB-Kann-Beschreibung ist `broadMatch` der GER- oder DigComp-Zelle.
- **Was einen Rahmen ausmacht**, bestimmt das Profil des Herausgebers: `schul:dt-Bildungsstandards`, `eb:dt-D7` (Referenzrahmen), `eb:dt-D13` (GRETA), `elem:dt-Beobachtungsinstrument`.

So entsteht das geplante **generische System für Kompetenzstandards** ohne Sonderlogik: Jeder neue Rahmen (EntreComp, GreenComp, LifeComp, ESCO-Sammlungen, Kammer-Raster) ist ein Import plus Knotentypen. Das Beispiel `beispiele/kompetenzrahmen.ttl` zeigt das Raster, die Konkretisierung eines Bildungsstandards, eine EB-Kann-Beschreibung an der Rasterzelle und eine Lernressource nach AMB.

**Was vor einem Import zu klären ist:** die Lizenz der Deskriptoren (GER-Begleitband, DigComp, lea.), stabile IRIs (für Bloom, KMK-Operatoren, KldB, DigComp und EU-Schlüsselkompetenzen gibt es keine) und die Fassung (`cur:targetVersion` an jeder Zuordnung).

---

## 11. Werk, Fassung und Identität

- **IRI-Schema** (Vorschlag):
  - `…/work/<land>/<kurztitel>` für das Werk;
  - `…/doc/<land>/<herausgeber>/<kurztitel>/<fassung>` für das Dokument (Land und Kurztitel des Werks; das Land, weil Herausgeber verschiedener Länder gleich heißen können), plus SHA-256 der Datei;
  - Knoten: Dokument + **Strukturpfad aus Codes** (`…/lf-5`, `…/if-5/st-3`). Fehlt ein Code, vergibt die Pipeline ihn deterministisch aus der Position (`cur:codeAssigned true`).
- **Laufbezogene IDs** (`run_id#node_id`) sind keine Identität. Die App hat gezeigt, dass Neuläufe sonst alle Kanten verlieren.
- **Zusammenführen über Dokumente** läuft über Code + Hochschule bzw. Beruf + Lernfeldnummer + Fassung des RLP; für den Wortlaut dient `cur:textHash` (NFC, Kleinschreibung, Leerraum, Trennstriche, ohne führende Nummer).
- **Fassungswechsel:** Die neue Fassung bekommt neue Knoten-IRIs. `rel_replaces` verbindet alte und neue Aussagen; der Wortlautvergleich läuft per Hash, sonst per Ähnlichkeit + Prüfung. Geprüfte Kanten der alten Fassung werden als Vorschläge an die neue weitergegeben, nie automatisch bestätigt.

---

## 12. Anpassung an Länder und Dokumente: das Lexikon

**Was mit „Länderbegriffen“ gemeint ist:** Für dieselbe Funktion nutzen die Länder verschiedene Wörter, Layouts und Kürzel – und dasselbe Wort bedeutet in zwei Ländern Verschiedenes.

| Ebene | Gleiche Funktion, verschiedene Begriffe | Gleicher Begriff, verschiedene Funktion |
|---|---|---|
| Dokument | Bildungsplan (BW), Kerncurriculum (HE, NI), Kernlehrplan (NW), Fachanforderungen (SH), Rahmenlehrplan (BE/BB) | „Rahmenlehrplan“: BE/BB-Schulplan oder KMK-Berufsschulplan |
| Gliederung | Inhaltsfeld (NW), Themenfeld (BE/BB), Leitidee (Mathematik), Kompetenzschwerpunkt (ST) | „Lernbereich“: Einheit mit Stunden (SN), Bereich (BY/TH), Fächerverbund (NRW-Gesamtschule) |
| Aussage | Kompetenzerwartung (BY, NW), Standard (BE/BB), Teilkompetenz (BW), Ziel des Kompetenzerwerbs (TH) | „Standard“: Erwartung im Landesplan, Regelstandard bei der KMK |
| Marker | L BNE (BW), [BNE]/[MD3] (MV), ⇒ Medienbildung (SN), P/I/F/L-Spalte (BW) | – |
| Niveau | A–H (BE/BB), G/M/E (BW), fett = E-Kurs (NI), ESA/MSA (SH) | „Niveau“, „Anforderung“ |
| Kita | Bildungsbereich, Bildungs- und Entwicklungsfeld (BW), Lernbereich und Erfahrungsfeld (NI), Bereichstitel je Land | „Bildungsplan“: Kita oder Schule |

**Verhältnis zu den heutigen Synonymen der App:** Die App-Profile führen je Elementtyp `synonyms_by_context` (Land → Begriffe), z. B. `NW: ["Kompetenzbereich", "Inhaltsfeld", …]` am Typ „bereich“. Das ist der richtige Gedanke – Begriffe gelten je Land. Ein `cur:LexicalCue` ist dieselbe Angabe, nur genauer:

| Synonymliste heute | Hinweis im Kern |
|---|---|
| Begriff → Typ | Begriff → Typ, Unterart, Dokumenttyp, Wert oder Eigenschaft |
| alle Einträge gleichrangig „synonym“ | Rolle: echtes Synonym (`alt`), bloßer Hinweis (`cue`), falscher Freund (`negative`), mehrdeutig mit Regel (`homonym`) |
| nur das Wort | Wort, Formmuster (Nummerierung), Layout (fett, Randspalte), Fundort (Überschrift, Tabellenkopf) |
| Geltung Land | Land, Dokumenttyp, Plangeneration, gültig von/bis, Träger, Fach |
| ungeprüft | Stärke, geprüft ja/nein, Testbeispiele |

Die bestehenden `synonyms_by_context` lassen sich mechanisch übernehmen: je Eintrag ein Hinweis mit Rolle `cue`, Geltung Land, Stärke 0,7, nicht geprüft. Danach werden sie an Originalen geprüft und auf `alt` hochgestuft oder als `homonym` mit Regel versehen. Am Beispiel „bereich“ in NW zeigt sich der Gewinn: „Kompetenzbereich“ und „Inhaltsfeld“ zeigen dann auf verschiedene Knotentypen und gehen nicht mehr in einem Typ „bereich“ auf.

### 12.1 Modell

`cur:TerminologyProfile` (je Bereich, mit `cur:profileScope`) enthält viele `cur:LexicalCue`.

| Feld | Bedeutung |
|---|---|
| `surfaceForm` / `pattern` / `layoutSignal` | Erkennungsform: Wort, Regex (Python-`re`) oder Layout (fett, kursiv, Randsymbol) |
| `cueRole` | **pref** (Vorzugsbezeichnung), **alt** (echtes Synonym), **cue** (Hinweis, kein Synonym), **negative** (falscher Freund, verweist auf Anderes), **homonym** (kontextabhängig; braucht `alsoMapsTo` oder Regeltext) |
| `cueKind` | term, headingPattern, tablePattern, sentencePattern, codePattern, layout |
| `mapsTo` / `alsoMapsTo` | Ziel(e): Knotentyp, Unterart, Dokumenttyp, Kernwert, Vokabularwert, Eigenschaft (Feldlexikon) bzw. Alternativziel |
| `occursIn` | Titelseite, Inhaltsverzeichnis, Überschrift, Fließtext, Tabellenkopf, Kasten, Kopf-/Fußzeile |
| Geltung | `scopeRegion`, `scopeDocumentType`, `scopeSector`, `scopeInstitutionType`, `scopeIssuer`, `scopeSubject`, `planGeneration`, `validFrom`/`validUntil` |
| `strength` | 0–1; ab 0,9 klassifiziert die Pipeline deterministisch ohne LLM, ab 0,8 markiert der Prompt ein starkes Signal |
| `verified` | am Original geprüft |
| `recognitionHint` / `negativeHint` | Regeltext für das LLM bzw. Warnung |
| `positiveExample` / `negativeExample` | Testfälle, die `pruefe.py` gegen das Muster prüft |

**Warum keine altLabels und keine skos-xl-Labels:** `altLabel` behauptet Gleichheit. In ELEM wurden so 28 Länder-Wortlaute zu Synonymen ihrer Konzepte, gleich dem prefLabel (SKOS-Integritätsverstoß S13), und Dokumenttitel wurden zu Synonymen von Dokumenttypen. Ein Hinweis behauptet nur Erkennbarkeit.

### 12.2 Aktives Profil

Für ein Dokument filtert die Pipeline alle Hinweise des Bereichs nach Land(en), Dokumenttyp und Plangeneration. Nur dieser Ausschnitt geht in die Prompts von X1, X3 und X4; laut ELEM sind das etwa 50–80 Zeilen statt aller Hinweise. In X1 kommt das **Dokumentprofil** dazu: die dokumenteigenen Begriffe (`termMappings`), neue Begriffe für die Prüfliste (`newTerms`) und Tabellenschemata (Spalte → Eigenschaft). Es wird gespeichert und allen Folgeaufrufen mitgegeben.

**Muster nach Form, nicht nach Wörtern.** Diese App-Lehre ist mit Testfällen belegt; die Muster sind in `schule.ttl`, `beruf.ttl`, `hochschule.ttl` und `erwachsenenbildung.ttl` mit Positiv- und Negativbeispielen hinterlegt. Fünf BBO-Muster und vier EB-Muster waren fehlerhaft und sind korrigiert, etwa:

- `^Lernfeld\s+\d+[A-Z]*\b\s*:?` trifft auch „Lernfeld 5 Kunden“ und „13GH“;
- das ÜLU-Muster ohne `$`-Anker trifft auch „G-MET2/19 Schweißen“;
- die Wahlregel trifft auch „zwei der folgenden zehn Wahlqualifikationen“;
- „Weiß, dass“ wird erkannt;
- lea.-Bezüge werden alle gefunden, nicht nur der erste.

**Homonyme mit Regel:**

| Begriff | Bedeutungen und Unterscheidung |
|---|---|
| „Lernbereich“ | SN mit „Ustd.“ = Einheit; BY/TH = Bereich; NRW-Gesamtschule = Fächerverbund (eigenes Curriculum); Fachschule = Bereich |
| „Standard“ | Landeslehrplan = Kompetenzerwartung; KMK = Regelstandard |
| „Themenfeld“ | mit Zeit oder Verbindlichkeit = Einheit, sonst Bereich |
| „Niveau“ | A–H = Kompetenzstufe; grundlegend/erhöht = Kursniveau; G/M/E = BW-Niveau |
| „Handlungsfeld“ | Beruf = berufliche Gliederung; EB = Lebensbereich |
| „Lernfeld“ in der EB | Fremdbegriff |
| sonstige | „Praktikum“, „P“, „SWS“, „dual“, „Modulkatalog“, „Technische Hochschule“, „BA“, „UE“, „Schwerpunkt“, „Kompetenzbereich“ (Kita) |

### 12.3 Bestand

| Profil | von Hand | generiert | Quelle der Generierung |
|---|---|---|---|
| Schule | 112 | 375 | FWU-Länderklassen (CC BY-SA 4.0); Begriffe, die ein Handhinweis desselben Landes abdeckt, sind ausgelassen. Die FWU-Daten sind nur für einen Teil der Länder belastbar – ein Startbestand, der die Länderrecherche nicht ersetzt |
| Elementar | 34 | 239 | 201 ELEM-Hinweise, je Land aufgefächert, ELEM-Fehler H.6 Nr. 2–6 korrigiert |
| Beruf | 55 | – | 43 BBO-Hinweise (korrigiert) + Dokumenttyp-, Zeit-, Prüfungs- und Entsprechungssignale |
| Hochschule | 21 | 395 | 396 HCO-Einträge (Feldlexikon des Modulsteckbriefs), HCO-Fehler H.9 korrigiert |
| Erwachsenenbildung | 34 | – | 24 EB-CO-Regeln (korrigiert) + Ergänzungen |

Der Kollisionsbericht von `pruefe.py` listet gleiche Formen mit verschiedenen Zielen in überlappender Geltung ohne Homonym-Rolle. Übrig sind drei Fälle aus dem HCO-Lexikon („Modulübersicht“, „Studienverlaufsplan“, „Applicability“), die tatsächlich doppelt zeigen und bei der Lexikonpflege zu entscheiden sind.

### 12.4 Vorgehen bei regionalen Besonderheiten

**Drei Ebenen, die spezifischere gewinnt:**

1. **Dokumentprofil** (`cur:DocumentProfile`, in X1 erzeugt): Besonderheiten genau eines Dokuments, z. B. eine eigene Tabellenspalte. Sie gehen nicht ins Lexikon, solange sie nur ein Dokument betreffen.
2. **Länderhinweise** (`cur:scopeRegion`, oft auch Dokumenttyp und Plangeneration): geprüfte vor ungeprüften, stärkere vor schwächeren.
3. **Bereichshinweise ohne Land** und die Definitionen der Knotentypen.

Bei Gleichstand entscheidet die Stärke. Liegen zwei Hinweise gleich auf, geht der Fall ans LLM mit beiden Regeltexten.

**Ablauf für ein Land (oder einen Träger):**

1. **Länder-Steckbrief erheben** (Recherche, Aufträge in `recherche-auftraege/`): Dokumentlandschaft und Plangenerationen, Gliederungsmuster je Dokumenttyp, Begriffe mit Funktion und Beispiel, Querschnittslegende, Niveausystem, Schularten bzw. Bildungsorte.
2. **Ins Lexikon übernehmen:** je Begriff ein Hinweis mit Rolle, Geltung und Fundstelle. Begriffe aus der Recherche bekommen höchstens Stärke 0,7 und „nicht geprüft“. Ein neues Gliederungsmuster wird ein Formmuster mit Positiv- und Negativbeispiel. Ein neuer Knotentyp kommt nur hinzu, wenn sich die Funktion von allen vorhandenen unterscheidet.
3. **Prüfen:** `pruefe.py` (Muster gegen Beispiele, Kollisionsbericht); dann ein Pilot an 2–3 Originaldokumenten des Landes mit Replay gegen den Goldstandard.
4. **Hochstufen:** Was im Pilot trägt, wird `verified true` mit Fundstelle; die Stärke steigt bis 0,9. Ab 0,9 typisiert die Pipeline ohne LLM.
5. **Laufend pflegen:** X1 meldet unbekannte Gliederungsbegriffe (`newTerms`). Die Redaktion entscheidet in der Review-Oberfläche „neuer Hinweis / Dokumentbesonderheit / Fehler“. Danach folgen Replay und Kollisionsbericht. Neue Plangenerationen bekommen eigene Hinweise mit `validFrom`; alte bleiben mit `validUntil`.

**Dateiorganisation:** Eine Unterontologie je Land, also eigene Klassen, gibt es nicht. Länderwissen ist Lexikondaten. Für Pflege und Review ist aber **eine Datei je Bereich und Land** sinnvoll, z. B. `profile/laender/schule-DE-NW.ttl`. Sie enthält die Hinweise des Landes und einen `cur:TerminologyProfile` mit `cur:profileScope` (Bereich + Land), der als Kommentar den Steckbrief trägt (Gliederungsmuster, Plangenerationen, Besonderheiten). Die Pipeline lädt Bereichsdatei + Länderdatei(en). Die heutigen Länderhinweise stehen noch in den Bereichsdateien. Getrennt wird, sobald die Rechercheergebnisse vorliegen – sonst bekämen die meisten Länder nur fast leere Dateien.

---

## 13. Pipeline

### 13.1 Lesekontext: ganzes Dokument lesen, für eine Einheit antworten

Die Genauigkeit steigt, wenn das Modell mehr als den Ausschnitt sieht. Ob ein Satz eine Erwartung oder ein Hinweis ist, ob „Lernbereich“ eine Einheit ist und welche Legende ein Kürzel auflöst, steht oft woanders im Dokument. Die App macht es heute schon so, und das bleibt die Regel:

- **Gemeinsamer, gecachter Präfix** für alle Aufrufe eines Dokuments: das ganze Dokument als Blocktext mit Block-IDs, dazu das Dokumentprofil aus X1 und die Auswahllisten aus X3 (Kompetenzmodell, Legende, Operatoren). Dahinter steht der Cache-Haltepunkt. In der App lesen so 15 von 16 parallelen Aufrufen Dokument und Anweisungen aus dem Cache (gemessen).
- **Auftrag dahinter, je Einheit verschieden:** „Gib die Aussagen der Einheit K12 (Blöcke p36-b1 bis p37-b9) zurück“, mit dem Titelpfad der Elternknoten und dem aktiven Lexikonausschnitt. Der Blockbereich legt fest, **wofür** geantwortet wird, nicht, **was** gelesen wird.
- **Gespeichert wird nur, was belegt ist:** Wortlaut + Block-IDs der Antwort, in X5 gegen genau diese Blöcke geprüft. Was das Modell aus dem Umfeld erschließt (Verbindlichkeit aus dem Vorwort, Niveau aus der Tabellenüberschrift), wird als Wert mit Herkunft `inherited` oder `rule` und der Fundstelle der Quelle gespeichert, nicht als Wortlaut der Aussage.
- **Zu lange Dokumente** (über dem Kontextbudget): Der Präfix besteht dann aus Titelei, Inhaltsverzeichnis, Rahmenteilen und dem Abschnitt der Einheit samt Nachbarabschnitten. Den Rest vertritt das Gerüst mit Titeln. Die Grenze wird gemessen, nicht geschätzt.

### 13.2 Stufen

| Stufe | Was | LLM | Schema | Ausgabe |
|---|---|---|---|---|
| **X0** Parsen | Layout-Blöcke mit Seite, BBox, Schrift, fett/kursiv, Tabellenzellen; Block-IDs; Kopf-/Fußzeilen markieren; Encoding prüfen; Zeichen aus Symbolschriften (Private Use Area U+F0xx, z. B. Wingdings 3) auf Unicode abbilden, sonst fehlen Layoutsignale im Text (SN: U+F0DA → ➔ Verweis, U+F0DE → ⇒ Querschnitt); Tabellen über Seiten zusammenführen | nein | – | Blockliste |
| **X1** Dokumentprofil und Gerüst | Titelei, Impressum, Inhaltsverzeichnis, Vorwortanfang → Metadaten, Spezifikationen, Varianten, dokumenteigene Begriffe. Gerüst deterministisch aus Inhaltsverzeichnis/Layout/Lexikon; nur unklare Überschriften gehen an das LLM | 1–2 Aufrufe | `x1-dokumentprofil`, `x1-gliederung` | Dokument, Spezifikationen, Knoten mit Seitenbereich |
| **X2** Segmentieren | Einheiten mit Seitenbereich schneiden (nie an festen Tokengrenzen; Abschnitte über ~15 Seiten an Unterknoten teilen); Muster mit Stärke ≥ 0,9 typisieren deterministisch | nein | – | Arbeitspakete |
| **X3** Rahmenteile | einmal je Dokument: Kompetenz- und Niveaumodell, Operatorenliste, Querschnittslegende, Regeln, Bildungsziele, Aufträge | 1–3 | `x3-rahmenteile` | Auswahllisten für X4 |
| **X4** Aussagen je Einheit | Dokument im gecachten Präfix (13.1), Auftrag je Einheit mit ihrem Blockbereich; Aussagen als Blätter im Wortlaut mit Art, Unterart, Adressat, Verbindlichkeit, Layout, Wortlaut-Feldern | ⌈Einheiten/Bündel⌉ | `x4-aussagen` | Aussagen |
| **X5** Prüfen | Wortlaut gegen Blöcke (Fundart), SHACL, Summen, Pflichtfelder | nein | – | Befunde |
| **X6** Reparatur | nur fehlerhafte Einheiten erneut | 0–2 | wie X4 | |
| **N1** Zerlegen und Normalisieren | Zerlegung; Hub-Kandidaten per Embedding, Wahl aus nummerierter Liste | ⌈Aussagen/50⌉ | `n1-zerlegung` | Zerlegungen, Konzeptbezüge |
| **N2** Anbinden | Hub-Konzepte gegen Normdaten (Wikidata, GND, ESCO) und Rahmen, einmal je Konzept | Reconciliation/Embedding; LLM höchstens als Wahl aus Liste | – | Zuordnungen an Konzepten |
| **G1** Kanten | Retrieval + Rerank → höchstens 40 nummerierte Kandidaten → Wahl der Kantenart (10 erlaubte) mit Begründung; Konfidenz berechnet die Pipeline | ja, im Batch | `g1-kanten` | Zuordnungen (proposed) |

**Budget (Planung, nicht gemessen):** Ein Lehrplan mit 15 Einheiten braucht etwa 1–2 + 1–3 + 8–15 Aufrufe in L1; Kita-Pläne laut ELEM 6–12, ein RLP mit 13 Lernfeldern laut BBO etwa 6. L2/L3 laufen als Batch über viele Dokumente. Die Kosten folgen der Zahl der Containerknoten, nicht der Seitenzahl. Das hat die App gemessen: eine Schachtelung im LLM kostete das Fünffache.

**JSON-Schemas** (`schemas/`, erzeugt von `werkzeuge/erzeuge_schemas.py`):

- strikt-kompatibel: jedes Objekt geschlossen, alle Felder Pflicht, Optionales als `null`;
- Enums = `skos:notation` der Kernschemata, markiert mit `x-cv-scheme`; `pruefe.py` prüft die Gleichheit;
- Profilwerte (Knotentyp, Unterart, Dokumenttyp) sind Zeichenketten aus der nummerierten Liste im Prompt und werden gegen das aktive Profil geprüft;
- das Modell liefert keine Konfidenzen, Seiten oder IRIs.

---

## 14. Prüfung

**SHACL in drei Schichten** (`cur-shapes.ttl`, `profil-shapes.ttl`):

- **Violation** – Struktur, die jede Extraktion erfüllen muss:
  - Pflichtfelder, Wertelisten, Kardinalitäten;
  - Baum ohne Zyklen; Aussagen als Blätter; Funktion = Knotentyp; Unterart passt zur Art;
  - Kompetenzkonzept nur bei Lernenden; DQR nicht an Aussagen; Bloom nur mit Herkunft;
  - Herkunftsregeln der Zuordnungen; Gewichte ≤ 100 %; Auswahlregel mit mindestens zwei Optionen; Block-ID-Format.
- **Warning** – Vollständigkeit und Plausibilität:
  - Herausgeber fehlt; Curriculum ohne Fach; Knoten ohne Fundstelle oder Typ;
  - Lernergebnis an Lehrkraft; unscharfe Fundstelle; AFB an Erwartung; Rückprobe;
  - `buildsOn` ohne gemeinsames Konzept; `exactMatch` auf ESCO; Kurzform ohne Deckung; Anrechnung > 50 %;
  - Profilregeln: Modul ohne LP/Lernergebnis, Workload-Plausibilität, Semesterlast, Lernfeld ohne Zeit, Zwischenprüfung mit Gewicht, Regelstandard im Landeslehrplan, Bildungsbereich ohne Feld, Niveaustufe ohne Niveau.
- **Info** – Arbeitsstand (Lernergebnis noch nicht zerlegt).

**Aufruf ohne Inferenz**, mit Ontologie, Vokabularen und Profilen im Datengraph. Die SCO-Anleitung empfahl RDFS-Inferenz; das verdeckt 22 Klassenprüfungen. Der dokumentierte ELEM-Aufruf (`pyshacl -e`) funktioniert mit pyshacl 0.40 nicht. BBO validiert nur mit dem Kern im Datengraph.

**`pruefung/pruefe.py`** (Python, rdflib + pyshacl, kein Netz) prüft:

1. Parsen und undefinierte Terme;
2. prefLabel@de und Schema; Notationen eindeutig;
3. Knotentyp, Unterart und Dokumenttyp mit genau einer Kernoberklasse;
4. Lexikon: Pflichtfelder, Homonym-Regel, Regex kompiliert und trifft die eigenen Beispiele;
5. JSON-Enums gleich den Vokabularen; Schemas strikt;
6. SHACL: Positivbeispiele konform, Negativbeispiele erzeugen genau die deklarierten Violations (`ex:expectsViolationOf`) und Warnungen (`ex:expectsWarningOf`);
7. `owl:imports`;
8. Anwendungsfall-Abfragen liefern Treffer.

Dazu kommt ein Kollisionsbericht. **Ergebnis am 19.10.2026: OK** (Zahlen in Abschnitt 0).

---

## 15. Bereichsprofile

### 15.1 Schule (`schul:`, Quelle SCO v2 + FWU + Andock-Lexikon)

- **Knotentypen:** Stufenabschnitt, Kompetenzbereich, Inhaltsbereich, Integrierter Bereich, Unterrichtseinheit, Teilbereich, Querschnittsbereich, Entwicklungsbereich, Rahmenteil, Verzeichnis. BE/BB Teil C ist ein eigenes Curriculum.
- **Unterarten:** Kompetenzerwartung (übergeordnet/konkretisiert), zusammenfassende Erwartung (BY „Grundlegende Kompetenzen“), niveaugebundene Erwartung (Tabellenzellen A–H, G/M/E, HH), Regelstandard, Inhalt, Fachbegriff, Experiment, Hinweis, Verweis, Bildungsbeitrag, Unterrichtsauftrag.
- **Geltung:** KIM-Schularten + Landesschularten, 7 Förderschwerpunkte, ziel-gleich/-different, Schulphasen, Stellung des Fachs.
- **Übernommen:**
  - Länder-Matrix und 92 Hinweise als Lexikon;
  - Querschnittslegenden (BW L-Kürzel, MV [BNE]/[MD], SN ⇒);
  - Verweisspalten (BW P/I/F/L, SN ➔);
  - Niveausysteme und das Prinzip „Standard ≠ Standard“.
- **Verworfen:** OWL-Länderklassen; RDFS-Inferenz in der Prüfanleitung; ein eigener `cur:`-Namensraum (`w3id.org/oeh/curriculum/kern#`).
- **Offen:** [DRF] (MV) ohne Legende; [MD1–6] als KMK-Bereich vermutet; Modul BY, Kerninhalt NI, Basisbegriff SL und Gegenstand BE/BB unverifiziert.

### 15.2 Elementarbildung (`elem:`, Quelle ELEM V2 + Archiv)

- **Knotentypen:** die 16 ELEM-Rollen mit Kernfunktion, darunter Leitbild (grouping), Bildungsbereich, Alltagssituation (area mit Kontext), Querschnitt und Basiskompetenzen (crossCutting) sowie neun Rahmenteile (typed/skip).
- **Unterarten:** Bildungsziel, Kompetenzbeschreibung, Bildungsanspruch, Grundsatz, Fachkraft-Aufgabe, Qualitätsanspruch, Entwicklungsindikator, Inhalt, Impuls, Reflexionsfrage, Praxisbeispiel.
- **Feldvokabular** `elem:Fields`: die 7 Bildungsbereiche des Gemeinsamen Rahmens mit 33 Unterkonzepten, Brücken zu KIM-Schulfächern und zum Querschnitts-Hub. **Prinzipien** `elem:Principles` (15) am Hub. **Bildungsorte** (Krippe, Kindergarten, Kita, KTP, Hort, Grundschule).
- **Übernommen:**
  - Werk/Fassung; Curriculum ↔ Dokument n:m; Knoten einmal je Dokument mit `appliesTo`; Extraktionstiefe;
  - Adressat als Pflicht; Altersband in Monaten; Entwicklungsqualifikator;
  - alle 201 Hinweise.
- **Verworfen:**
  - Kindziel-Ableitung als Aussage (Dubletten, Paraphrase);
  - 21 OWL-definierte Profilklassen (Reasoner-Pflicht);
  - drei Konfidenzen;
  - `weitereRolle`, `gebuendeltUnter` und `anteil` als Pflicht;
  - die DigComp-Abbildung von „Prävention und Sicherheit“.
- **Korrigiert:**
  - 28 SKOS-Konflikte (durch Hinweise statt Labels);
  - Dokumenttitel als altLabel;
  - Bildungsdimension TH;
  - Bereiche ohne Weltausschnitt;
  - SL-Bereichsname (vermutlich BE 2014);
  - gemischte SH-Fassungen.

### 15.3 Berufliche Bildung (`beruf:`, Quelle BBO v0.2 + bb-*)

- **Knotentypen (25):**
  - Ordnungen: Verordnungsteil, Ausbildungsberufsbild, RLP-Rahmenteil;
  - ARP und RLP: Abschnitt ARP, Kernqualifikationen, Lernfeldteil, Lernfeld, Berufsbildposition, Standardberufsbildposition (Querschnitt);
  - Pflege und Bildungsgänge: Curriculare Einheit, Anforderungssituation, Bündelungsfach, Handlungsfeld, Kompetenzbereich/-schwerpunkt, Lernbereich, Fach, Lerngebiet, Modul;
  - Wahl und Lehrgänge: Wahlqualifikationseinheit, ÜLU-Lehrgang;
  - Fortbildung: Prüfungs-/Handlungsbereich, Qualifikationsschwerpunkt;
  - sonstige: Lernsituation, Verzeichnis.
- **Unterarten:** Kernkompetenz, Zielformulierung, FKF, PflAPrV-Kompetenz, Qualifikationsinhalt, Prüfungsanforderung, Inhalt, Bildungsauftrag, Hinweis, Ausbildungsauftrag.
- **Wertelisten:** Rechtsebene, Zuständigkeitsbereiche, Strukturparadigmen, Differenzierungsmodelle, Ordnungsregime R1–R5, Prüfungstypen (Zwischenprüfung ≠ AP Teil 1), Prüfungsinstrumente, Handlungsphasen, FKF-Kompetenzmodell. Lernort ist `beruf:learningPlace` ⊑ `cur:context`.
- **Kern-Entscheidungen aus der BBO:**
  - Lernortkooperation als amtliche `rel_correspondsTo`-Kante aus der Entsprechungsliste, n:m, nie `concretizes`;
  - DQR nur an der Qualifikation; Ausbildungsjahr ist Zeit;
  - Beruf als Andockpunkt Fach/Feld mit BIBB-Kennung und Jahresstand;
  - Varianten + Wahlregel.
- **Verworfen:** BFO, opake IDs, Typen als Klassen, 14 Zuordnungsarten (→ Kantenset des Kerns), `istKernkompetenz`, Integer-Nummern („13GH“).

### 15.4 Hochschule (`hs:`, Quelle HCO v1.0)

- **Knotentypen:** Ordnungsteil, Studiengangsprofil, Studienabschnitt, Studienbereich, Schwerpunkt/Studienrichtung (Bereich + Variante), Wahlpflichtkatalog, Modul, Praxisphase, Abschlussarbeit, Projekt, Künstlerisches Hauptfach, Lehrveranstaltung, Verzeichnis.
- **Dokumenttypen:** 21 HCO-Typen. Der Typ bestimmt nie die Verbindlichkeit; ein Modulhandbuch ist nur als Anlage (`hs:annexOf`) verbindlich.
- **Wertelisten (19):** MRVO-Fassungen, Hochschularten, Abschlussarten, 19 Grade, Studienformen, Studiengangstypen und -profile, Lehramtstypen, Rollen im Kombinationsstudium, Turnus, Lehrformen, Prüfungsformen, Voraussetzungsarten, Modultypen, Anrechnungsverfahren, nicht extrahierte Felder (Personendaten, Literatur).
- **Übernommen:**
  - `Placement` (ComponentUse) in den Kern;
  - Datei ≠ Dokument; Dokumentrelationen; Konfliktauflösung; Rechtsstatus aus Bekanntmachungsformeln;
  - Feldlexikon des Modulsteckbriefs (396 Einträge, der wichtigste Segmentierungshebel).
- **Korrigiert (H.9):**
  - `amends` ⊑ `supersedes`;
  - die HQR-Brücke (WV → Kenntnisse, EAE → Fertigkeiten, KK → Sozial, WSP → Selbstständigkeit);
  - Homonyme „Technische Hochschule“, „BA“, „UE“, „Fachrichtung“, „Leistungsnachweis“, „Curriculum“;
  - „Gewichtung der Note“ zeigt jetzt auf das Notengewicht;
  - das Muster `^Modul` (traf Modulhandbuch, Modulprüfung, Modulverantwortliche:r).
- **Verworfen:** paralleler `cc:`-Kern, Identitätsklassen als Extraktionsziel, fünf Regel-Unterklassen in eigener Hierarchie (jetzt Kern-Regeln), Modulverantwortliche (Personendaten).

### 15.5 Erwachsenen- und Weiterbildung (`eb:`, Quelle EB-CO v0.2)

- **Knotentypen:** Teil, Grundlagenkapitel, Niveaustufe (grouping mit Niveauzuordnung), Handlungsfeld (Lebensbereich-Kontext), übergreifender Kommunikationsbereich (crossCutting), Teilbereich, sprachliche Handlung, Modul/Kursabschnitt, Sachgebiet, Kompetenzbereich/-gruppe, Kompetenzeinheit (K1 ist Einheit, kein Lernergebnis), Prüfungsteil, Rubrik/Fokus, Verzeichnis.
- **Unterarten:** Kann-Beschreibung, Lernziel, Wissensaussage, Übersichts-Lernergebnis, Sensibilisierung (Bildungsziel), Niveaudeskriptor, Prüfungsziel, Bewertungskriterium, Sprachinventar, Inhalt, Vermittlungshinweis, Spiralverweis.
- **Wertelisten:** Programmbereiche (VHS) → ISCED-F, Trägerarten [A], Kursformate [A], Anerkennungskategorie Bildungsfreistellung (Länderbegriffe im Lexikon), sprachbezogene Inhaltstypen, GER-Aktivitäten als Kompetenzmodell. Die 12 Handlungsfelder stehen in `ctx:` und sind dort als zu prüfen markiert.
- **Übernommen:**
  - Dokument-Adressat ≠ Zielgruppe;
  - Zuordnungsart des Niveaus einmal je Dokument;
  - Tabellenschema einmal erkennen, dann deterministisch; Spiralverweise per Parser;
  - Entscheidungsregel Curriculum vs. Facette; Fortbildungsordnungen an `beruf:`.
- **Verworfen:** zweiter `cc:`-Kern, `elementRole`, ApplicabilityRule mit excludes, AFB und DIHK-Taxonomie in der EB, „Profile Deutsch“ als GER-Synonym.

### 15.6 Fehler in den Recherche-Ontologien (Auswahl; Details in den Prüferberichten)

| Paket | Befund | Behandlung |
|---|---|---|
| Andock-Entwurf | `cur:breiter` ↔ `ceasn:broadAlignment` in falscher Richtung; `folgtAuf` (Dokumentreihenfolge) ↔ CASE `precedes` | Kantenarten mit SKOS-Richtung; Position ≠ Reihenfolge |
| SCO | Prüfanleitung mit RDFS-Inferenz verdeckt 22 Klassenprüfungen | SHACL ohne Inferenz |
| ELEM | 28 SKOS-S13-Verstöße über skos-xl; Kindziel kopiert Quelltext; OWL-Profilklassen; `pyshacl -e`-Aufruf defekt | Hinweise statt Labels; keine abgeleiteten Aussagen; keine Reasoner-Pflicht |
| BBO | 5 fehlerhafte Regexe; Shapes nur mit Kern im Datengraph gültig; `konkretisiertDurch` richtungsunklar; Prüfungsbereich als Prüfungsart | korrigiert und getestet |
| bb-* | Lernfeld als „CE-Bereich ohne Inhalt“; Prüfungsteil ⊑ Prüfungsbereich umgekehrt; Kompetenzklassen disjunkt | Inhalte übernommen, Struktur verworfen |
| HCO | `amends` ⊑ `supersedes`; HQR-Brücke verschoben; `^Modul`-Muster; MRVO-Shape nur mit `-a`; Homonyme als altLabel | korrigiert |
| EB-CO | Severity wirkungslos; r03/r04 überlappend; r18 nur erster Treffer; r20 trifft nicht; Beispiel-Zerlegungen nicht im Wortlaut | korrigiert; Rückprobe als Warnregel |
| alle | sechs verschiedene Kern-Namensräume | ein Kern, Migrationstabelle |

---

## 16. Erkenntnisse aus der App und Empfehlung

| Befund aus der App (gemessen oder belegt) | Konsequenz im Modell |
|---|---|
| Kosten folgen der Zahl der Containerknoten; Schachtelung im LLM ×5 | Gerüst deterministisch; Aussagen als Blätter; ein Auftrag je Einheit über dem gecachten Dokument (13.1) |
| Regel in der Typbeschreibung schlägt den Vorspann (Titel im Wortlaut 37 → 100 %) | `cur:wordingRule`, `delimitation`, `positiveExample` am Knotentyp bzw. an der Unterart |
| Beispielklammern liest das Modell als abschließend; Platzierungssätze schaden | Beispiele als eigene Felder, nicht in Definitionen |
| Muster nach Form schlagen Wortmuster; Segmentierungsregeln wirken stark | `cueKind` + `segmentation`; Muster mit Testfällen |
| Vorschlagslisten erreichten das Prompt nie | Enums im JSON-Schema, aus dem Vokabular generiert |
| `typical_parents` wirken als harte Regel | `cur:typicalParent` nur als Hinweis, Funktion bleibt frei |
| Zitatpflicht wirkt (99–100 % verankert); unscharfe Anker wurden als wörtlich gezählt | `cur:matchKind` in der Fundstelle; Warnung bei fuzzy |
| Codes schlagen Text (KMK 351/351) | `cur:code` wie im Dokument, Zusammenführen über Codes |
| Deterministische Themenzuordnung mit Labelrollen erreichte Präzision 0,86 | Lexikonrollen; LLM nur als Wahl aus ≤ 40 nummerierten Kandidaten |
| Generisches Profil (UBO) verlor gegen das Bereichsprofil (EBO) | Kern + Bereichsprofile statt eines Universalprofils |
| Laufbezogene IDs verlieren Kanten bei Neuläufen | stabile IRIs aus Werk/Fassung/Strukturpfad |
| Ohne Replay und Goldstandard ist keine Änderung bewertbar | Goldstandard und Replay im Fahrplan vor jedem Profilwechsel |

**Empfehlung:**

- **Übernehmen** aus der App: Konvertierung (Docling, Mistral-OCR-Fallback), X0-Blöcke und Block-IDs, Zitat- und Ankerprüfung (Ankersuche mit Fundart), Job-System, Review-Oberfläche, Replay-Werkzeuge, Prompt-Cache-Erfahrungen.
- **Neu bauen:**
  - Datenmodell und Speicherung nach Kern 1.0 (RDF-nah; SQLite/JSON kann bleiben, wenn es die L1/L2/L3-Trennung abbildet);
  - Prompts je Stufe aus Profil + Lexikon generiert;
  - die neuen JSON-Schemas;
  - G1 als Batch mit Review-Warteschlange.
- **Nicht migrieren:** bestehende Profile 1:1. Sie werden über die Migrationstabelle und das Lexikon neu erzeugt.

---

## 17. Anwendungsfälle als Abfragen

Die Abfragen liegen in `pruefung/abfragen/` und laufen bei jeder Prüfung gegen die Beispiele.

| Abfrage | Frage | Ergebnis auf den Beispielen |
|---|---|---|
| `q1-thema-ueber-bereiche.rq` | Was lernt man zum Thema „Elektrizität“, in welchem Bildungsbereich? | 6 Treffer: Inhaltsfeld, Lernfeld und Aussagen zum Ohmschen Gesetz aus Schule, Berufsschule und Hochschule |
| `q2-lernpfad.rq` | Welche Aussagen bauen bestätigt aufeinander auf? | 2 Pfade (Berufsschule → Schule; Raster-Stufe 2 → 1) |
| `q3-vergleich.rq` | Welche Aussagen zweier Spezifikationen teilen ein Konzept, mit welcher Kante? | 6 Paare, davon eines bestätigt, eines vorgeschlagen |
| `q4-querschnitt.rq` | Wo wird ein Hub-Querschnittsziel verankert, auch über Quellschemata? | 3 Treffer (Kinderrechte über Kita-Prinzip, Landeskunde, Datenschutz) |
| `q5-ressource-lehrplan.rq` | Zu welchen Lernenden-Aussagen passt eine Ressource (AMB `teaches`)? | 1 Treffer |
| `q6-durchlaessigkeit.rq` | Welche Abschlüsse sind amtlich worauf anrechenbar, wo steht es? | 1 Treffer mit Zitat und Seite |

Beispiel q1 (gekürzt):

```sparql
SELECT DISTINCT ?sector ?spec ?element ?text WHERE {
  VALUES ?topic { ex:ic-elektrizitaet }                 # Einstieg: ein Thema
  ?concept skos:broader* ?topic .                       # das Thema und alle Begriffe darunter
  { ?element a cur:CurriculumNode ; cur:mentions ?concept ; cur:originalTitle ?text . }
  UNION
  { { ?d cur:decomposes ?element ; cur:mentions ?concept . } UNION { ?element a cur:Statement ; cur:mentions ?concept . }
    ?element cur:verbatim ?text ; cur:addressee cv:addr_learner . }
  ?element cur:partOf* ?n . ?n cur:partOf ?spec .
  ?spec a ?c . ?c rdfs:subClassOf* cur:Specification .
  ?doc cur:represents ?spec ; cur:educationSector ?sector .
}
```

---

## 18. Externe Bezüge und Belegstand

| Standard | IRI | Stand |
|---|---|---|
| EQF | `http://data.europa.eu/snb/eqf/1…8` | belegt |
| DQR (EU QDR) | `http://data.europa.eu/snb/qdr/c_f77c7095` (1) … `c_341d539b` (8), Rahmen `c_ef113b94` | belegt |
| ISCED-F (EU) | `http://data.europa.eu/snb/isced-f/<code>` | belegt |
| KIM ISCED 2013 / 2011 | `https://w3id.org/kim/isced-2013/n<code>`, `https://w3id.org/kim/isced-2011/levelN` | belegt |
| KIM Bildungsstufe | `https://w3id.org/kim/educationalLevel/level_0…5, A, 6–8, B, C` | belegt |
| KIM Schulfächer | `http://w3id.org/kim/schulfaecher/s10xx` (**http**) | belegt |
| KIM Schularten | `https://w3id.org/kim/schularten/s02…s16` | belegt |
| OEH Bildungskontext | `http://w3id.org/openeduhub/vocabs/educationalContext/…` | belegt (lokale Kopie) |
| ELM | 3.3 `http://data.europa.eu/snb/model/ontology/`; 3.2 `…/snb/model/elm/` | belegt |
| ESCO | `http://data.europa.eu/esco/model#`, `…/esco/skill/<uuid>`, v1.2.1 | belegt |
| CTDL-ASN | `https://purl.org/ctdlasn/terms/`; ProgressionModel in `http://purl.org/ASN/schema/core/` | teilweise belegt |
| CASE 1.1 | keine RDF-Terme, nur Tokens | belegt |
| GER (Wikidata) | Q221385; A1 Q104381878 … C2 Q104381943 | belegt |
| Länder (Wikidata) | BW Q985 … TH Q1205, DE Q183 | belegt |
| FWU Lehrplan-Ontologie | `https://w3id.org/lehrplan/ontology/LP_…` (CC BY-SA 4.0) | belegt (lokale Kopie) |
| schema.org | `https://schema.org/` | belegt |
| Bloom, KMK-Operatoren, KldB, BIBB, EU-Schlüsselkompetenzen, DigComp | keine stabilen URIs → eigene Schemata mit `dct:source` | – |

---

## 19. Übernahme der Hinweise des dritten Prüfers („Curriculum Core v1“)

| Empfehlung | Umsetzung |
|---|---|
| ein `cur:`-Namensraum, englische IRIs, Labels de/en | umgesetzt |
| SourceFile ≠ Document | umgesetzt, dazu Work und Collection |
| Specification mit 4 Untertypen | umgesetzt (SHACL xone) |
| CurriculumNode mit nodeFunction + nodeType + extractionDepth | umgesetzt (7 Funktionen) |
| Placement | umgesetzt, bereichsübergreifend |
| Statement mit statementKind + addressee; Profilklassen abgeleitet | umgesetzt; abgeleitete Klassen als `owl:equivalentClass` nur für Abfragen |
| Decomposition, Konzepte als Hubs, externe Mappings nur an Konzepten | umgesetzt (SHACL-Warnung bei ESCO-exactMatch von Aussagen) |
| n-äre LevelAssignment | umgesetzt, Dimension am Schema |
| eine Alignment-Klasse, ein Kantenvokabular, Herkunft × Prüfstand | umgesetzt (22 Kantenarten, 6 Herkünfte, 3 Prüfstände, 11 Methoden) |
| ein Lexikonmodell mit 5 Rollen, TerminologyProfile, DocumentProfile | umgesetzt |
| Pipeline X0–X6, N1–N2, G1 | umgesetzt (`cv:Stages`) |
| 8 Andockpunkte | umgesetzt |
| keine Skill-Zuordnung an der Aussage; AFB kein Niveau von Lernergebnissen; DQR nur an Qualifikation | umgesetzt als SHACL-Regeln |
| 12 Kern-Enums mit ≤ 10 Werten | **Abweichung:** 19 Schemata als LLM-Enum markiert (`cur:llmEnum`), jedes mit ≤ 10 Werten; je Stufe sieht das Modell nur die Enums ihres Schemas (X4: fünf) |
| SHACL: model ⇒ Konfidenz, nie amtlich; amtlich ⇒ Anker; Kompetenz nur bei Lernenden | umgesetzt (Violation) |

---

## 20. Offene Fragen

1. **Namensraum und Lizenz:** w3id-Registrierung (`wlo` oder `openeduhub`)? Lizenz des Kerns (Vorschlag CC BY 4.0)? Das FWU-Startlexikon ist CC BY-SA 4.0.
2. **Rechte an Wortlauten:** Bildungspläne sind oft amtliche Empfehlungen, nicht Gesetze; § 5 UrhG greift nicht ohne Weiteres. Wie viel Wortlaut darf gespeichert und gezeigt werden?
3. **Primärtexte prüfen:**
   - HQR 2017 und MRVO 2024 (Pflichtangaben, Benotung, Inkrafttreten je Land);
   - KMK-Handreichung RLP (Teile I–V oder I–VI, Bedeutung des Kursivsatzes);
   - Wortlaut der Wahlregeln in Ausbildungsordnungen;
   - BAMF-Mindestniveau-Formel; die 12 Handlungsfelder und die Bereiche B–D;
   - SH-Kita-Neufassung 2026, SL-Bereiche, MV [DRF], BW-Grundbedürfnisse;
   - Fortbildungsstufen 400/1 600 h.
4. **Kompetenz-Hub:** Clusterschwelle, Benennung und Zuständigkeit (Redaktion), Umgang mit Konzeptdrift über Fassungen.
5. **Gesamtstudiengang bei Kombi/Lehramt:** Als eigenes Curriculum geführt, droht doppelte LP-Zählung. Vorschlag: `cur:Programme` + Teil-Curricula.
6. **Kalibrierung:** Die Stärkeschwellen 0,8/0,9 und die G1-Kandidatenzahl sind nicht gemessen. Dafür braucht es den Goldstandard.
7. **Mehrsprachigkeit:** englische Studiengänge – eine Aussage je Sprache oder mehrsprachiger Wortlaut?
8. **Basiskompetenzen (Kita):** Modell (`kd:EarlyChildhood`) und Querschnitt zugleich – reicht die Doppelnutzung über den Knotentyp?
9. **Bildungsstandards und Raster:** Gibt es nutzbare SKOS-Ausgaben (IQB, KMK)? Wie werden Lizenz und Fassung der Deskriptoren (GER, DigComp, lea.) gelöst?
10. **Wann ein Profil einen neuen Knotentyp braucht** und wann ein Lexikonhinweis reicht (Pflegeprozess).
11. **Restkollisionen im HCO-Lexikon** („Modulübersicht“, „Studienverlaufsplan“, „Applicability“).

---

## 21. Fahrplan

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **0 Entscheiden** (1 Woche) | Namensraum, Lizenz, Freigabe Kern 1.0-rc; offene Fragen 1–2 | Kern 1.0-rc |
| **0b Länderrecherche** (parallel, 2–4 Wochen) | Aufträge aus `recherche-auftraege/`, etwa 45–50 Läufe: Schule und Elementar je ein Land je Lauf; Beruf Überblick über alle Länder + Detail nur für Länder mit eigenen Lehrplanbeständen; Hochschule, Erwachsenenbildung und Querschnitt/Niveau als Sammelläufe, Noten- und Verhaltensskalen in vier Läufen zu je vier Ländern. Erst Piloten (NW, SN, BB, Beruf-Überblick), dann der Rest. Ergebnisse als Tabellen, Abgleich mit den Vorlisten, Übernahme nach 12.4 | Länder-Steckbriefe, Länderhinweise (ungeprüft) |
| **1 Goldstandard** (2–3 Wochen) | Je Bereich 6–10 Dokumente, geschichtet nach Land/Typ; je Dokument ~50 Aussagen von Hand; Messgrößen: Gerüst (Baumähnlichkeit), Aussagen (F1, Wortlaut-Treffer), Art/Adressat (Genauigkeit), Lexikontreffer | Goldkorpus + Replay-Harness |
| **2 L1 in der App** (4–6 Wochen) | X0/X2/X5 aus der App übernehmen; X1/X3/X4 mit den neuen Schemas; Prompts aus Profil + Lexikon generiert; Replay gegen Gold; Lexikonpflege aus `newTerms` | Extraktion nach Kern 1.0 für alle Bereiche |
| **3 L2** (3–4 Wochen) | N1 Zerlegung + Hubs (Embedding + Wahl); N2 Normdaten; Import erster Rahmen (Bildungsstandards Primar/MSA, GER, DigComp) | Hubs, Rahmen |
| **4 L3 + Landkarte** (4 Wochen) | G1 im Batch, Review-Warteschlange, Kurzformen; Abfragen q1–q6 als API; Lernpfad- und Vergleichsansicht | Bildungslandkarte v1 |
| **5 Konsolidieren** | LinkML als Einzelquelle für Kern + Schemas + Shapes; Veröffentlichung (SkoHub) nach w3id-Registrierung; Versionierung | Kern 1.1 |

**Vor jeder Profiländerung:** Replay gegen Gold, dann `pruefe.py`, dann den Kollisionsbericht lesen.

---

## Anhang A – Arbeitsweise

- **Grundlagen:**
  - die fünf Bereichsspezifikationen mit TTL, Shapes und Beispielen sowie die Deep-Research-Berichte;
  - der Andock-Entwurf;
  - die Vorarbeiten in `wissen/` und `data/sources` (UBO 0.2, FWU, KIM, IQB, ELM);
  - das Profilwissen der App;
  - die Hinweise des dritten Prüfers.
- **Neun Prüferberichte** (je Bereich, App, UBO, lokale Vokabulare, externe IRIs) wurden zu einer Querschnittssynthese zusammengeführt. Die Bereichsberichte liegen nicht im Repository; ihre Befunde sind hier und in den Kopfkommentaren der TTL-Dateien zusammengefasst.
- **Alle Beispiele sind fiktiv** (nach dem Muster echter Pläne); es werden keine Originalwortlaute geschützter Rahmen wiedergegeben.
- **Prüfung:**

  ```bash
  python -I pruefung/pruefe.py
  ```

  Mit einem Python, das `rdflib` und `pyshacl` hat; im Repository das `.venv` des Backends.
