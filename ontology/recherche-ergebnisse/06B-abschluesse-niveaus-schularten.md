<!-- 06 B Abschluesse/Niveaus/Schularten, sonnet medium, 2026-10-20; Ziel-IDs in eckigen Klammern im Feld system (Schema ohne ziel_id) -->

**Besonderheiten (Übersicht)**

- Gesamtlage: Die KMK-Vereinbarung über die Schularten und Bildungsgänge im Sekundarbereich I (Beschluss 03.12.1993 i.d.F. 07.10.2022) liegt im Volltext vor. Ich habe sie per Textextraktion selbst gelesen. Anlage 1 (Schularten je Land, S. 17-23) und Anlage 2 (Abschlussbezeichnungen je Land, S. 24-25) tragen die Zeilen mit beleg E. Die Spaltenzuordnung A1/A2/A3/B/C in Anlage 1 habe ich aus dem Textlayout abgeleitet. Bei Niedersachsen und NRW ist die Extraktion von Anlage 2 verstümmelt. Dort habe ich mit dem Niedersächsischen RdErl. und der Bremer Übersicht gegengeprüft.
- Landesnormen: Die Landesrechtsportale lieferten per WebFetch keinen Volltext, weil sie per Script gerendert werden. Paragrafen nenne ich deshalb nur, wo ich den Text gesehen habe:
  - NRW: APO-S I Fassung 2012/2014, §§ 14, 19, 40-42.
  - BE: Änderungsverordnung zur SekIVO, §§ 27, 32, 44, 48.
  - BY: Art. 7a BayEUG, nur über Suchzusammenfassung (S).
  - Alle übrigen Landesnormen sind nicht eingesehen.
- Zweistufig statt dreistufig: Mehrere Länder haben keinen erweiterten ersten Abschluss: MV, RP, SL und SH. Im Land Bremen kann der erste Abschluss erst nach zehn Schuljahren eingelöst werden (KMK Fn. 10, S. 11).
- Abschlussbezeichnungen: Es gibt vier Familien.
  - Hauptschul-Familie: BW, HE, NI, SL, SN, ST, TH. Die erweiterten Formen heißen Werkrealschulabschluss, Qualifizierender Hauptschulabschluss, Qualifizierter Hauptschulabschluss oder Sekundarabschluss I - Hauptschulabschluss.
  - Berufsbildungsreife-Familie: BE, BB, HB. In Bremen heißt sie „Einfache Berufsbildungsreife“.
  - Berufsreife: MV und RP.
  - Neutrale Bezeichnungen: HH, NW und SH. In NW und SH heißt der erste Abschluss „Erster Schulabschluss“. SH nennt ihn in den Fachanforderungen „Erster allgemeinbildender Schulabschluss“. Die NRW-APO-S I in der eingesehenen Fassung 2012/2014 sagt noch „Hauptschulabschluss“, die KMK-Anlage 2 (2022) führt NRW mit ESA/EESA/MSA.
- Mittlerer Abschluss: Hier gibt es mehr Varianten. Beispiele sind „Fachoberschulreife“ (BB), „Mittlere Reife“ (MV), „Qualifizierter Sekundarabschluss I“ (RP), „Mittlerer Bildungsabschluss“ (SL) und in Bayern zwei Namen (Realschulabschluss und Mittlerer Schulabschluss an der Mittelschule).
- Kursniveaus Sek I lassen sich nicht vereinheitlichen. Die Namen unterscheiden sich stark:
  - BE: GR-/ER-Niveau und GR-/ER-Kurs. Das ist aus E-/G-Niveau umbenannt, die Anpassung an den neuen Rahmenlehrplan nennt die Änderungsverordnung.
  - HB: G-Niveau und E-Niveau.
  - NI: G-, E- und Z-Kurs.
  - NW: Grundkurse und Erweiterungskurse.
  - HE: A-/B-/C-Kurse und E-/G-Kurse (ältere Handreichung).
  - BW: G/M/E.
  - HH: Mindestanforderungen.
  - SH: drei Anforderungsebenen (ESA, MSA, Übergang in die Oberstufe).
- Oberstufe: Die KMK führt bundesweit „grundlegendes“ und „erhöhtes Anforderungsniveau“. In Bayern gilt das so (eA). Sachsen nutzt Leistungs- und Grundkurse, Sachsen-Anhalt „kein Grund- und Leistungskurs“. Thüringen soll „Fächer mit erhöhtem bzw. grundlegendem Anforderungsniveau“ führen (S).
- Zielliste: Das Schema hat keine Spalte für IDs. Ich habe passende IDs in eckigen Klammern an das Feld `system` angehängt. „neu“ steht, wo kein Eintrag der Zielliste passt. Die Zuordnung zu KIM-Schularten bei Landesbezeichnungen ist Annahme (beleg A), außer bei Namensgleichheit.

**T5 Niveau**

