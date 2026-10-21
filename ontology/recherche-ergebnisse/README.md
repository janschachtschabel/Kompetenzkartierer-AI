# Rechercheergebnisse

Rohberichte der Rechercheläufe aus [`../recherche-auftraege/`](../recherche-auftraege/README.md), ein Bericht je Lauf. Jeder Bericht hat eine Zusammenfassung und danach die Tabellen als CSV-Blöcke. Die Berichte sind **ungeprüft**: Sie gehen erst über den Importer (noch zu schreiben) und die Redaktion ins Lexikon.

**Erzeugung:** Recherche-Agenten (Sonnet, mittlerer Aufwand) lesen Auftrag und Vorlisten und recherchieren im Web, nur lesend. Ihr Endbericht wird unverändert hier abgelegt; die erste Zeile vermerkt Lauf, Modell und Datum.

**Grenze der Belege:** Das Abrufwerkzeug gibt Webseiten und PDFs als maschinelle Aufbereitung zurück, nicht als Rohtext. Beleg E heißt deshalb nur: Die Stelle wurde im Primärdokument gefunden, mit URL und Seite. Wörtlich ist sie damit nicht gesichert. Der Bayern-Lauf weist darauf ausdrücklich hin, weil die LehrplanPLUS-Webseiten keine Seitenzahlen haben. Titel, Begriffe und Muster müssen vor der Übernahme am Originaldokument geprüft werden, ebenso Fett- und Kursivsatz, den die Textextraktion nicht zeigt (Konzept 12.4, Pilot an Originaldokumenten).

**Prüfen** (aus `ergebnis/`):

```bash
python -I werkzeuge/pruefe_recherche.py . recherche-ergebnisse/<datei>.md
```

Die Prüfung zeigt je Tabelle die Zeilenzahl, die verschobenen Zeilen (Semikolon im Feld), feste Werte außerhalb der Liste, unbekannte `ziel_id` und den Anteil der Belege E (am Primärdokument mit Seite).

## Pilotläufe (2026-10-20)

| Datei | Lauf | Zeilen T3 | verschoben | Beleg E | Vorliste |
|---|---|---|---|---|---|
| [`01-schule-DE-NW.md`](01-schule-DE-NW.md) | Schule NW | 53 | 3 von 146 (alle in T2) | 67–100 % | 12 bestätigt, 5 korrigiert, 6 nicht gefunden |
| [`01-schule-DE-SN.md`](01-schule-DE-SN.md) | Schule SN | 41 | 3 von 117 | 95–100 % | 8 bestätigt, 11 korrigiert, 1 nicht gefunden |
| [`02-elementar-DE-BB.md`](02-elementar-DE-BB.md) | Elementar BB | 61 | 0 von 112 (erste Ausgabe: 55 von 111) | 60–100 % | 17 bestätigt, 2 korrigiert, 1 nicht gefunden |
| [`03A-beruf-ueberblick.md`](03A-beruf-ueberblick.md) | Beruf, Überblick 16 Länder | – | 1 von 120 | 12 % (T0), 25 % (T1) | – |

**Format.**

- Die Schulläufe sind fast sauber.
- Im Elementarlauf BB standen in der ersten Ausgabe in der Hälfte der Zeilen Semikolons im Feld. Dort fehlten auch die Bildungsbereiche, Prinzipien und Kontexte in der Zielliste, deshalb hat der Lauf IDs erfunden (`ctx:reading`, `ctx:outdoor`, `ctx:arrival-departure` statt `ctx:arrival-farewell`).

Zwei Korrekturen gelten seither für alle Aufträge. Mit ihnen hat der Lauf BB seine Tabellen ohne neue Recherche neu ausgegeben: keine verschobene Zeile, keine unbekannte ID.

