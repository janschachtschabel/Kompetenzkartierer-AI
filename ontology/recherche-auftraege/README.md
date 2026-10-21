# Rechercheaufträge: Länder-Steckbriefe für das Lexikon

**Zweck:** Die Länderbegriffe im Lexikon sind lückenhaft. Die FWU-Daten sind nur für einen Teil der Länder belastbar, die Bereichsrecherchen haben je Land meist nur einzelne Begriffe erfasst. Die Aufträge erheben je Land und Bildungsbereich einen Steckbrief, der ohne Umwege in Lexikonhinweise übersetzt werden kann (Konzept, Abschnitt 12.4):

- welche Dokumente es gibt;
- wie sie gegliedert sind;
- welche Begriffe, Kürzel und Layoutsignale sie verwenden;
- welche Querschnittslegenden und Niveausysteme gelten.

## Läufe

| Auftrag | Zuschnitt | Läufe | Anhänge (aus `vorlisten/`) |
|---|---|---|---|
| [`01-schule-land.md`](01-schule-land.md) | allgemeinbildende Schule, **ein Land je Lauf** | 16 | `schule-ziele.csv`, `schule-DE-XX.csv`, `schule-DE.csv`, `schule-ohne-land.csv` |
| [`02-elementar.md`](02-elementar.md) | Kita/Kindertagespflege/Hort, **ein Land je Lauf** | 16 | `elementar-ziele.csv`, `elementar-DE-XX.csv`, `elementar-DE.csv`, `elementar-ohne-land.csv` |
| [`03-beruf-land.md`](03-beruf-land.md) A | berufliche Schulen, **Überblick über alle 16 Länder**: Übernahme der KMK-RLP, eigene Lehrplanbestände, Empfehlung Detaillauf | 1 | `beruf-ziele.csv`, `beruf-ohne-land.csv` |
| [`03-beruf-land.md`](03-beruf-land.md) B | berufliche Schulen, **Detail je Land** – nur Länder mit Empfehlung aus A | erwartet 5–8 | wie A + `beruf-DE-XX.csv` (falls vorhanden) + Zeilen des Landes aus A |
| [`04-hochschule.md`](04-hochschule.md) | Landesrecht und Ordnungsbezeichnungen, alle Länder; optional Stichprobe von Modulhandbüchern | 1 (+1) | `hochschule-ziele.csv`, `hochschule-DE-*.csv` |
| [`05-erwachsenenbildung.md`](05-erwachsenenbildung.md) | Landesrecht EB + bundesweite Rahmendokumente | 1–2 | `erwachsenenbildung-ziele.csv`, `erwachsenenbildung-ohne-land.csv` |
| [`06-querschnitt-niveau.md`](06-querschnitt-niveau.md) | Querschnittsrahmen, Abschlüsse, Kursniveaus, Schularten – alle Länder | 1–2 | `schule-ziele.csv` |
| [`07-bewertungsskalen.md`](07-bewertungsskalen.md) | Notenstufen, Notenpunkte, Kopfnoten bzw. Arbeits- und Sozialverhalten, Zeugnisraster; TH „Modi der Weltaneignung“ | 4 (je vier Länder) | `schule-ziele.csv` |

**Insgesamt etwa 45–50 Läufe** (mit den vier Läufen von 07). Davon sind 32 Länderläufe für Schule und Elementar und bis zu 9 für Beruf. Ein Land je Lauf ist die Regel, wo jedes Land einen eigenen, umfangreichen Dokumentbestand hat: Die Recherchetiefe soll nicht auf mehrere Länder verteilt werden, und die Begriffe sollen am Primärdokument belegt sein. Sammelläufe gibt es nur, wo sich die Länder vor allem rechtlich unterscheiden (Hochschule, Erwachsenenbildung) oder wo ein Überblick über die Tiefe entscheidet (Beruf A).

**Reihenfolge:**

1. **Pilotläufe**, um Format und Tiefe zu prüfen, bevor die übrigen starten:
   - zwei Läufe von Auftrag 01, z. B. NW und SN (unterschiedliches Gliederungsprinzip, schon Vorlisten);
   - ein Lauf von 02, z. B. BB (neue Fassung 2024);
   - der Überblickslauf 03 A.
