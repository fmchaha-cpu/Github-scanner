# Changelog v0.6.0

## Recall / Fetching

- HTTP-Seiten mit 0 Listing-Links, Challenge-Signalen oder zu wenig Inhalt triggern Browser-Fallback.
- HTTP-Probe und Browser-Ergebnis werden getrennt diagnostiziert.
- Final URL wird gespeichert, um Redirects leichter zu erkennen.
- Listing-aehnliche aber nicht gematchte URLs werden als Pattern-Drift-Samples erfasst.
- PlayerAuctions hat einen breiten Root-Index zusaetzlich zu EU/C6/Character-Suchen.
- Pagination und rotierende Character-Suchen bleiben erhalten.

## Parsing

- Karten-Grenzen verhindern staerker das Vermischen benachbarter Angebote.
- Seller-Erkennung nutzt zusaetzlich Store-/Member-/Profile-Links.
- EpicNPC/PlayerUp WTB-/Buying-Threads werden gefiltert.
- Parser Strategy und Extraction Quality werden gespeichert.

## Verification

- Kandidaten werden adaptiv tief verifiziert bis zum konfigurierten Hard Cap.
- Zusaetzliche Calibration Samples pruefen, ob der Parser ausserhalb der Kandidaten korrekt arbeitet.
- Detail-Fetch-Mode, Fallback-Reason, Blocksignale und HTTP-Status werden pro Listing gespeichert.
- Neue `verification_events` behalten jeden Verifikationsversuch historisch statt nur den letzten Zustand.

## Quality / Observability

- Per-Platform Completeness und Verification Quality.
- Page-Level Fetch-/Parserdiagnostik in `coverage_diagnostics`.
- Pattern-Drift, repeated-content, zero-yield, block/challenge und seller-gap Signale.
- `/v1/coverage/diagnostics`
- `/v1/verification/events`
- `/v1/quality/trends` mit Plattformverlauf.
- Daily Quality Audit zeigt Plattformqualitaet, Fetch/Parser-Probleme, Trends und Verification Performance.

## Tests

- Regressionstests fuer PlayerAuctions Seller/Card-Boundaries.
- EpicNPC Seller + Buying-Thread-Filter.
- Challenge/Zero-Link Browser-Fallback.
- Pattern-Drift-Diagnose.
- Adaptive Calibration Verification.
- Quality-Signal-Tests.
- D1-Schema-/Migrationstests inklusive Observability-Tabellen.