1. **CSV-Regeln:** kein Semikolon im Feld, Mehrfachwerte mit „ | “, feste Werte ohne Umlaute, `ziel_id` nur aus der Zielliste.
2. **Ziellisten:** Sie enthalten jetzt auch die Konzepte der Profilschemata (Bildungsbereiche, Prinzipien, Bildungsorte, Schularten …) und die gemeinsamen Vokabulare `ctx:`, `qz:`, `lvl:` und `kd:`. Das sind 374–466 IDs je Bereich statt 31–52.

**Inhalt – was ins Lexikon und ins Konzept gehört:**

- **NW Schule:**
  - Drei Plangenerationen laufen nebeneinander (2011, 2019–2023, Oberstufe 2022/23; neue Oberstufe ab 01.08.2027).
  - Erkennbar sind sie an „Progressionsstufe“ und „Mögliche Kontexte“ (2011) gegenüber „Erprobungsstufe“ und „Ende der Sekundarstufe I“.
  - Kompetenzerwartungen verweisen per Klammerkürzel „(UF1, E6)“ auf übergeordnete Erwartungen. Das ist ein Verweis, kein Label.
  - Querschnittskürzel („MKR 2.1“, „VB Ü“) stehen nur in den Integrationstabellen des Sachunterrichts.
  - 6 Vorlisteneinträge gibt es nicht, u. a. „Lehrplanfragment“, „Doppeljahrgangsstufe“ und „Fachliche Konkretisierung“.
- **SN Schule:**
  - Verweise (➔) und Querschnittsmarken (⇒) stehen in der Textschicht als Wingdings-Zeichen U+F0DA und U+F0DE. Sie müssen bei der Vorverarbeitung (X0) abgebildet werden.
  - Es gibt sieben Zielbegriffe; „Beherrschen“ und „Problemlösen“ fehlen im heutigen Muster.
  - Generation 2025 (Grundschule Deutsch): „Lernbereich“ meint dort den Kompetenzbereich, Zeitrichtwerte fehlen.
  - „Querschnitt:“ und „Längsschnitt:“ sind in Geschichte Homonyme. „Wahlpflichtbereich“ bezeichnet die Schulorganisation, nicht die Gliederung.
- **BB Elementar:**
  - Die Fassung 2024 hat 10 Bildungsbereiche (2004: 6) und 18 Alltagssituationen in 4 Gruppen.
  - Fachkräfte werden mit „ihr“ und im Imperativ angesprochen; das Muster „Pädagogische Fachkräfte …“ trifft das nicht.
  - „Umsetzungsideen“ wurde nicht gefunden, ein Bezug auf den Gemeinsamen Rahmen ebenfalls nicht.
- **Beruf, Überblick:**
  - Detailläufe empfohlen für NW, BY, BW, SN, RP und NI.
  - Der Beleganteil E ist niedrig. Mehrere Landesserver antworteten mit 403/404/500/503, und Bestandsangaben stammen oft aus Portalseiten statt aus den Plänen. Die Detailläufe prüfen diese Zeilen nach.

## Läufe

| Welle | Läufe | Stand |
|---|---|---|
| Pilot | Schule NW, SN · Elementar BB · Beruf A | fertig; BB-Tabellen nach den CSV-Regeln neu ausgegeben |
| 1 | Beruf B: NW, BY, BW, SN, RP, NI · Elementar HE, NW | fertig 2026-10-20 (Tabelle unten) |
| 2 (fortlaufend, je fertigem Lauf ein neuer) | Schule: alle 14 übrigen Länder · Elementar: alle 13 übrigen Länder | fertig 2026-10-20 (Tabellen unten) |
| 3 | 06 B Abschlüsse, Niveaus, Schularten (06 A entfällt, weil 01 die Tabellen T4–T6 je Land schon liefert) · 04 A Hochschule Länder · 04 B Modulhandbücher · 05 A Erwachsenenbildung Länder · 05 B Rahmendokumente | fertig 2026-10-20 (unten) |
| 4 | 07 A–D Noten- und Verhaltensskalen, je vier Länder; TH Modi der Weltaneignung | fertig 2026-10-21 (unten) |

