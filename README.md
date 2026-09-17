# Genshin Market Tracker v0.6.0

Hybrid-System fuer hohe Markt-Abdeckung, identity-bound Verifikation, historische Preisvergleiche und eine messbare Verbesserungsschleife.

## Was v0.6 verbessert

v0.6 konzentriert sich auf **Recall + Datenqualitaet + Diagnosefaehigkeit**. Ein Scan soll nicht nur Listings sammeln, sondern auch genug Informationen hinterlassen, um zu erkennen, *warum* eine Quelle oder ein Parser schlecht funktioniert.

- **Smarter HTTP -> Browser Fallback**: Eine grosse HTML-Seite gilt nicht mehr automatisch als erfolgreich. Wenn eine Indexseite 0 Listing-Links liefert, Challenge-Signale zeigt oder fast leer ist, wird normal per Playwright nachgeladen.
- **HTTP-vs-Browser Telemetrie**: Der Scanner speichert getrennt, was die HTTP-Antwort zeigte und was nach Browser-Fallback sichtbar war.
- **Pattern-Drift-Erkennung**: Listing-aehnliche URLs, die nicht zum konfigurierten Detail-Pattern passen, werden als Diagnose-Samples gespeichert. So fallen geaenderte Marktplatz-URLs schneller auf.
- **Final-URL/Redirect-Diagnose**: Weiterleitungen und Shell-/Challenge-Seiten werden sichtbarer.
- **Sicherere Karten-Grenzen**: Preis/C6/Seller sollen nicht mehr so leicht von einer benachbarten Listing-Karte uebernommen werden.
- **Profil-basierte Seller-Erkennung**: Neben Text wie `Seller:` werden auch oeffentliche Store-/Member-/Profile-Links auf Karten und Detailseiten genutzt.
- **Forum-Filter**: WTB/Buying/Searching-Threads auf EpicNPC/PlayerUp werden nicht als Verkaufsangebote behandelt.
- **Adaptive Deep Verification**: Kandidaten werden priorisiert tief verifiziert; zusaetzlich werden bewusst Nicht-Kandidaten als Calibration Samples geprueft.
- **Verification Events**: Jeder Deep-Verification-Versuch wird historisch protokolliert. Damit kann man spaeter pro Plattform messen, wie oft Identity-Verifikation wirklich klappt.
- **Per-Platform Quality**: Preis-, Server-, Seller-, Availability-, Detail- und Identity-Quoten werden pro Plattform getrennt ausgewertet.
- **Parser-/Fetch-Diagnostik**: Browser-Anteil, Fallback-Anteil, Block-Signale, Zero-Hit-Seiten, Parse-Yield, wiederholter identischer Content und Pattern-Misses werden gemessen.
- **Quality Trends**: Qualitaetssnapshots koennen ueber mehrere Runs verglichen werden, inklusive Plattform-Trends.
- **Taeglicher Quality Audit**: GitHub Actions fasst Qualitaet, Parserdiagnostik, Trends und Verification Performance zusammen.

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

Siehe [`docs/V06_UPGRADE_DE.md`](docs/V06_UPGRADE_DE.md).

## Grenzen

Keine Garantie auf 100 % Marktabdeckung. Es werden keine Logins, CAPTCHAs, Rate Limits oder Anti-Bot-Schutzmechanismen umgangen. Wenn eine Quelle eine Challenge zeigt, versucht v0.6 nur normales oeffentliches Browser-Rendering und **misst/markiert** das Problem. Historische Asking Prices sind nicht automatisch Settlement Prices. Unsicherheit und Evidenzstaerke bleiben deshalb explizit.
