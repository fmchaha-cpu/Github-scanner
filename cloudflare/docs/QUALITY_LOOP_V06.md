# Quality Loop v0.6

Ziel ist nicht nur "mehr Listings", sondern **messbar bessere Erkennung**.

## Schleife

```text
Scan
 -> Page-/Fetch-Diagnostik
 -> Parser-/Field-Qualitaet
 -> Candidate + Calibration Verification
 -> historische Verification Events
 -> Quality Snapshot
 -> Problemklasse
 -> gezielte Code-/Query-Aenderung
 -> Regressionstest
 -> neuer Scan
 -> Vorher/Nachher-Vergleich
```

## Was pro Page gemessen wird

- HTTP oder Browser
- HTTP Status
- Laufzeit
- HTML-/Textgroesse
- Anchor-Anzahl
- erkannte Detail-Links
- geparste Listings
- Page Title
- Content Hash
- Challenge-/Block-Signale
- Fallback-Grund
- Final URL
- Sample-Detail-URLs
- listing-aehnliche URLs, die das konfigurierte Detail-Pattern **nicht** matchen
- bei Browser-Fallback zusaetzlich dieselben Kerndaten der vorherigen HTTP-Probe

Damit kann man unterscheiden:

- Marktplatz wirklich leer
- falsche Kategorie-URL
- Redirect/Shell-Seite
- Anti-Bot-/Challenge-Seite
- Detail-Pattern veraltet
- Parser findet Links, baut aber keine Rows
- Parser baut Rows, aber Seller/Server/Availability fehlen

## Was pro Plattform gemessen wird

- Listings / Kandidaten
- Preis-/Server-/Seller-/Availability-Abdeckung
- Detail-Verifikationsquote
- Candidate-Detail-Verifikationsquote
- Identity-/Strict-Live-Quote
- durchschnittliche Extraction Quality
- Browser-/Fallback-Anteil
- Zero-Link-/Zero-Parsed-Seiten
- Parse Yield
- Blocksignale
- Pattern-Drift-Signale

## Verification Events

Jeder Candidate- oder Calibration-Deep-Check erzeugt ein Event mit:

- Plattform
- Grund (`candidate`, `calibration`, `manual_exact_url`)
- Fetch Mode / Fallback
- HTTP Status / Seitengroesse
- Blocksignalen
- Identity Verified / Strict Live
- Extraction Quality
- Quality Flags

Dadurch wird sichtbar, ob z. B. ein Seller-Fix wirklich die Identity-Quote von PlayerAuctions verbessert oder nur mehr False Positives produziert.

## Calibration Samples

Nicht nur Kandidaten werden geprueft. Pro Quelle werden einige Nicht-Kandidaten gezielt tief gelesen, bevorzugt mit fehlendem Seller/Server/Availability oder guenstigen EU-Angeboten.

Das ist wichtig, weil man sonst nur die "interessanten" Listings testet und Parserfehler im Rest des Marktes nicht bemerkt.

## Wie eine Verbesserung bewertet wird

Eine Codeaenderung ist nicht automatisch gut, nur weil die Listing-Zahl steigt. Bei Vorher/Nachher sollten mindestens diese Punkte betrachtet werden:

1. Listings und Coverage steigen oder bleiben stabil.
2. Seller-/Server-/Preis-Abdeckung verbessert sich.
3. Identity Verified steigt **ohne** mehr Identity-Mismatches.
4. Parse Yield steigt.
5. Calibration Samples bleiben plausibel.
6. Zero-Hit-/Pattern-Drift-/Block-Signale sinken.
7. Historische Duplicate-/Comparable-Daten werden nicht kuenstlich aufgeblasen.

## Feedback-Labels

```text
false_positive
false_negative
bad_price
bad_server
bad_seller
bad_status
bad_c6_parse
duplicate_confirmed
duplicate_rejected
security_issue
missed_kronjuwel
```

Ein bestaetigter Fehler sollte nach Moeglichkeit als Regressionstest in die naechste Version eingehen.
