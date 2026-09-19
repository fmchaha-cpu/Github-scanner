# Freigabeprotokoll v1.1

## Ergebnis

- Python: 95 Tests bestanden.
- TypeScript: `tsc --noEmit` bestanden.
- Benchmark: 6 von 6 bekannten Fällen bestanden.
- systemd: Full-Service, Fast-Service und beide Timer erfolgreich verifiziert.
- Bash: Installations- und Upgrade-Skripte syntaktisch gültig.

## Scanlast

- Full-Profil: höchstens 33 konfigurierte Indexseiten vor Rotation und Circuit-Breakern.
- Fast-Profil: höchstens 9 Kernseiten; EpicNPC ist wegen Challenge-Seiten ausgeschlossen.
- Fast-Profil: höchstens 3 Detailprüfungen pro Quelle.

## Datensicherheit

- Fast-Scans speichern unveränderte Listings nicht erneut als Rohtext-Snapshot.
- Fast-Scans erzeugen keine Verschwinden-Markierungen und keine schweren Qualitäts-Snapshots.
- Full-Scans bleiben für vollständige Markt- und Qualitätsgeschichte verantwortlich.
- Gemeinsame Dateisperre verhindert parallele Browser-Scans.
- Bestehende D1-Tabellen und Daten bleiben unverändert; keine neue Migration erforderlich.
