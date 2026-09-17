# Genshin Market Tracker v0.8.0

Hybrid-System fuer hohe Markt-Abdeckung, identity-bound Verifikation, historische Preisvergleiche und eine messbare Verbesserungsschleife.

## Was v0.8 verbessert

v0.8 baut auf den zwei reproduzierbaren v0.7-Scans auf. Der Circuit Breaker bleibt erhalten, waehrend die naechsten systematischen Schwachstellen gezielt gemessen und repariert werden.

- **Hydration-/False-Block-Fix:** CAPTCHA-/Challenge-Woerter in versteckten Scripts zaehlen nicht mehr automatisch als Block. Sichtbare Human-Checks bleiben blockiert.
- **Marketplace settle timing:** echte ZeusX-/PlayerUp-Seiten mit Listing-Links erhalten kurz Zeit fuer Seller-/Profil-Widgets; echte Challenge-Seiten werden weiterhin frueh beendet.
- **ZeusX Seller Recovery:** Seller kann aus Profil-Link, Profilbild-Alt-Text und Detail-Sidebars ausserhalb von `<main>` erkannt werden.
- **Staerkere Availability-Evidenz:** echte Detailseiten-Controls wie `Buy Now`, `Purchase Now` oder `Add to cart` koennen Live-Verfuegbarkeit belegen; Controls aus verlinkten Related Listings werden ignoriert.
- **Worker/Collector Handshake:** GitHub Actions und der Collector selbst pruefen vor dem Scan, ob wirklich Worker v0.8 mit den erwarteten Faehigkeiten deployed ist. Ein veralteter Worker faellt frueh und klar auf.
- **Persistent Historical Stats:** `/v1/historical/stats` zeigt den tatsaechlichen D1-Historienpool getrennt von historischen Statusbeobachtungen des aktuellen Scans.
- **Seed-Verifikation:** der Historical-Seed-Workflow prueft nach dem Upsert Anzahl der Tracker-Seeds und bestaetigten Sold-Anker.
- **Passive Candidate Comparables:** fuer bis zu acht Top-Kandidaten werden historische Median-/Spread-/Confidence-Werte abgefragt und als Telemetrie gespeichert. Sie veraendern in v0.8 noch keine Alerts oder Scores.
- **Mehr Calibration Data:** ZeusX und PlayerUp erhalten etwas hoehere Deep-Verification-Budgets fuer bessere Feld- und False-Negative-Messung.
- **Version-to-Version Quality:** neue Metriken fuer Historical Pool, confirmed sold, Comparable Coverage und Worker-Kompatibilitaet.

Die v0.7-Funktionen (Circuit Breaker, Source Health/Cooldown, Field Provenance, Calibration/Control Samples, Known-case Benchmark) sowie die Historical Comparable Engine aus v0.5/v0.6 bleiben enthalten.

## Wichtige Read-only Endpunkte

```text
/health
/v1/candidates/recent?hours=24
/v1/review-queue
/v1/coverage/recent?hours=24
/v1/coverage/diagnostics?hours=24
/v1/verification/events?hours=24
/v1/quality/recent?hours=24
/v1/quality/trends?limit=20
/v1/quality/by-version?limit=50
/v1/source-health
/v1/quality/snapshots?limit=20
/v1/historical/recent?limit=100
/v1/historical/stats
/v1/comparables?url=<URL-ENCODED-LISTING>&limit=30
/v1/duplicates/recent?hours=168
/v1/status/history?url=<URL-ENCODED-LISTING>
/v1/feedback/summary?days=30
```

## Rollen im System

- **Collector** = Discovery, Recall, Triage und Messdaten sammeln.
- **D1** = Listings, Snapshots, Coverage, Parserdiagnostik, Verification Events, Statushistorie und historische Anker.
- **Comparable Engine** = deskriptiver Marktvergleich; kein Kaufentscheidungsautomat.
- **ChatGPT/Human Review** = tiefe Pruefung von Identitaet, Seller, Security, persoenlicher Relevanz und auffaelligen Kandidaten.
- **Excel** = gebuendelter Analyse-/Ranking-Output, nicht Primaerdatenbank.

## Scan-Rhythmus

Der normale GitHub-Scan laeuft einmal pro Stunde bei Minute 17. Blockierte Quellen werden innerhalb eines Runs frueh abgebrochen; funktionsfaehige Quellen erhalten das Verification-Budget.

## Upgrade

Siehe [`docs/V08_UPGRADE_DE.md`](docs/V08_UPGRADE_DE.md).

Kurzfassung:

1. ZIP-Inhalt ueber das bestehende Repository kopieren. `.git` **nicht** loeschen.
2. Commit + Push.
3. PowerShell im Repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v08.ps1
```

4. GitHub Actions: **Import tracker historical seed** einmal ausfuehren.
5. Danach **Genshin market scan** starten.

## Grenzen

Keine Garantie auf 100 % Marktabdeckung. Es werden keine Logins, CAPTCHAs, Rate Limits oder Anti-Bot-Schutzmechanismen umgangen. Sichtbare Challenge-Seiten werden markiert und durch Circuit Breaker begrenzt. Historische Asking Prices sind nicht automatisch Settlement Prices. Unsicherheit und Evidenzstaerke bleiben explizit.