Zwei Läufe hielten die CSV-Regeln nicht ein: Schule TH (46 verschobene Zeilen) und Schule RP (17). Beide haben ihre Tabellen ohne neue Recherche neu ausgegeben. Die Zahlen unten zeigen den Stand danach.

**Welle 2 – Prüfergebnis Schule:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`01-schule-DE-BB.md`](01-schule-DE-BB.md) | 162 | 0 | 74 | 76 % | Fachteil-PDFs enthalten Berliner und Brandenburger Seiten (Kopfzeile filtern) |
| [`01-schule-DE-BE.md`](01-schule-DE-BE.md) | 194 | 1 | 89 | 100 % | wie BB; Teil C dreiteilig, Niveaustufen A–H als Matrix |
| [`01-schule-DE-BW.md`](01-schule-DE-BW.md) | 116 | 1 | 45 | 98 % | drei Plangenerationen BP2016, V2, V3.0 (G9 neu) |
| [`01-schule-DE-BY.md`](01-schule-DE-BY.md) | 130 | 0 | 46 | 98 % | LehrplanPLUS nur als Web-Aufbereitung, ohne Seitenzahlen |
| [`01-schule-DE-HB.md`](01-schule-DE-HB.md) | 157 | 0 | 79 | 90 % | neue Sek-I-Pläne ab 2026/27; Bildungsplan 0–10 für die Grundschule |
| [`01-schule-DE-HE.md`](01-schule-DE-HE.md) | 130 | 0 | 52 | 98 % | Kerncurricula 2011 neben Lehrplänen 2002; KCGO 2016 und 2024 |
| [`01-schule-DE-HH.md`](01-schule-DE-HH.md) | 172 | 3 | 64 | 100 % | Bildungsplan 2022 mit Teil A/B/C; Rahmenpläne in Erprobung bis 2027 |
| [`01-schule-DE-MV.md`](01-schule-DE-MV.md) | 150 | 2 | 59 | 100 % | vier Rahmenplan-Generationen mit wechselnden Kapiteln und Kürzeln |
| [`01-schule-DE-NI.md`](01-schule-DE-NI.md) | 211 | 0 | 92 | 100 % | drei KC-Generationen; jährlicher Runderlass listet die gültigen Pläne |
| [`01-schule-DE-NW.md`](01-schule-DE-NW.md) | 146 | 3 | 53 | 81 % | Pilot |
| [`01-schule-DE-RP.md`](01-schule-DE-RP.md) | 145 | 0 | 71 | 73 % | mehrere Pläne nur über Spiegelserver; Bio/Chem/Phys und Deutsch Sek I nicht lesbar |
| [`01-schule-DE-SH.md`](01-schule-DE-SH.md) | 155 | 0 | 68 | 84 % | Fachanforderungen; Generationen 2014–2019, 2024, 2026 nebeneinander |
| [`01-schule-DE-SL.md`](01-schule-DE-SL.md) | 135 | 1 | 57 | 77 % | saarland.de lieferte 403; nur Spiegel- und Archivkopien |
| [`01-schule-DE-SN.md`](01-schule-DE-SN.md) | 117 | 3 | 41 | 100 % | Pilot |
| [`01-schule-DE-ST.md`](01-schule-DE-ST.md) | 126 | 1 | 50 | 86 % | Grundsatzband plus Fachlehrpläne; Kompetenzschwerpunkt mehrdeutig |
| [`01-schule-DE-TH.md`](01-schule-DE-TH.md) | 100 | 0 | 38 | 89 % | Erprobungsfassungen 2026; Gymnasialpläne nicht lesbar |

