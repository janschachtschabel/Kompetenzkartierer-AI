# Vergleichsdatensatz v62.493 (Saat des Quellregisters)

Zwei Tabellen aus dem offenen Datensatz einer Vergleichs-App für Lehrpläne. Sie stammen aus
deren Länder-Auszug Deutschland (`data_deutschland.json.gz`, Modellversion `62.493-at-luecken`,
Stand 2026-09-30). Daraus abgeleitet wurden sie als Semikolon-CSV mit BOM und CRLF, im
Rechercheordner des Vorgängerprojekts (`docs/recherche/konkurrenz/`).

**Lizenz:** Der Deutschland-Auszug steht unter **CC0 1.0 Universal**. Diese Dateien dürfen also
ohne Namensnennung kopiert, verändert und verbreitet werden. Andere Länder-Auszüge desselben
Angebots haben eigene Lizenzen, zum Beispiel Frankreich, England und Singapur. Sie sind hier
nicht enthalten.

**Verwendung (Gesamtplan §7.5):**
- **Saat:** Jede nicht ausgelassene Zeile wird ein Kandidat im Quellregister mit Herkunft
  `vergleichsdatensatz-v62.493` und Status `unchecked` (`python -m app.sources.seed`).
- **Übernommene Felder:** URL, Archiv-URL, Land, Schulform, Fach, Jahrgänge, Verbindlichkeit und
  Quelltyp, dazu Bildungsstufe, Fach-Schlüssel und Wayback-Zeitstempel der Archivkopie.
- **Nicht übernommen:** Titel, Beschreibungen, Themen, Knotenzahlen und Verifikationsangaben.
- **Ausgelassen:** ESA-Ableitungen und „kanonisch“ modellierte Zeilen.
- **Zugangsnotizen:** Die Umgehungshinweise werden Zugangsnotizen je Land, Schulform und Fach;
  ohne Schulform oder Fach gelten sie für alle des Landes. Technische Sperren umgehen wir nicht.

Die Dateien bleiben byte-gleich (`.gitattributes`: `-text`). Ein Test vergleicht sie mit dieser
Tabelle (`backend/tests/sources/test_seed_files.py`).

| Datei | Bytes | SHA-256 |
|---|---|---|
| `lehrplan_dokumente_de.csv` | 2.118.571 | 326b00742837e049240a2eeafbe4919928620b5e7656417829fbe016be2156d5 |
| `umgehungshinweise_de.csv` | 107.686 | b72b7098cc0d11cebc229a037eeb33807938fd6d2e827ae39a1fd1482321196a |

**Inhalt:**
- **`lehrplan_dokumente_de.csv`:** 1.831 Dokumente je Land × Schulform × Fach. Nach dem
  Auslassen bleiben 1.498 Einträge mit 1.278 Adressen (1.279 Zeichenketten: eine trägt einen
  Vermerk in Klammern) auf 34 Hosts.
- **`umgehungshinweise_de.csv`:** 355 Hinweise auf gesperrte Portale und Umwege: Wayback-Archiv,
  Sekundärquelle, Sperre 403/429, Spiegel, GEI.