```csv
land;system;stufen_in_reihenfolge_woertlich;bezug;schularten_stufen;darstellung_in_lehrplaenen;rechtsgrundlage;fundstelle;beleg
BW;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Hauptschulabschluss | Werkrealschulabschluss | Realschulabschluss;abschluss;Sek I Kl. 9 und 10;nicht erhoben;KMK-Vereinbarung Schularten und Bildungsgänge Sek I (Beschluss 03.12.1993 i.d.F. 07.10.2022) Ziff. 5.1-5.2 | Schulgesetz BW nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 24;E
BY;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Erfolgreicher Abschluss der Mittelschule | Qualifizierender Abschluss der Mittelschule | Realschulabschluss | Mittlerer Schulabschluss an der Mittelschule;abschluss;Mittelschule Kl. 9 (erfolgreich und qualifizierend) | Mittlere-Reife-Klasse Kl. 10 | Realschule;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Art. 7a BayEUG (Mittlere-Reife-Zug Jgst. 7-10 und qualifizierender Abschluss in Abs. 4 laut Suchzusammenfassung);KMK-Vereinbarung Sek I Anlage 2 S. 24 | gesetze-bayern.de BayEUG Art. 7a;E
BE;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Berufsbildungsreife (BBR) | Erweiterte Berufsbildungsreife (EBBR) | Mittlerer Schulabschluss (MSA);abschluss;Integrierte Sekundarschule | Gemeinschaftsschule | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Sekundarstufe I-Verordnung nicht im Volltext eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 24 (Anmerkung für BBR: keine Abschlussprüfungen aber zentrale vergleichende Arbeiten);E
BB;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Berufsbildungsreife (BBR) | Erweiterte Berufsbildungsreife (EBR) | Fachoberschulreife (FOR);abschluss;Oberschule Jgst. 7-10 | Gesamtschule;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Sekundarstufe I-Verordnung nicht im Volltext eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 24;E
HB;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Einfache Berufsbildungsreife (EinfBBR) | Erweiterte Berufsbildungsreife (ErwBBR) | Mittlerer Schulabschluss (MSA);abschluss;Oberschule Kl. 10 | Gymnasium;Bildungsplan Deutsch Oberschule 5-10 (Stand 08/2026) nennt am Ende Jgst. 10 „Erweiterte Berufsbildungsreife“ | „Mittlerer Schulabschluss“ | „Zugang zur Gymnasialen Oberstufe (Abitur nach 9 Jahren)“;KMK-Vereinbarung Sek I Ziff. 5.1.1 Fn. 10 | Bremer Schulgesetz und Oberschulverordnung nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 24 | Bildungsplan Deutsch Oberschule S. 5;E
HH;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Erster allgemeinbildender Schulabschluss (ESA) | Erweiterter erster allgemeinbildender Schulabschluss (eESA) | Mittlerer Schulabschluss;abschluss;Stadtteilschule | Gymnasium;Bildungsplan Stadtteilschule Chemie 7-11 nennt „ersten allgemeinbildenden Schulabschluss und den mittleren Schulabschluss“ sowie Übergang über die Vorstufe (Jgst. 11) in die Studienstufe;KMK-Vereinbarung Sek I Ziff. 5 | Hamburgisches Schulgesetz nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 24 | Bildungsplan Stadtteilschule Chemie S. 4;E
HE;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Hauptschulabschluss | Qualifizierender Hauptschulabschluss | Realschulabschluss;abschluss;Hauptschulbildungsgang | Realschulbildungsgang | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Hessisches Schulgesetz nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 25;E
MV;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-MSA];Berufsreife | Mittlere Reife;abschluss;Regionale Schule | Gesamtschulen | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Schulgesetz MV nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 25 (kein erweiterter erster Abschluss ausgewiesen);E
NI;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Hauptschulabschluss | Sekundarabschluss I - Hauptschulabschluss | Sekundarabschluss I - Realschulabschluss | Erweiterter Sekundarabschluss I;abschluss;Oberschule Kl. 9 (Hauptschulabschluss) und Kl. 10 | Gymnasium Einführungsphase Jgst. 10;Erlass nennt „Erweiterter Sekundarabschluss I“ berechtigt zum Besuch der Einführungsphase der gymnasialen Oberstufe;KMK-Vereinbarung Sek I Ziff. 5 | RdErl. d. MK „Die Arbeit in der Oberschule“ vom 07.07.2011 (gültig ab 01.08.2015) | NI-Eltern-Info „Die Arbeit in der Oberschule“ 2011;KMK-Vereinbarung Sek I Anlage 2 S. 25 (Extraktion verstümmelt) | Eltern-Info S. 5 (Abschlüsse Ende Jg. 10 und Jg. 9);E
NW;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Erster Schulabschluss | Erweiterter Erster Schulabschluss | Mittlerer Schulabschluss (Fachoberschulreife) | ESA | EESA | MSA;abschluss;Hauptschule | Realschule | Gesamtschule | Sekundarschule | Gymnasium;APO-S I in der eingesehenen Fassung 2012/2014 führt „Hauptschulabschluss“ „Hauptschulabschluss nach Klasse 10“ und „Mittlerer Schulabschluss (Fachoberschulreife)“;APO-S I §§ 40-42 (Fassung vom 02.11.2012 geändert 26.03.2014) | Umbenennung zu ESA/EESA siehe KMK Anlage 2;KMK-Vereinbarung Sek I Anlage 2 S. 25 | APO-S I Inhaltsverzeichnis Abschnitt 6 §§ 40-42;E
RP;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-MSA];Berufsreife | Qualifizierter Sekundarabschluss I;abschluss;Realschule plus Kl. 9 (Berufsreife) und Kl. 10 | Integrierte Gesamtschule | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Schulgesetz RP § 10 Abs. 3 laut Suchzusammenfassung;KMK-Vereinbarung Sek I Anlage 2 S. 25 (kein erweiterter erster Abschluss ausgewiesen);E
SL;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-MSA];Hauptschulabschluss | Mittlerer Bildungsabschluss;abschluss;Gemeinschaftsschule | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Landesnorm nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 25;E
SN;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Hauptschulabschluss | Qualifizierender Hauptschulabschluss | Realschulabschluss;abschluss;Oberschule | Gemeinschaftsschule | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Sächsisches Schulgesetz nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 25;E
ST;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Hauptschulabschluss | Qualifizierter Hauptschulabschluss | Realschulabschluss;abschluss;Sekundarschule | Gemeinschaftsschule | Gesamtschulen | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Schulgesetz LSA nicht eingesehen;KMK-Vereinbarung Sek I Anlage 2 S. 25;E
SH;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-MSA | lvl:school-transition];Erster allgemeinbildender Schulabschluss (ESA) | Mittlerer Schulabschluss (MSA) | Übergang in die Oberstufe;abschluss;Gemeinschaftsschule | Gymnasium;Fachanforderungen Mathematik: „Sie können am Ende der neunten Jahrgangsstufe den Ersten allgemeinbildenden Schulabschluss am Ende der zehnten Jahrgangsstufe den Mittleren Schulabschluss oder die Versetzung in die Sekundarstufe II erlangen“;KMK-Vereinbarung Sek I Ziff. 5 | Fachanforderungen Mathematik Sek I/II SH Kap. 1;KMK-Vereinbarung Sek I Anlage 2 S. 25 | Fachanforderungen Mathematik Einleitung;E
TH;Schulabschlüsse Sek I [lvl:school-ESA | lvl:school-EESA | lvl:school-MSA];Hauptschulabschluss (HSA) | Qualifizierender Hauptschulabschluss (QHSA) | Realschulabschluss (RSA);abschluss;Regelschule | Gemeinschaftsschule | Gesamtschulen | Gymnasium;nicht erhoben;KMK-Vereinbarung Sek I Ziff. 5 | Thüringer Schulordnung (ThürSchulO) nur über Suchzusammenfassung;KMK-Vereinbarung Sek I Anlage 2 S. 25;E
alle;Sekundarabschlüsse und Oberstufenreife [lvl:school-AHR | lvl:school-FHR];Fachhochschulreife (schulischer Teil) | Allgemeine Hochschulreife (Abitur);abschluss;gymnasiale Oberstufe Einführungsphase (1 Jahr) + Qualifikationsphase (2 Jahre);nicht erhoben;Vereinbarung zur Gestaltung der gymnasialen Oberstufe und der Abiturprüfung (Beschluss 07.07.1972 i.d.F. 16.03.2023) Ziff. 1 und Ziff. 12;KMK Oberstufenvereinbarung 2023 Ziff. 1 S. 5 | Ziff. 12 S. 22;E
alle;Anspruchsebenen der Leistungsdifferenzierung Sek I [lvl:course-G | lvl:course-E];obere | mittlere | untere Anspruchsebene (zwei oder drei definierte Anspruchsebenen);kursniveau;Schularten der Kategorien B und C (mindestens in Deutsch Mathematik erster Fremdsprache und einem naturwissenschaftlichen Fach ab Jgst. 7 bzw. 9);Differenzierung in eigens eingerichteten Kursen oder in der klasseninternen Lerngruppe (Fn. 4);KMK-Vereinbarung Sek I Ziff. 3.2.5-3.2.7 und 5.2.3;KMK-Vereinbarung Sek I S. 6-7 und S. 12;E
alle;Anforderungsniveaus gymnasiale Oberstufe [lvl:course-basic | lvl:course-advanced];grundlegendes Anforderungsniveau | erhöhtes Anforderungsniveau;kursniveau;Qualifikationsphase: zwei oder drei Fächer auf erhöhtem Anforderungsniveau (fünfstündig bzw. vierstündig bei drei);in Länderlehrplänen Bezeichnung Landesrecht (siehe Länderzeilen);Oberstufenvereinbarung Ziff. 7.2 und 8.1.2;KMK Oberstufenvereinbarung 2023 S. 8-11 (Ziff. 7.2)  S. 12 (Ziff. 8.1.2);E
BW;Niveaus G/M/E Gemeinschaftsschule Sek I [lvl:bw-G | lvl:bw-M | lvl:bw-E];G (grundlegendes Niveau) | M (mittleres Niveau) | E (erweitertes Niveau);kursniveau;Gemeinschaftsschule Sek I (G führt zu Hauptschulabschluss M zu Realschulabschluss E zum Abitur) | Realschule M | Gymnasium E;Niveaustufe steht im Lernentwicklungsbericht rechts neben jedem Fach (G = Grundlegendes Niveau M E analog);Bildungsplan 2016 BW Allgemeiner Teil nicht im Volltext eingesehen;Kultusministerium BW Lernentwicklungsbericht Gemeinschaftsschule | KM-BW Gemeinschaftsschule Broschüre 2021;S
BW;Kursstufe Gymnasium [lvl:course-basic | lvl:course-advanced];Basisfach | Leistungsfach;kursniveau;Kursstufe Jgst. 11-12 (J1 und J2);nicht erhoben;Abiturverordnung BW nicht eingesehen;nicht belegt;A
BY;Anforderungsniveaus Profil- und Leistungsstufe [lvl:course-basic | lvl:course-advanced];grundlegendes Niveau | erhöhtes Anforderungsniveau (eA) | Leistungsfach;kursniveau;Gymnasium Jgst. 12 und 13 (Profil- und Leistungsstufe)|;Fachlehrplan „Deutsch 12/13 auf erhöhtem Anforderungsniveau“ und „Deutsch als Pflichtfach … auf erhöhtem Anforderungsniveau (eA) vierstündig“;Gymnasiale Schulordnung (GSO) nicht eingesehen;ISB Informationen zum LehrplanPLUS der Profil- und Leistungsstufe Deutsch S. 2 und S. 4;E
BE;Niveaus der äußeren Fachleistungsdifferenzierung [lvl:course-G | lvl:course-E];grundlegende Anforderungsniveau (GR-Niveau) | erhöhte Anforderungsniveau (ER-Niveau) | GR-Kurs | ER-Kurs;kursniveau;Integrierte Sekundarschule Sek I (Kurse) | Gemeinschaftsschule;Vormals „Grundniveau (G-Niveau)“ und „Erweiterungsniveau (E-Niveau)“ sowie G-Kurs und E-Kurs: umbenannt in GR/ER;Sekundarstufe I-Verordnung (SekIVO) §§ 27 Abs. 2 und 4 | 32 | 44 Abs. 3-4 | 48 geändert durch Verordnung zur Änderung von Vorschriften für die Sekundarstufe I (Vorlage zur Kenntnisnahme Abgeordnetenhaus 18. WP);Abgeordnetenhaus Berlin vo18-066 S. 5-6;E
BE;Niveaustufen A-H Rahmenlehrplan 1-10 Berlin/Brandenburg [lvl:bebb-A | lvl:bebb-B | lvl:bebb-C | lvl:bebb-D | lvl:bebb-E | lvl:bebb-F | lvl:bebb-G | lvl:bebb-H];Niveaustufe A | Niveaustufe B | Niveaustufe C | Niveaustufe D | Niveaustufe E | Niveaustufe F | Niveaustufe G | Niveaustufe H;kompetenzstufe;Jgst. 1-10 gemeinsamer Rahmenlehrplan;Standards je Fach nach Niveaustufen in Teil C (Zusammenfassung der Senatsantwort „Standards auf acht Niveaus“);Rahmenlehrplan Jahrgangsstufen 1-10 Teil C;Drucksache 17/17 987 vom 26.02.2016 „Niveaustufen im neuen Rahmenlehrplan“ (Titel) | berlin.de RLP-Seite (Suchzusammenfassung);S
BB;Niveaustufen A-H Rahmenlehrplan 1-10 Berlin/Brandenburg [lvl:bebb-A | lvl:bebb-B | lvl:bebb-C | lvl:bebb-D | lvl:bebb-E | lvl:bebb-F | lvl:bebb-G | lvl:bebb-H];Niveaustufe A | Niveaustufe B | Niveaustufe C | Niveaustufe D | Niveaustufe E | Niveaustufe F | Niveaustufe G | Niveaustufe H;kompetenzstufe;Jgst. 1-10 gemeinsamer Rahmenlehrplan;wie Berlin (gemeinsamer Plan);nicht eingesehen;aus Berliner Zielliste übernommen;A
BB;Kursniveaus Oberschule Sek I und Oberstufe;nicht erhoben;kursniveau;Oberschule Jgst. 7-10 (Bildungsgänge EBR und FOR);nicht erhoben;SekI-V nicht im Volltext eingesehen;siehe T7;A
HB;Anforderungsniveaus Oberschule [lvl:course-G | lvl:course-E];Niveau mit grundlegenden Anforderungen (G-Niveau) | Niveau mit erweiterten Anforderungen (E-Niveau);kursniveau;Oberschule Sek I: am Ende Jgst. 6 ein Niveau und am Ende Jgst. 8 und 10 zwei Niveaus;Inhaltsteil: „Differenzierung nach grundlegendem Niveau (G-Niveau) und erweitertem Niveau (E-Niveau)“ und rechte Spalte mit Kürzeln auf Kompetenzen aus Kap. 3 „Standards“;Oberschulverordnung § 9 Abs. 2 (äußere Differenzierung in niveaubezogenen klassenübergreifenden Kursen) laut Suchzusammenfassung 2014;Bildungsplan Deutsch Oberschule 5-10 Bremen (Stand 08/2026) Einleitung;E
HH;Mindestanforderungen Stadtteilschule Sek I;Mindestanforderungen | Anforderungen für den Erwerb der Übergangsberechtigung in die Studienstufe;erwartungsniveau;Stadtteilschule Jgst. 7-11 (Sek I und Vorstufe);Rahmenplan führt „tabellarisch aufgeführte Mindestanforderungen“ die „von allen Schülerinnen und Schülern erreicht werden müssen die den entsprechenden Abschluss erwerben wollen“ und Anforderungen für die Übergangsberechtigung in die Studienstufe;Hamburgisches Schulgesetz nicht eingesehen;Bildungsplan Stadtteilschule Chemie 7-11 S. 4-5;E
HH;Studienstufe;grundlegendes Niveau | erhöhtes Niveau;kursniveau;Studienstufe Jgst. 12-13;nicht erhoben;nicht eingesehen;siehe T7;A
HE;Fachleistungskurse Gesamtschule Sek I [lvl:course-G | lvl:course-E];A-Kurs | B-Kurs | C-Kurs | E-Kurs | G-Kurs;kursniveau;schulformübergreifende (integrierte) Gesamtschule und Förderstufe: A- und E-Kurs nach gymnasialem Bildungsgang erweitert | B-Kurs nach Realschulplan | C- und G-Kurs nach Hauptschulplan reduziert;Handreichung: „Im B-Kurs wird nach dem Realschulplan unterrichtet“ und „graduelle Niveauunterschiede“ zwischen E/A und G/C;Handreichung zur Arbeit mit den Lehrplänen der Bildungsgänge Hauptschule Realschule und Gymnasium Deutsch an schulformübergreifenden Gesamtschulen (Hessisches Kultusministerium) ältere Fassung - Geltung nicht geprüft;Handreichung Deutsch S. 2-3;E
HE;Gymnasiale Oberstufe [lvl:course-basic | lvl:course-advanced];Grundkurs | Leistungskurs;kursniveau;Einführungsphase + Qualifikationsphase;nicht erhoben;OAVO nicht eingesehen;nicht belegt;A
NI;Fachleistungsdifferenzierung Oberschule [lvl:course-G | lvl:course-E];grundlegende Anforderungsebene (G-Kurs) | erhöhte Anforderungsebene (E-Kurs) | zusätzliche Anforderungsebene (Z-Kurs);kursniveau;Oberschule Sek I: zwei oder drei Anforderungsebenen (G-Kurs Kerncurricula Hauptschule E-Kurs Realschule Z-Kurs Gymnasium);im Erlass: Kerncurricula der Hauptschule | der Realschule | des Gymnasiums je Kurs;RdErl. d. MK „Die Arbeit in der Oberschule“ vom 07.07.2011 zuletzt geändert 23.06.2015 (SVBl. 2015 Nr. 7 S. 310) Kap. 6;MK Niedersachsen download/94684 (Erlass Kap. 6) S. 2;E
NW;Äußere Fachleistungsdifferenzierung [lvl:course-G | lvl:course-E];Grundkurse | Erweiterungskurse;kursniveau;Hauptschule Englisch und Mathematik Kl. 7-9 | Gesamtschule Fächer nach Schulprogramm;„auf zwei Anspruchsebenen (Grundkurse Erweiterungskurse)“;APO-S I § 14 Abs. 2 (Hauptschule) und § 19 Gesamtschule (Fachleistungsdifferenzierung) Fassung 2012/2014;APO-S I S. 13 ff.;E
NW;Gymnasiale Oberstufe [lvl:course-basic | lvl:course-advanced];Grundkurs | Leistungskurs;kursniveau;Einführungsphase + Qualifikationsphase;nicht erhoben;APO-GOSt nicht eingesehen;nicht belegt;A
RP;Fachleistungsdifferenzierung Realschule plus [lvl:course-G | lvl:course-E];Fachleistungsdifferenzierung in Kursen und klasseninternen Lerngruppen ab Klassenstufe 7 | abschlussbezogene Klassen ab Klassenstufe 8 (integrative Form) | abschlussbezogene Klassen ab Klassenstufe 7 (kooperative Form);kursniveau;Realschule plus integrative oder kooperative Form;Kursbezeichnungen A B C nicht belegt;KMK-Vereinbarung Sek I Anlage 1 Bemerkung;KMK-Vereinbarung Sek I Anlage 1 S. 21;E
RP;Mainzer Studienstufe;Grundfach | Leistungsfach;kursniveau;MSS Jgst. 10-12;nicht erhoben;Landesverordnung MSS nicht eingesehen;nicht belegt;A
SN;Gymnasiale Oberstufe [lvl:course-basic | lvl:course-advanced];Leistungskurs | Grundkurs;kursniveau;Jgst. 11 und 12 Gymnasium;nicht erhoben;VwV zur Umsetzung der Oberstufen- und Abiturprüfungsverordnung (OAVwV) Ziff. 3.1;recht.sachsen.de vorschrift_gesamt/3361/13983 Ziff. 3.1;E
ST;Gymnasiale Oberstufe [lvl:course-basic | lvl:course-advanced];grundlegendes Anforderungsniveau | erhöhtes Anforderungsniveau;kursniveau;Einführungsphase Schuljahrgang 10 + Qualifikationsphase Schuljahrgänge 11 und 12;„Zwei Fächer auf erhöhtem und sechs auf grundlegendem Anforderungsniveau“ (Fassung für Waldorfschulen) | Landtagsanfrage 2015: „Grund- und Leistungskurse werden nicht vorgesehen“;Oberstufenverordnung ST (OberStV) nur über Suchzusammenfassungen;Suchzusammenfassung lexaris WaldorfAbiV ST | Kleine Anfrage 6/4221;S
SH;Anforderungsebenen Sek I;Erster allgemeinbildender Schulabschluss (ESA) | Mittlerer Schulabschluss (MSA) | Übergang in die Oberstufe;erwartungsniveau;Gemeinschaftsschule Sek I (alle drei Ebenen) | Gymnasium (Ebene Übergang in die Oberstufe);Fachanforderungen Sek I weisen „angestrebte Kompetenzen und zentrale Inhalte auf drei Anforderungsebenen“ aus: ESA beschreibt „die Regelanforderungen“ und MSA „die über den ESA hinausgehenden Regelanforderungen“;Schulgesetz SH und Fachanforderungen (Curricula nach SchulG);Fachanforderungen Mathematik Sek I/II Kap. 1.4 S. 21-22;E
TH;Gymnasiale Oberstufe [lvl:course-basic | lvl:course-advanced];Fächer mit grundlegendem Anforderungsniveau | Fächer mit erhöhtem Anforderungsniveau;kursniveau;Qualifikationsphase Klassenstufen 11-12 (12-jähriger Bildungsgang) vier Schulhalbjahre;nicht erhoben;ThürSchulO § 75 laut Suchzusammenfassung;anwalt24 ThürSchulG und Thüringer Schulordnung (Suchzusammenfassung);S
```