**Welle 2 – Prüfergebnis Elementar:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`02-elementar-DE-BE.md`](02-elementar-DE-BE.md) | 110 | 0 | 63 | 94 % | neues Berliner Bildungsprogramm 2026 mit 7 statt 6 Bereichen |
| [`02-elementar-DE-BW.md`](02-elementar-DE-BW.md) | 117 | 1 | 72 | 100 % | neuer Orientierungsplan 2025, verbindlich ab 2029/30, bis dahin parallel |
| [`02-elementar-DE-BY.md`](02-elementar-DE-BY.md) | 99 | 0 | 46 | 100 % | 11. Auflage 2024 nur als Inhaltsverzeichnis lesbar; Binnenstruktur aus 2016 |
| [`02-elementar-DE-HB.md`](02-elementar-DE-HB.md) | 133 | 3 | 68 | 97 % | Bildungsplan 0–10 seit 2025/26 löst den Rahmenplan 2004 ab |
| [`02-elementar-DE-HH.md`](02-elementar-DE-HH.md) | 106 | 0 | 50 | 86 % | Hamburger Bildungsleitlinien 2024; Fassung 2012 nicht am Original gelesen |
| [`02-elementar-DE-MV.md`](02-elementar-DE-MV.md) | 126 | 0 | 56 | 100 % | Bildungskonzeption 0–10, Stand 01/2025; Vorgänger 2020/21 mit gleichem Titel |
| [`02-elementar-DE-NI.md`](02-elementar-DE-NI.md) | 118 | 0 | 66 | 100 % | Orientierungsplan 2005; Gesamtausgabe 2023 bündelt drei Teile (2005, 2011, 2012) |
| [`02-elementar-DE-RP.md`](02-elementar-DE-RP.md) | 103 | 0 | 52 | 100 % | Titel seit 2004 gleich; Ausgabe 2020 ff. nur teilweise online gelesen |
| [`02-elementar-DE-SH.md`](02-elementar-DE-SH.md) | 108 | 3 | 53 | 100 % | Neufassung 02/2026: 7 Themen und 4 Handlungsprinzipien statt 6 + 6; über Institutskopie |
| [`02-elementar-DE-SL.md`](02-elementar-DE-SL.md) | 89 | 0 | 46 | 100 % | Bildungsprogramm 2018; saarland.de 403, gelesen über Spiegel |
| [`02-elementar-DE-SN.md`](02-elementar-DE-SN.md) | 99 | 2 | 44 | 95 % | Sächsischer Erziehungs- und Bildungsplan gilt ab 2027-01-01, Teile A–C |
| [`02-elementar-DE-ST.md`](02-elementar-DE-ST.md) | 116 | 1 | 58 | 76 % | Fortschreibung 2025 nur als Inhaltsverzeichnis lesbar (Volltext über 10 MB) |
| [`02-elementar-DE-TH.md`](02-elementar-DE-TH.md) | 90 | 1 | 49 | 98 % | TBP-18 über Spiegel (Portal hinter Captcha); „Modi der Weltaneignung“ sind als `zeit` markiert, gemeint sind Entwicklungsstufen |

**Welle 3 – Prüfergebnis 06 B:**

| Datei | Zeilen T5 / T6 / T7 | verschoben | Beleg E in T5 / T6 | Hinweis |
|---|---|---|---|---|
| [`06B-abschluesse-niveaus-schularten.md`](06B-abschluesse-niveaus-schularten.md) | 40 / 81 / 23 | 0 | 72 % / 75 % | KMK-Vereinbarung Sek I (i. d. F. 07.10.2022) mit Anlagen 1–2 im Volltext; Landesnormen meist nicht lesbar |

- T5 hat keine Spalte `ziel_id`. Der Lauf hat die Ziel-IDs darum in eckigen Klammern an das Feld `system` gehängt. Alle 21 IDs gibt es im Modell, der Prüfer sieht sie aber nicht. Für künftige Läufe braucht T5 eine Spalte `ziel_id`.
- Die KIM-Zuordnung widerspricht teils dem Profil. Mittelschule BY: Profil s03, Lauf s07. Integrierte Sekundarschule BE: Profil s05, Lauf s10. Regionale Schule, Realschule plus und Regelschule: Profil s10, Lauf s07. Am 2026-10-21 gegen die KIM-Liste geprüft: Das Profil stimmt (KIM führt „Mittelschule“ und „Mittelstufenschule“ als andere Namen der Hauptschule s03). Die Zuordnungen des Laufs waren als Annahme markiert und werden nicht übernommen.
- MV, RP, SL und SH haben keinen erweiterten ersten Abschluss. `lvl:school-EESA` gilt dort nicht.
- Die Kursniveaus der Sek I heißen je Land anders: GR/ER (BE, umbenannt aus G/E), G/E (HB), G/E/Z (NI), Grund-/Erweiterungskurs (NW), A/B/C und E/G (HE). Für den niedersächsischen Z-Kurs fehlt ein Ziel im Modell.
- Die eingesehene APO-S I NRW (Fassung 2012/2014) sagt noch „Hauptschulabschluss“. Die KMK-Anlage von 2022 führt NRW mit ESA/EESA/MSA.

