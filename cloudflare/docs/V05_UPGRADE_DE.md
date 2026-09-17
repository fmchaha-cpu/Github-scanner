# Upgrade auf v0.5 – kurz und sicher

## 1. Dateien ins bestehende Repo kopieren

Den Inhalt des v0.5-Ordners ueber deinen bestehenden `Github-scanner`-Ordner kopieren. Dateien ersetzen, aber den Ordner nicht vorher loeschen. Dadurch bleiben `.git` und `.generated_ingest_token.txt` erhalten.

## 2. GitHub Desktop

Aenderungen kontrollieren, dann Commit z. B.:

```text
Upgrade market tracker to v0.5 historical comparables
```

Danach **Push origin**.

## 3. Cloudflare/D1 migrieren und Worker deployen

PowerShell im Repo:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v05.ps1
```

Das Script:
1. stellt die v0.2 Quality-Tabelle sicher,
2. legt die v0.5 Historical-/Comparable-Tabellen an,
3. typecheckt den Worker,
4. deployt den Worker.

Der bestehende `INGEST_TOKEN` wird dabei nicht neu erzeugt.

## 4. Test

GitHub -> Actions -> **Quality checks**. Python-Tests und Worker-Typecheck muessen gruen sein.

Danach **Genshin market scan -> Run workflow**.

Im Browser pruefen:

```text
https://genshin-market-api.piet-genshin-market-260917.workers.dev/health
https://genshin-market-api.piet-genshin-market-260917.workers.dev/v1/quality/recent?hours=24
https://genshin-market-api.piet-genshin-market-260917.workers.dev/v1/historical/recent?limit=20
```

## 5. Historische Anker importieren

Historische Datensaetze bleiben getrennt von Live-Listings. Beispiel `historical.json`:

```json
[
  {
    "source_key": "workbook:HIST-W-008",
    "provenance": "existing_tracker_verified_history",
    "title": "Historical EU account",
    "server": "EU",
    "price_value": 50,
    "currency": "USD",
    "market_status": "SOLD_CONFIRMED",
    "status_confidence": 0.9,
    "status_evidence": "verified historical sold/closed listing",
    "observed_at": "2026-09-01T12:00:00Z",
    "limited_c6_count": 0,
    "c6r1_count": 0,
    "risk_hits": 0
  }
]
```

Import:

```powershell
.\scripts\import_historical.ps1 `
  -ApiUrl "https://genshin-market-api.piet-genshin-market-260917.workers.dev" `
  -JsonPath ".\historical.json"
```

Bei alten Daten gilt: lieber `OUTCOME_UNKNOWN` oder `SOLD_CLAIMED` als einen nicht belegten Verkauf zu `SOLD_CONFIRMED` aufzuwerten.

## 6. Vergleich fuer einen aktuellen Kandidaten

```text
/v1/comparables?url=<URL-ENCODED-LISTING>&limit=30
```

Die Antwort trennt:
- historische Vergleichsanker,
- aktuelle Asking-Price-Vergleiche,
- Weighted Median + robuste Streuung,
- Daten-/Vergleichs-Confidence,
- Duplicate-Deduplizierung,
- Recency-Gewichtung.
