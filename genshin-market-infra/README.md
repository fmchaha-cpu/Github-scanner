# Genshin Market Infrastructure

Ein Hybrid-System fuer hohe Markt-Abdeckung und anschliessende qualitative Accountbewertung.

## Kernidee

- **GitHub Actions** sammelt oeffentlich sichtbare Listings regelmaessig.
- **Cloudflare Worker + D1** speichert Listings, Snapshots, Coverage und Kandidatenhistorie.
- Der automatische Detector sucht billig/ungewoehnlich/stark – inklusive Living-History-/Dormant-Veteran-Profilen.
- **ChatGPT** macht die tiefe identity-bound Verifikation und entscheidet, ob etwas wirklich ein bezahlbares Kronjuwel ist.
- Die bestehende **Excel-Datei** bleibt der taeglich aktualisierte Analyse-Tracker, nicht die Primaerdatenbank.

## Schnellstart

Siehe [`docs/SETUP_DE.md`](docs/SETUP_DE.md).

## Bereits aktivierte Quellen im Starterpaket

- PlayerAuctions: EU, C6, mehrere Character-Kategorien, Reroll
- ZeusX: Genshin Accounts Index
- EpicNPC: EU Forum, erste drei Seiten
- PlayerUp: Account-Index + Preis-aufsteigend

Eldorado und G2G sind absichtlich noch deaktiviert, bis ihr aktueller oeffentlicher Listing-Aufbau sauber kalibriert wurde. Das System markiert solche Coverage-Luecken statt sie zu verschleiern.

## Wichtige Grenzen

- Keine Garantie auf 100 % aller Listings.
- Kein Umgehen von Logins, CAPTCHA, Rate Limits oder Anti-Bot-Massnahmen.
- Marketplace-HTML kann sich aendern; deshalb Coverage- und Health-Monitoring.
- Der Detector ist **Triage**, keine Kaufentscheidung.