**Welle 3 – Prüfergebnis 05 B:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`05B-eb-rahmendokumente.md`](05B-eb-rahmendokumente.md) | 256 | 0 | 71 | 99 % | 13 Rahmendokumente im Original-PDF gelesen (BAMF, DVV, telc, GRETA, DigComp 3.0) |

- Bei `eb:r11` (Aktivitäten) sind die Werte die Fertigkeiten des GER 2001, nicht die Aktivitäten des Begleitbands 2020. Die Abbildung auf `eb:CEFRActivities` muss beide Fassungen kennen.
- Die DVV-Rahmencurricula nutzen Alpha-Level 1–4, das lea.-Original beschreibt Alpha-Level 1–6. Das Modell kennt 4 Stufen.
- DigComp 3.0 hat 4 Niveaus und deckt sich mit `lvl:DigComp3`. Eine deutsche Fassung hat der Lauf nicht gefunden.
- Das Konzept für gering Literalisierte (Stand 03/2025) und der Berufssprachkurs Basiskurs B2 (Stand 10/2026) sind neu.
- Nicht gefunden: Lernfeld (`eb:r10`), Kompetenzgruppe (`eb:r07`), Prüfung zum anerkannten Fortbildungsabschluss (`eb:c-fortbildung`).

**Welle 3 – Prüfergebnis 04 A:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`04A-hochschule-laender.md`](04A-hochschule-laender.md) | 131 | 0 | 55 | 58 % | Landesverordnungen nach MRVO 2024 nur für BY und TH im Verordnungsblatt gelesen, sonst über die Vergleichsdokumente des Akkreditierungsrats (S); juris-Portale nicht lesbar |

- Die MRVO 2024 ist in allen 16 Ländern umgesetzt, überwiegend ab 01.08.2025 (BB 01.09.2025).
- § 7 Abs. 2 nennt jetzt acht Pflichtangaben. Nr. 1 heißt „angestrebte Lernergebnisse und Studieninhalte“ statt „Inhalte und Qualifikationsziele“. Die Pflichtangabe „Verwendbarkeit des Moduls“ ist gestrichen; die Beschreibung bei `hs:mrvo-2024` („Verwendbarkeit optional“) ist zu ungenau. Nur Bremen behält sie für Lehramtsmodule.
- Neu in § 12 (in BY und TH gelesen): Module sollen mindestens 5 Leistungspunkte umfassen; „dual“ nur bei systematischer Verzahnung der Lernorte.
- Anrechnung außerhochschulisch erworbener Kompetenzen: fast überall bis zur Hälfte. Im Gesetzestext gelesen für BY, BE, BB, SN.
- Ordnungsnamen: APSO und FPSO (TU München), StuPrO mit Modulplänen als Anlage 2 (DHBW), SPO und ABV (FU Berlin). Sachsen verlangt Modulbeschreibungen „als Anlage“ der Studienordnung (§ 37 Abs. 3 SächsHSG).
- Nicht gefunden, aber nicht widerlegt: BE-StuPO, BW-SPO, BY-Eignungsfeststellungsordnung.

**Welle 3 – Prüfergebnis 05 A:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`05A-eb-laender.md`](05A-eb-laender.md) | 131 | 0 | 62 | 69 % | alle 16 Länder; Gesetzestexte am Original nur für BY, BB, HE, NW, RP, SN |

