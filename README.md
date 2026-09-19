# Dream Account Market Scanner v1.1.2

Produktionssystem für Genshin-Traumaccounts und separat bewertete Warframe-Founder-Angebote.

- Contabo-VPS mit schnellem Kernscan ungefähr alle 10 Minuten und vollständigem Scan ungefähr alle 30 Minuten.
- GitHub Actions für CI und manuell startbaren Fallback – kein konkurrierender Zeitplan.
- Discord-Alerts mit Deduplizierung und ohne erlaubte Mentions.
- Genshin-Wunschpreis 100–200 und Warframe bis 300 sind weiche Präferenzen. Gute Treffer außerhalb werden weiter gemeldet.
- Warframe meldet erst dann, wenn eine Detailseite Founder plus mindestens ein exklusives Prime-Item nennt. Das ist Angebots-Evidenz, kein Echtheitsbeweis.
- Ausschließlich öffentliche Seiten: kein Login-, CAPTCHA-, Rate-Limit- oder Anti-Bot-Bypass.

## v1.1.2 – D1-Schreiboptimierung

- Unveränderte Listing-Daten werden nicht mehr bei jedem Scan vollständig neu geschrieben.
- Fast-Scans überspringen unveränderte Listings vollständig; Full-Scans schreiben höchstens einmal pro Stunde ein kompaktes Lebenszeichen.
- Snapshots, Kandidaten- und Verifikationsereignisse entstehen nur bei neuen oder tatsächlich geänderten Listings.
- Dynamische Kategoriepfade bleiben als kompakte Discovery-Metadaten erhalten. Die schreibintensive Verschwinden-Verfolgung bleibt auf exakte manuelle Listing-URLs beschränkt.
- Der überholte doppelte Eintrag jeder Coverage-Beobachtung entfällt; `coverage_paths` bleibt die maßgebliche Tabelle.
- API-Zähler zeigen geänderte, übersprungene und per Heartbeat aktualisierte Listings. Die Erkennungs- und Alert-Regeln bleiben unverändert.

Installation: [`docs/V1_SERVER_INSTALL_DE.md`](docs/V1_SERVER_INSTALL_DE.md)  
Architektur: [`docs/V1_ARCHITECTURE_DE.md`](docs/V1_ARCHITECTURE_DE.md)  
Discord: [`docs/DISCORD_SETUP_DE.md`](docs/DISCORD_SETUP_DE.md)

## Bewährter Genshin-Kern aus v0.10

## v0.10.0 – Identity + Plausibility

v0.10 is the first version built from the successful v0.9.3 production scan instead of from crash recovery. The scan completed with 130 listings, 6 candidates, 17 historical records, 94.6% seller coverage and 87.7% server coverage, but 0 identity-verified listings. v0.10 targets that quality bottleneck directly.

- **Identity is separated from merit:** an exact listing can now be identity-verified even when a C6/resource claim is still unconfirmed. Alert eligibility still requires the valuable claim to be supported.
- **Missing C6 text is uncertainty, not contradiction:** only explicit conflicting C6-character evidence is a hard mismatch. `detail_unconfirmed_c6` records the weaker case.
- **Blocked detail pages are never parsed as listings:** challenge pages preserve the good card observation and become `detail_blocked:*` telemetry instead of corrupting title/seller/C6 evidence.
- **Rich card titles survive generic H1s:** labels such as `www.epicnpc.com` or challenge headings no longer overwrite a useful marketplace title.
- **Seller consensus:** profile candidates are ranked and the exact normalized card seller is preferred. Matching ignores punctuation/case but never uses fuzzy username similarity.
- **Price plausibility hold:** absurd parses such as a mature/whale account at $1.10 are kept for diagnostics but cannot trigger an alert. Dedicated plausibility probes deep-check a small sample.
- **Comparable telemetry clarified:** reports now distinguish *any* historical coverage from *usable-confidence* coverage.
- **More diagnostic output:** identity mismatch breakdown, blocked-detail count, merit-unconfirmed count and price-plausibility anomalies are reported explicitly.
- **Collector/Worker versions decoupled:** collector v0.10 intentionally reuses the proven Worker API v0.9, so no Cloudflare deploy is required for this upgrade.
- **GitHub Actions updated:** checkout v5 and setup-python v6 remove the Node 20 deprecation path.
v0.9.3 Hotfix: CI-safe async batching tests ohne zusaetzliches pytest-asyncio Plugin.

Hybrid-System fuer hohe Markt-Abdeckung, identity-bound Verifikation, historische Preisvergleiche und eine messbare Verbesserungsschleife.


## v0.9.2 Hotfix