**T6 Schularten**

```csv
land;bezeichnung_woertlich;stufen;kim_schulart;bemerkung;beleg
BW;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
BW;Hauptschule;Sek I bis ESA;s03;KMK-Kategorie A1;E
BW;Werkrealschule;Sek I bis ESA und EESA (Werkrealschulabschluss);s03;KMK-Kategorie A1 laut Anlage 1;E
BW;Realschule;Sek I bis MSA;s04;KMK-Kategorie A2;E
BW;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C. Eigene Oberstufe möglich. Sek I bereitet auf alle drei Abschlüsse vor;E
BW;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
BW;Sonderpädagogisches Bildungs- und Beratungszentrum (SBBZ);Sek I;s06;Landesname von Förderschulen nicht belegt;A
BY;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
BY;Mittelschule;Sek I Jgst. 5-10 (Mittlere-Reife-Klasse Jgst. 7-10);s07;KMK-Kategorie B. Zuordnung zu KIM-Schulart ist Annahme;E
BY;Wirtschaftsschule;Sek I bis MSA;keine;KMK-Kategorie A2. Kein passender KIM-Wert;E
BY;Realschule;Sek I bis MSA;s04;KMK-Kategorie A2;E
BY;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
BE;Grundschule;Primarbereich Kl. 1-6;s02;Dauer sechs Jahre in BE und BB nicht quellenbelegt;A
BE;Integrierte Sekundarschule;Sek I und Sek II;s10;KMK-Kategorie C. Oberstufe eigenständig oder im Verbund. Zuordnung ist Annahme;E
BE;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C;E
BE;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
BB;Grundschule;Primarbereich Kl. 1-6;s02;Dauer sechs Jahre in BE und BB nicht quellenbelegt;A
BB;Oberschule;Sek I Jgst. 7-10;s07;KMK-Kategorie B. Bildungsgänge zur erweiterten Berufsbildungsreife und zur Fachoberschulreife;E
BB;Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
BB;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
HB;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
HB;Oberschule;Sek I und Sek II;s07;KMK-Kategorie C. Gymnasiale Oberstufe vorhanden oder zugeordnet;E
HB;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
HH;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
HH;Stadtteilschule;Sek I und Sek II (Vorstufe Jgst. 11 + Studienstufe);s05;KMK-Kategorie C;E
HH;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
HE;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
HE;Hauptschule;Sek I bis ESA;s03;KMK-Kategorie A1. Seit 01.08.2021 keine eigenständigen Hauptschulen mehr nur noch in Verbindung mit Grund- und Förderschulen;E
HE;Realschule;Sek I bis MSA;s04;KMK-Kategorie A2;E
HE;Verbundene Haupt- und Realschule;Sek I;s07;KMK-Kategorie B. Zuordnung ist Annahme;E
HE;Mittelstufenschule;Sek I;s07;KMK-Kategorie B. Zuordnung ist Annahme;E
HE;Schulformübergreifende (integrierte) Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C. Auch ohne Oberstufe möglich;E
HE;Schulformbezogene (kooperative) Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C. Auch ohne Oberstufe möglich;E
HE;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
MV;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
MV;Regionale Schule;Sek I;s07;KMK-Kategorie B. Zuordnung ist Annahme;E
MV;Kooperative Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C. Abitur sofern Oberstufe eingerichtet;E
MV;Integrierte Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C. Abitur sofern Oberstufe eingerichtet;E
MV;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
NI;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
NI;Hauptschule;Sek I bis ESA;s03;KMK-Kategorie A1;E
NI;Realschule;Sek I bis MSA;s04;KMK-Kategorie A2;E
NI;Oberschule;Sek I;s07;KMK-Kategorie B laut Anlage 1. Mit oder ohne gymnasiales Angebot (Z-Kurs);E
NI;Kooperative Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
NI;Integrierte Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
NI;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
NW;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
NW;Hauptschule;Sek I bis ESA;s03;KMK-Kategorie A1;E
NW;Realschule;Sek I bis MSA;s04;KMK-Kategorie A2;E
NW;Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
NW;Sekundarschule;Sek I;s10;KMK-Kategorie B. Unterricht bis Kl. 10 auf gymnasialem Standard. Keine eigene Oberstufe sondern Kooperation;E
NW;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
RP;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
RP;Realschule plus;Sek I;s07;KMK-Kategorie B. Integrative oder kooperative Form. Fachoberschule angeschlossen möglich. Zuordnung ist Annahme;E
RP;Integrierte Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
RP;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3. G9 oder G8GTS;E
SL;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
SL;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C. Eigene Oberstufe oder Oberstufenverbund;E
SL;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
SN;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
SN;Oberschule;Sek I;s07;KMK-Kategorie B;E
SN;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C;E
SN;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
ST;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
ST;Sekundarschule;Sek I;s10;KMK-Kategorie B;E
ST;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C. Oberstufe eigen oder in Kooperation;E
ST;Kooperative Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
ST;Integrierte Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
ST;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3. Durchgängig Schuljahrgänge 5-12;E
SH;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
SH;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C. Eigene Oberstufe möglich;E
SH;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
TH;Grundschule;Primarbereich Kl. 1-4;s02;nicht in KMK-Anlage 1;A
TH;Regelschule;Sek I;s07;KMK-Kategorie B. Zuordnung ist Annahme;E
TH;Gemeinschaftsschule;Sek I und Sek II;s09;KMK-Kategorie C;E
TH;Kooperative Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
TH;Integrierte Gesamtschule;Sek I und Sek II;s05;KMK-Kategorie C;E
TH;Gymnasium;Sek I und Sek II;s08;KMK-Kategorie A3;E
alle;Förderschule;Primarbereich und Sek I;s06;Landesnamen abweichend (zum Beispiel SBBZ in BW). Namen je Land nicht erhoben;A
alle;Abendgymnasium | Kolleg;Sek II (Zweiter Bildungsweg);s16;Landesrecht nicht eingesehen. KMK-Vereinbarung Sek I Ziff. 5.4.3 nennt den Zweiten Bildungsweg;A
alle;Ersatzschule (Privatschule);Primarbereich bis Sek II;s15;Ergänzungs- und Ersatzschulen je Land nicht erhoben;A
```

