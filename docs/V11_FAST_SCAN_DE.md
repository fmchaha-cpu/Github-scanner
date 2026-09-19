# v1.1: intelligenter Scan-Rhythmus

## Profile

- `fast`: relevante Start-, EU-, C6-, Favoriten- und Niedrigpreis-Seiten; höchstens eine Seite pro Route; kleines Detailbudget.
- `full`: alle aktivierten und rotierenden Routen; vollständige Qualitäts- und Verlaufslogik.

## Zeitplan

- `market-scanner-fast.timer`: ungefähr alle 10 Minuten, bis zu 60 Sekunden Zufallsverzögerung.
- `market-scanner.timer`: ungefähr alle 30 Minuten, bis zu 4 Minuten Zufallsverzögerung.

Beide Dienste verwenden `/var/lib/genshin-scanner/scan.lock`. Läuft bereits ein Full-Scan, wird ein kollidierender Fast-Scan ohne Fehler übersprungen. Ein Full-Scan wartet bis zu drei Minuten auf einen laufenden Fast-Scan.

## Datenspeicherung

Fast-Scans aktualisieren `last_seen` und aktuelle Angebotsfelder. Rohtext-Snapshots, Kandidatenereignisse und Verifikationsereignisse werden dabei nur für neue oder materiell geänderte Angebote angelegt. Verschwinden-Erkennung und schwere Qualitäts-Snapshots bleiben dem Full-Scan vorbehalten.
