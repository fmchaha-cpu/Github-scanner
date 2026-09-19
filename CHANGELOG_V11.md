# v1.1.0

- Zweistufiger VPS-Scan: schneller Kernscan alle 10 Minuten, vollständiger Scan alle 30 Minuten.
- Fast-Profil prüft nur markierte Kernrouten und reduziert Detailabrufe.
- Unveränderte Fast-Scan-Angebote erzeugen keine neuen Rohtext-Snapshots, Kandidaten- oder Verifikationsereignisse.
- Fast-Scans lösen keine Verschwinden-Erkennung und keine schweren Qualitäts-Snapshots aus.
- Gemeinsame Dateisperre verhindert parallele Browserläufe; Fast-Scans werden bei einem laufenden Full-Scan sauber übersprungen.
- EpicNPC bleibt im vollständigen Scan, wird im häufigen Fast-Scan wegen Challenge-Seiten ausgelassen.
- Worker-API 1.1 meldet `smart_scan_profiles` und `sparse_snapshots`.
