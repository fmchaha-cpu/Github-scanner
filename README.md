# Genshin Market Tracker v0.7.0

Hybrid-System fuer hohe Markt-Abdeckung, identity-bound Verifikation, historische Preisvergleiche und eine messbare Verbesserungsschleife.

## Was v0.7 verbessert

v0.7 baut auf der v0.6-Diagnostik auf und macht blockierte Quellen billiger, die Extraktion nachvollziehbarer und die Weiterentwicklung messbarer.

- **Circuit Breaker** stoppt eine Quelle innerhalb des Runs nach bestaetigtem Challenge/Zero-Yield statt viele identische Blockseiten zu laden.
- **Persistente Source Health + Cooldown** verhindert wiederholte erfolglose Vollscans und sondiert spaeter automatisch erneut.
- **Field Provenance** speichert, ob Werte aus Karte, Profil-Link, Detailtext, JSON-LD oder URL stammen.
- **Calibration-Gap + Control Samples** pruefen neben Kandidaten auch gezielt unvollstaendige und scheinbar unauffaellige Listings.
- **Known-case Benchmark Corpus** schuetzt bekannte wichtige Faelle vor Regressionen.
- **Version-to-Version Quality** vergleicht exakte Collector-Scan-Metriken.
- **Stale-Flag-Recompute** verhindert alte Kartenwarnungen nach erfolgreicher Detailpruefung.
- **Historical Seed v26** bringt 17 preisbekannte, evidenzklassifizierte historische Tracker-Angebote in die Comparable Engine.

Die v0.6-Features (Browser-Fallback, Seller/Profile-Erkennung, Parserdiagnostik, Verification Events, per-platform Quality) bleiben enthalten.

## Bereits aus v0.5 enthalten

- Historical Comparable Engine mit getrennten Evidenzklassen
- `SOLD_CONFIRMED`, `SOLD_CLAIMED`, `EXPIRED_REMOVED`, `OUTCOME_UNKNOWN`, `RISK_CONTAMINATED`
- konservative 3-Miss-Entfernungserkennung
- gewichteter Median / robuste historische Vergleiche
- Relisting-/Duplicate-Fingerprints
- Historical Import + manuelle Annotation
- Feedback Loop fuer False Positives / False Negatives / Parserfehler
- parallele Account-Archetypen statt einer einzigen Kategorie

## Wichtige Read-only Endpunkte

```text
/health
/v1/candidates/recent?hours=24
/v1/review-queue
/v1/coverage/recent?hours=24
/v1/coverage/diagnostics?hours=24
/v1/coverage/diagnostics?hours=24&platform=PlayerAuctions
/v1/verification/events?hours=24
/v1/quality/recent?hours=24
/v1/quality/trends?limit=20
/v1/quality/by-version?limit=50
/v1/source-health
/v1/quality/snapshots?limit=20
/v1/historical/recent?limit=100
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

Der normale GitHub-Scan laeuft einmal pro Stunde bei Minute 17. Das Runtime-Budget wird lieber fuer Browser-Fallback, Pagination und Deep Verification genutzt als fuer viele oberflaechliche Runs.

## Upgrade

Siehe [`docs/V07_UPGRADE_DE.md`](docs/V07_UPGRADE_DE.md).

## Grenzen

Keine Garantie auf 100 % Marktabdeckung. Es werden keine Logins, CAPTCHAs, Rate Limits oder Anti-Bot-Schutzmechanismen umgangen. Wenn eine Quelle eine Challenge zeigt, versucht v0.7 nur normales oeffentliches Browser-Rendering und **misst/markiert** das Problem. Historische Asking Prices sind nicht automatisch Settlement Prices. Unsicherheit und Evidenzstaerke bleiben deshalb explizit.