v0.9.2 behebt den im ersten echten v0.9-Produktionslauf gemessenen Upload-Timeout: Der Collector kam durch Worker-Handshake, Installation und Tests, scheiterte aber beim Schreiben eines 40-Listing-Batches nach D1 mit `httpx.ReadTimeout`. Listings werden jetzt standardmaessig in 8er-Chunks uebertragen (hartes Maximum 20), und der API-Timeout wurde auf 60 Sekunden erhoeht. Blindes Wiederholen eines bereits zeitlich abgebrochenen Schreibvorgangs wird bewusst vermieden, damit Snapshot-Evidenz nicht doppelt geschrieben wird. Fuer v0.9.2 ist kein neuer Cloudflare-Deploy noetig; Worker v0.9 ist kompatibel.

## v0.9.1 Hotfix

v0.9.1 behebt den GitHub-Actions-Preflight aus v0.9.0: `/health` wird jetzt mit dem vorhandenen API-Token, browseraehnlichem User-Agent und kurzen Retries geprueft. Der fehlerhafte 403-Preflight konnte v0.9.0 stoppen, bevor Tests oder der eigentliche Marktscan starteten. Fuer diesen Hotfix ist allein kein neuer Cloudflare-Deploy notwendig.

## Was v0.9 verbessert

Der erste v0.8-Produktionsscan war ein Recall-Durchbruch: 294 statt 79 Listings, davon 215 von PlayerAuctions. Gleichzeitig zeigte die neue Diagnostik einen klaren Qualitaetsfehler: dieselbe PlayerAuctions-Listing-URL wird oft ueber Titel/Bild **und** einen spaeteren `BUY NOW`-Link verlinkt. Der spaetere generische Anchor konnte in v0.8 die reichere Beobachtung ueberschreiben.

v0.9 korrigiert genau diese gemessenen Schwachstellen:

- **Evidence-preserving Card Merge:** gleiche exakte Produkt-URL wird aus mehreren Anchors zusammengefuehrt statt ueberschrieben.
- **Rich-title preference:** Titel/Bild-Labels schlagen generische `BUY NOW`, `View` oder `Details` Anchors.
- **PlayerAuctions Hydration:** Server/AR koennen konservativ aus Produkt-Slug und bekannter EU-Query abgeleitet werden; Kategorie-URLs zaehlen nicht mehr faelschlich als Parser-Drift.
- **AR parser v0.9:** erkennt auch `MaleAR55`, `FemaleAR 55` und `FamaleAR-54`.
- **ZeusX Detail Evidence:** `Server/Region` und semantische/stylisierte Kauf-Controls werden staerker erkannt, ohne generischen Text als Live-Beweis zu akzeptieren.
- **Verification budget:** Kandidaten erhalten ein festes Budget; zusaetzlich werden guenstige, potenziell wertvolle unvollstaendige Listings als `merit_probe` tief geprueft.
- **Historical Seed Self-Heal:** fehlt der evidence-backed Tracker-Seed in D1, importiert v0.9 ihn automatisch und verifiziert die persistente Anzahl.
- **Comparables bleiben passiv:** historische Vergleiche dienen weiterhin als Mess-/Kalibrierungsdaten und veraendern Alerts noch nicht automatisch.

Die v0.8-Funktionen (Worker/Collector Handshake, Historical Stats, passive Candidate Comparables) sowie v0.7 Source Health/Circuit Breaker/Field Provenance und die Historical Comparable Engine bleiben erhalten.

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

## Scan-Rhythmus (v1.1.2)

Ein leichter Kernscan prüft relevante Marktseiten ungefähr alle 10 Minuten. Der vollständige Scan läuft ungefähr alle 30 Minuten und bleibt für breite Abdeckung, Verschwinden-Erkennung und Qualitäts-Snapshots zuständig. Unveränderte Fast-Scan-Beobachtungen erzeugen keine Listing-Schreibvorgänge. Bei Full-Scans wird `last_seen` für unveränderte Listings höchstens einmal pro Stunde aktualisiert, sodass das Drei-Stunden-Aktivitätsfenster erhalten bleibt. Der GitHub-Workflow ist nur ein manueller Fallback. Blockierte Quellen werden nicht umgangen.

## Upgrade

Siehe [`docs/V1_SERVER_INSTALL_DE.md`](docs/V1_SERVER_INSTALL_DE.md).

Kurzfassung:

1. ZIP-Inhalt ueber das bestehende Repository kopieren. `.git` **nicht** loeschen.
2. Commit + Push.
3. Worker v1.1.2 deployen; für dieses Update ist keine neue D1-Migration nötig.
4. VPS-Service installieren, Secret-Datei ausfüllen und einen kontrollierten Testlauf starten.

## Grenzen

Keine Garantie auf 100 % Marktabdeckung. Es werden keine Logins, CAPTCHAs, Rate Limits oder Anti-Bot-Schutzmechanismen umgangen. Sichtbare Challenge-Seiten werden markiert und durch Circuit Breaker begrenzt. Historische Asking Prices sind nicht automatisch Settlement Prices. Unsicherheit und Evidenzstaerke bleiben explizit.