- Die Länderhinweise der Vorliste sind veraltet.
  - RP: Seit 01.03.2026 gilt das Landesbildungszeitgesetz mit „Bildungszeit“. Das Bildungsfreistellungsgesetz von 1993 ist außer Kraft.
  - BB: Das Erwachsenenbildungsgesetz vom 20.12.2023 sagt „Bildungszeit“. „Bildungsfreistellung“ steht nur noch im Titel der Verordnung von 2005.
  - NI: Das Bildungszeitgesetz löst zum 01.01.2027 das Bildungsurlaubsgesetz ab. Belegt ist das nur über einen Auszug (S).
  - SN: Der Landtag hat das Qualifizierungszeitgesetz beschlossen, mit 3 Arbeitstagen „Qualifizierungszeit“ ab 2027. Gelesen ist nur die Beschlussempfehlung, die Verkündung nicht.
- Im Saarland heißen Veranstaltungen „freistellungsfähig festgestellt“, nicht „anerkannt“. In NRW heißt das Gesetz „Arbeitnehmerweiterbildungsgesetz“, die Kurstexte sagen „Bildungsurlaub“.
- Keine Landesnorm schreibt eine einheitliche Anerkennungsformel für Kursausschreibungen vor. Belegt sind Bescheidformeln (BE, HH, BB) und Trägerhinweise (NW, HE, TH, SH).
- Die sechs Programmbereiche `eb:pa-*` der VHS-Statistik stehen in keinem Landesgesetz wörtlich. Eigene Sachgebietslisten haben nur RP (12) und NRW (7).
- Berlin und Hamburg haben kein Weiterbildungsgesetz.

**Welle 3 – Prüfergebnis 04 B:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`04B-hochschule-modulhandbuecher.md`](04B-hochschule-modulhandbuecher.md) | 173 | 0 | 151 | 99 % | 12 Modulhandbücher aus 7 Ländern: 4 Universitäten, 4 HAW, DHBW, PH, Musikhochschule, weiterbildender MBA |

- Das Feld für Lernergebnisse hat mindestens 10 Namen, auch innerhalb eines Landes.
- Die DHBW gliedert es in vier Unterfelder: Fachkompetenz, Methodenkompetenz, personale und soziale Kompetenz, übergreifende Handlungskompetenz. Das ist eine Kompetenzdimension je Aussage, ohne Niveau. Das Modell kennt diese Vierteilung nicht: `kd:FourComponents` trennt Sozial- und Selbstkompetenz, und eine übergreifende Handlungskompetenz fehlt.
- Die THWS reiht die Bloom-Verben in Lernergebnissen der Reihe nach auf.
- Homonyme: „Unit“ (Frankfurt, DHBW) ist eine Lehrveranstaltung unter dem Modul. „Niveaustufe“ (BHT) ist die Semesterlage, kein DQR-Niveau. „Leistungsnachweis“ ist die Prüfung selbst, „Prüfungsnummer“ (THWS) die Modulnummer. „Stand“ ist das Fassungsdatum und kein Zeichen fehlender Verbindlichkeit.
- Eine Anlage-Formel zur Prüfungsordnung belegen nur PH Freiburg und Trossingen. Bei der HfMT Köln ist das Modulhandbuch über die Amtliche Bekanntmachung mittelbar verbindlich.

**Welle 4 – Prüfergebnis 07 (Noten- und Verhaltensskalen):**

| Datei | Zeilen gesamt | verschoben | Zeilen T2 | Beleg E in T2 | Hinweis |
|---|---|---|---|---|---|
| [`07A-bewertungsskalen.md`](07A-bewertungsskalen.md) | 50 | 0 | 19 | 68 % | BW, BY, BE, BB; bravors.brandenburg.de lieferte 503, BB daher nur S |
| [`07B-bewertungsskalen.md`](07B-bewertungsskalen.md) | 54 | 0 | 19 | 53 % | HB, HH, HE, MV; Normen von HH und MV nicht im Volltext |
| [`07C-bewertungsskalen.md`](07C-bewertungsskalen.md) | 56 | 0 | 19 | 42 % | NI, NW, RP, SL; NI und SL nur über Textspiegel |
| [`07D-bewertungsskalen.md`](07D-bewertungsskalen.md) | 69 | 0 | 23 | 70 % | SN, ST, SH, TH; ST nur über eine Präsentation des Landesschulamts; T8 Modi 5 Zeilen, 100 % E |