**T7 Lücken**

```csv
land;thema;befund;quelle
alle;Landesnormen zu Abschlussbezeichnungen;Schulgesetze und Abschlussverordnungen waren über die Landesrechtsportale per WebFetch nicht lesbar. Bezeichnungen stützen sich auf KMK-Anlage 2 (Stand 07.10.2022). Paragrafen je Land fehlen außer NW BE BY;Landesrechtsportale (JavaScript-Rendering) und KMK-Vereinbarung Sek I
alle;Anforderungsbereiche I-III;Nicht erhoben (kein Primärdokument gelesen);offen
alle;IQB-Kompetenzstufen und Regel-/Mindest-/Optimalstandard;Nicht erhoben;offen
alle;Berufliche Abschlüsse und FHR-Bezeichnungen je Land;Landesbezeichnungen der Fachhochschulreife (berufliche Schulen) nicht erhoben. Nur KMK-Oberstufenvereinbarung Ziff. 12 gelesen;KMK Oberstufenvereinbarung 2023 Ziff. 12
BW;Gemeinschaftsschule G/M/E im Bildungsplan;Wortlaut aus Allgemeinem Teil Bildungsplan 2016 nicht gelesen. Nur Kultusministerium-Material (S);Kultusministerium BW Lernentwicklungsbericht
BW;Kursstufe Bezeichnung;Basisfach/Leistungsfach ist Annahme;offen
BY;Mittelschule M-Zug und Differenzierung;Kurse und Niveauwörtlichkeit der Mittelschule nicht erhoben. Art. 7a BayEUG nur über Suchzusammenfassung;gesetze-bayern.de BayEUG Art. 7a
BY;Qualifikationsphase GSO;Paragrafen der GSO nicht eingesehen. Wortlaut „erhöhtes Anforderungsniveau (eA)“ aus ISB-Folien;ISB LehrplanPLUS Profil- und Leistungsstufe Deutsch
BE;Niveaustufen A-H im Rahmenlehrplan;Buchstaben A-H und Zuordnung zu GR/ER nicht im Rahmenlehrplan Teil C geprüft;Drucksache 17/17 987
BE;Oberstufe;Grundkurs/Leistungskurs nicht belegt;offen
BB;Kursniveaus Sek I und Oberstufe;SekI-V nicht lesbar. Weder Grundkurs/Erweiterungskurs noch GR/ER-Kurs belegt;bravors.brandenburg.de
HB;Oberstufe Bezeichnungen;nicht erhoben;offen
HH;Studienstufe-Niveaus;„grundlegendes/erhöhtes Niveau“ nicht belegt. Kursniveaus Sek I (Grundkurs/Erweiterungskurs) nicht belegt;offen
HE;Aktualität Fachleistungskurse;Handreichung ist ältere Fassung. Geltung nach Schulgesetz-Änderungen offen. Oberstufe Grundkurs/Leistungskurs nicht belegt;Hessisches Kultusministerium Handreichung Deutsch
MV;Kursniveaus Sek I und Oberstufe;kein Beleg für Niveausystem;offen
NI;Oberstufe Niveaus und aktueller Erlass;Einführungsphase belegt. Bezeichnung grundlegend/erhöht nicht gelesen. Erlass Stand 2015. Entwurf 2026 zur Fachleistungsdifferenzierung ab Jgst. 6 laut Anhörung;MK Niedersachsen Anhörung Grundsatzerlasse 2026
NW;Aktuelle APO-S I;eingesehene Fassung 2012/2014 nennt noch „Hauptschulabschluss“. Aktuelle Fassung mit „Erster Schulabschluss“ nicht gelesen. Fettdruck für E-Kurs in KLP nicht geprüft;bass.schule.nrw
RP;Kursbezeichnungen A/B/C;nicht belegt. MSS Grundfach/Leistungsfach nur Annahme;KMK-Vereinbarung Sek I Anlage 1
SL;Kursniveaus Sek I und Oberstufe;kein Beleg;offen
SN;Sek I Differenzierung;Oberschule Hauptschul-/Realschulbildungsgang nicht belegt;offen
ST;Oberstufenverordnung Wortlaut;nur Suchzusammenfassung. Sekundarschule Abschlussregeln nicht belegt;Kleine Anfrage 6/4221
SH;Oberstufe Niveaus und Kursbezeichnungen;nicht erhoben;offen
TH;Paragraf zu Anforderungsniveaus;§ 75 ThürSchulO nur aus Suchzusammenfassung. Kursniveaus Sek I nicht erhoben;anwalt24 ThürSchulG
```

Quellenumfang: rund 35 Abrufe (WebFetch und WebSearch). Gelesen habe ich die KMK-Vereinbarung Sek I (Fassung 07.10.2022, vollständig mit Anlagen 1 und 2) und die KMK-Oberstufenvereinbarung (Fassung 16.03.2023, Ziff. 1, 5, 7, 8, 12). Außerdem gelesen: NRW APO-S I (Fassung 2012/2014), die Berliner Änderungsverordnung zur SekIVO und das Bremer Bildungsplan Deutsch Oberschule (08/2026). Dazu kommen der niedersächsische Erlass und die Eltern-Info, die Hamburger Chemie-Bildungspläne und das SH-Mathematik-Fachanforderungsdokument, die hessische Handreichung, ISB Bayern und die sächsische OAVwV. Alle übrigen Landesnormen und Pläne liegen nur als Suchzusammenfassungen (beleg S) oder gar nicht vor (beleg A oder T7).
