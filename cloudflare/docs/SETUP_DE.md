# Einrichtung – Schritt fuer Schritt

## Was du brauchst

- kostenloses Cloudflare-Konto
- GitHub-Konto
- Windows-PC fuer die erste Einrichtung
- Git / GitHub Desktop
- Node.js LTS

Python musst du lokal nicht zwingend installieren, wenn der Collector nur in GitHub Actions laufen soll.

---

## 1. Projekt in GitHub hochladen

1. Auf GitHub ein neues Repository erstellen.
2. Fuer kostenlose Actions am einfachsten **Public** waehlen.
3. Projektdateien in das Repository kopieren.
4. Commit + Push.

Es werden keine Passwoerter oder Markt-API-Tokens ins Repository geschrieben.

---

## 2. Cloudflare Worker + D1 einrichten

Im Projektordner PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_cloudflare.ps1
```

Das Skript:

1. installiert Wrangler,
2. oeffnet Cloudflare-Login,
3. erstellt D1,
4. laesst dich die `database_id` in `cloudflare/wrangler.toml` eintragen,
5. spielt Basis-Schema + Quality-Erweiterung ein,
6. erzeugt einen kryptographisch zufaelligen Schreib-Token,
7. speichert ihn als Cloudflare Secret,
8. deployt den Worker.

Am Ende bekommst du etwa:

```text
https://genshin-market-api.<dein-subdomain>.workers.dev
```

Teste:

```text
https://...workers.dev/health
```

Es sollte JSON mit `"ok": true` erscheinen.

---

## 3. GitHub Actions Secrets setzen

Repository -> **Settings -> Secrets and variables -> Actions**.

### MARKET_API_URL

```text
https://genshin-market-api.<dein-subdomain>.workers.dev
```

### MARKET_API_TOKEN

In der lokalen Datei:

```text
.generated_ingest_token.txt
```

Den Inhalt kopieren. Die Datei niemals committen.

---

## 4. Ersten Scan starten

GitHub -> **Actions -> Genshin market scan -> Run workflow**.

Danach:

```text
https://...workers.dev/health
https://...workers.dev/v1/candidates/recent?hours=24
https://...workers.dev/v1/quality/recent?hours=24
```

Der Collector laeuft automatisch **einmal pro Stunde** bei Minute 17.

---

## 5. Was der Collector und was ChatGPT macht

Collector:

- hohe Recall / breite Discovery
- Deduplizierung ueber URL/Listing-ID
- Kandidaten-Triage
- Detail-Recheck der wichtigsten Kandidaten
- Coverage + Quality-Metriken
- Speicherung von Snapshots und Kandidatenhistorie

ChatGPT / Human Review:

- unabhaengige Tiefenpruefung
- identity-bound Plausibilisierung
- Security-/Seller-Kontext
- Markt-/AVP-Auswertung
- Entscheidung, ob ein Fund wirklich das strenge Kronjuwel-Niveau erreicht

Der Collector allein loest keine Kaufentscheidung aus.

---

## 6. Quality Loop

Wichtige Endpunkte:

```text
GET /v1/review-queue?limit=50
GET /v1/coverage/recent?hours=24
GET /v1/quality/recent?hours=24
GET /v1/feedback/summary?days=30
```

Details:

[`QUALITY_LOOP.md`](QUALITY_LOOP.md)

Mit Feedback koennen echte Fehler gesammelt werden:

```powershell
.\scripts\submit_feedback.ps1 `
  -ListingUrl "https://..." `
  -Label "false_positive" `
  -Notes "Preis aus related listing gezogen" `
  -ApiUrl "https://...workers.dev"
```

Jeder reale Fehler sollte spaeter moeglichst zu einem Regressionstest werden.

---

## 7. Excel

D1 ist die Rohdatenquelle. Die bestehende Datei

`/Genshin Market Tracker/Genshin_Account_Market_Tracker(1).xlsx`

bleibt Analyse-/Ranking-Tracker und wird nur einmal taeglich gebuendelt aktualisiert.

---

## 8. Bereits laufende v0.1 Installation upgraden

Nicht erneut das komplette Setup starten.

Nutze:

[`V2_UPGRADE_DE.md`](V2_UPGRADE_DE.md)

Kurzfassung nach Commit/Push:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v2.ps1
```

Der bestehende API-Token bleibt erhalten.

---

## 9. Noch manuell zu kalibrieren

Eldorado und G2G bleiben zunaechst deaktiviert, bis ihre oeffentlichen Listing-Strukturen sauber getestet sind.

Nach mehreren v0.2 Runs beobachten wir besonders:

- Seller-Extraction pro Plattform
- Server-/Preis-Completeness
- Detail-Verification-Rate
- Zero-hit Query-Familien
- Parserfehler
- False Positives
- echte Misses

So wird die naechste Version aus gemessenen Schwachstellen gebaut, nicht aus Vermutungen.