- **Notenstufen:** Alle 16 Länder nutzen die sechs Notenstufen. Tendenzen sind uneinheitlich: Zulässig sind sie in SN und MV, in BW nur in der Halbjahresinformation, in HE und BE nur außerhalb des Zeugnisses. Unzulässig sind sie in HB, NI, RP, SL, SH und TH.
- **Notenpunkte:** 15–0 mit derselben Zuordnung zu den Notenstufen, wo der Text gelesen wurde (BY, BB, HB, HE, NI, NW, RP, SL, SH). Das passt zu `lvl:GradePoints`. HE erlaubt Punkte gesetzlich für alle Schulformen. SH hat zusätzlich eine Übertragungsskala 1–8 für die Anforderungsebenen.
- **Arbeits- und Sozialverhalten**, je Land eine eigene Skala:

| Land | Bereiche | Stufen | Beleg |
|---|---|---|---|
| BW | Verhalten, Mitarbeit | 4: sehr gut, gut, befriedigend, unbefriedigend | E |
| BY | keine Kopfnoten; Grundschule: Sozialverhalten, Lern- und Arbeitsverhalten als Text | – | E |
| BE | 5 Merkmale, nur nach Beschluss der Schulkonferenz | offen | E/A |
| BB | Arbeitsverhalten (4 Merkmale), Sozialverhalten (3) | 4: hervorragend … wenig ausgeprägt (Ankreuzraster) | S |
| HB | Information als Text | – | E |
| HH | keine Kopfnoten; Raster überfachlicher Kompetenzen | Grundschule 5, Stadtteilschule 4 (nur Muster) | S |
| HE | Arbeits- und Sozialverhalten | Note oder Punkte; Kriterien je Schule | E |
| MV | Arbeitsverhalten (Fleiß, Zuverlässigkeit), Sozialverhalten (Umgangsformen, Teamfähigkeit) | 6 Notenwörter | S |
| NI | Arbeitsverhalten, Sozialverhalten (je 6 Merkmale) | 5: verdient besondere Anerkennung … entspricht nicht den Erwartungen | S |
| NW | nur Aussagen als Text (Kopfnoten 2008 nicht mehr gültig) | – | E |
| RP | Mitarbeit und Verhalten | 4: sehr gut, gut, befriedigend, unbefriedigend | E |
| SL | Verhalten, Mitarbeit; Grundschule und Förderschule: Sozialverhalten, Lern- und Arbeitsverhalten | 5: sehr gut … nicht immer befriedigend, unbefriedigend | S |
| SN | Betragen, Fleiß, Mitarbeit, Ordnung | 5: Noten 1–5 | E |
| ST | Sozialverhalten, Lernverhalten | 5: Noten 1–5 | S |
| SH | Lernverhalten und Sozialverhalten als Text | – | E |
| TH | Mitarbeit, Verhalten (seit 01.08.2025, Klassen 3–8) | 4: sehr gut, gut, befriedigend, nicht befriedigend | E |

- **Thüringer Modi der Weltaneignung** (TBP-18, S. 16, öffentlich zugängliche Kopie der Ausgabe 2015): fünf Modi von „basal“ bis „autonom-expansiv“. Der Plan schreibt ihnen den Charakter einer sequentiellen Abfolge zu, bindet sie aber ausdrücklich nicht an Alter oder Einrichtung. Ein Kind kann in verschiedenen Bereichen in verschiedenen Modi sein. Das erfüllt die Bedingung für eine Skala der Art `development`. Lauf 02 TH hatte sie fälschlich als `zeit` markiert.
- **Hinweise für den Import:**
  - Die Verhaltensstufen „sehr gut … unbefriedigend“ sind nicht die Notenstufen. Jede Landesskala wird ein eigenes `cur:LevelScheme` der Art `conduct`.
  - Das Bremer 10-stufige Raster im Lernentwicklungsbericht hat der Lauf als `entwicklung` markiert. Es ist ein fachliches Kompetenzraster und gehört zu `proficiency`.