2. Dann die übrigen Läufe von 01 und 02, parallel dazu 06 und die Detailläufe 03 B für die Länder mit Empfehlung „ja“.
3. Zuletzt 04 und 05; dort sind die Länderunterschiede kleiner.
4. 07 (Noten- und Verhaltensskalen) unabhängig von den übrigen, in vier Läufen zu je vier Ländern.

**Wenn das Budget nicht reicht:** zuerst bei 04 B (Modulhandbuch-Stichprobe) und 05 A (Landesrecht EB) kürzen. Danach 03 B auf die Länder mit Kriterium a und b beschränken. Die Länderläufe 01 und 02 nicht zusammenlegen.

**Vorlisten neu erzeugen** (nach Lexikonänderungen), aus `ergebnis/`:

```bash
python -I werkzeuge/exportiere_vorlisten.py .
```

Die Vorlisten enthalten alle heutigen Hinweise mit Land, Rolle, Ziel, Stärke und Prüfstand, auch die aus den FWU-Klassen erzeugten (`hinweis_id` beginnt mit `schul:fwu-`). Die Recherche soll jeden Eintrag bestätigen, korrigieren oder als „nicht gefunden“ markieren.

Die Ziellisten (`<bereich>-ziele.csv`) nennen alle IDs, die in `ziel_id` stehen dürfen:

- Knotentypen, Aussage-Unterarten und Dokumenttypen des Profils;
- die Konzepte seiner Schemata (Bildungsbereiche, Prinzipien, Bildungsorte, Schularten …);
- die gemeinsamen Vokabulare `ctx:`, `qz:`, `lvl:` und `kd:`.

Ohne diese Konzepte hat der Pilot BB IDs erfunden. Ergebnisse und Pilotauswertung: [`../recherche-ergebnisse/`](../recherche-ergebnisse/README.md).

## Gemeinsames Ausgabeformat

Alle Aufträge liefern dieselben Tabellen als CSV-Blöcke (Semikolon, eine Tabelle je Codeblock, Spaltennamen exakt wie vorgegeben). Daraus entsteht ohne Nacharbeit je Begriff ein Hinweis mit Rolle, Geltung, Beispiel und Fundstelle:

| Tabelle | Inhalt | wird zu |
|---|---|---|
| T1 Dokumente | Dokumentlandschaft mit Fassungen und Gültigkeit | `cur:Document`/`cur:Work`-Vorlagen, Dokumenttyp-Hinweise |
| T2 Gliederung | Ebenenfolge je Dokumentart mit Nummerierung, Zeit-, Niveau- und Tabellenlayout | Formmuster (`pattern`) mit Testbeispielen, `typicalParent` |
| T3 Begriffe | jeder Begriff mit Funktion, Ziel, Rolle, Merkmal, Beispiel, Fundstelle, Abgleich mit der Vorliste | `cur:LexicalCue` |
| T4 Querschnitt | Kürzel/Symbole und ihre Bedeutung | Marker-Hinweise → `qz:` |
| T5 Niveau | Stufensysteme und ihre Darstellung | Niveau-Hinweise → `lvl:` |
| T6 Einrichtungen | Schularten, Bildungsorte, Bildungsgänge | Profilwerte mit KIM-Abbildung |
| T7 Lücken | Nicht Gefundenes und Widersprüche | offene Fragen |

Die genauen Spalten stehen in jedem Auftrag, damit er für sich kopierbar ist.

## Übernahme

Ein Importer (`werkzeuge/importiere_recherche.py`, noch zu schreiben) liest T3–T5 und erzeugt Länderdateien `profile/laender/<bereich>-DE-XX.ttl`. Dabei gilt:

- Hinweise aus der Recherche bekommen höchstens Stärke 0,7 und „nicht geprüft“;
- Belegstatus E (am Primärdokument mit Seite) wird als Fundstelle mitgeführt;
- Einträge, die eine Vorliste-Zeile korrigieren, ersetzen diese erst nach Redaktionsentscheid.

Danach folgen `pruefe.py` (Muster gegen Beispiele, Kollisionsbericht) und ein Pilot an Originaldokumenten (Konzept 12.4).