**Welle 1 – Prüfergebnis:**

| Datei | Zeilen gesamt | verschoben | Zeilen T3 | Beleg E in T3 | Hinweis |
|---|---|---|---|---|---|
| [`03B-beruf-DE-NW.md`](03B-beruf-DE-NW.md) | 84 | 4 | 43 | 100 % | T6 zweimal ausgegeben; der erste Block hat einen falschen Kopf, der zweite gilt |
| [`03B-beruf-DE-BY.md`](03B-beruf-DE-BY.md) | 109 | 0 | 46 | 100 % | Wirtschaftsschule nur über Suchtreffer (S) |
| [`03B-beruf-DE-BW.md`](03B-beruf-DE-BW.md) | 119 | 1 | 47 | 98 % | Kriterium a (Bündelung) nicht bestätigt |
| [`03B-beruf-DE-SN.md`](03B-beruf-DE-SN.md) | 103 | 1 | 40 | 100 % | Wingdings-Verweise auch in den Fachlehrplänen der beruflichen Schulen |
| [`03B-beruf-DE-RP.md`](03B-beruf-DE-RP.md) | 128 | 0 | 44 | 100 % | KMK-RLP gelten unmittelbar; eigene Struktur bei Lernbausteinen, Fachschul-Lernmodulen, Pflegeschule |
| [`03B-beruf-DE-NI.md`](03B-beruf-DE-NI.md) | 94 | 3 | 33 | 97 % | Server von nibis teils nicht erreichbar; mehrere Rahmenrichtlinien nur als Landtagsanlage |
| [`02-elementar-DE-HE.md`](02-elementar-DE-HE.md) | 159 | 0 | 94 | 100 % | BEP 0–10, Auflagen 2019 und 2025 textgleich |
| [`02-elementar-DE-NW.md`](02-elementar-DE-NW.md) | 94 | 2 | 40 | 95 % | Neufassung 2026 angekündigt, Entwurf nicht öffentlich |

## Ins Modell übernommen (2026-10-21)

Aus den Läufen der Welle 3 in Profile und Vokabulare eingearbeitet; die übrigen Zeilen warten auf den Import:

| Befund | Änderung |
|---|---|
| 06 B: Z-Kurs (NI), GR/ER (BE) | `lvl:course-Z`; GR-/ER-Niveau als altLabel an `lvl:course-G`/`lvl:course-E`; Hinweis auf landesabhängige Kursbuchstaben |
| 06 B: kein erweiterter erster Abschluss in MV, RP, SL, SH | Hinweis an `lvl:SchoolLeaving` |
| DQR-Zuordnung der Schulabschlüsse (Eurydice) | closeMatch ESA → DQR 2, MSA → DQR 3, FHR und AHR → DQR 4 |
| 05 B: lea. beschreibt Alpha-Level 1–6 | `lvl:alpha-5`, `lvl:alpha-6` |
| 05 A: Bildungszeit, Qualifizierungszeit, „freistellungsfähig“ | `eb:r24-bw` um RP, BB, NI erweitert; RP und BB aus `eb:r24-rp`; neu `eb:r24-sn`, `eb:r24-sl` |
| 04 A: MRVO 2024 | `hs:mrvo-2024` mit den acht Pflichtangaben, gestrichener Verwendbarkeit und 5-LP-Regel; Feldname an `hs:Modulziel` und `hs:Inhalt` |
| 04 B: DHBW-Vierteilung | Kompetenzmodell `kd:DHBW` mit vier Dimensionen |
