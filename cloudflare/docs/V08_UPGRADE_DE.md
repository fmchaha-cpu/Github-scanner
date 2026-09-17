# Upgrade auf v0.8

1. ZIP-Inhalt ueber das bestehende Repository kopieren. Den `.git`-Ordner **nicht** loeschen.
2. In GitHub Desktop committen und pushen.
3. PowerShell im Repository oeffnen:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v08.ps1
```

Das Deploy-Skript prueft danach selbst `/health` und akzeptiert nur Worker-Version `0.8`.

4. GitHub -> Actions -> **Import tracker historical seed** -> Run workflow.
   Der Workflow importiert/upsertet den Seed und prueft anschliessend `/v1/historical/stats`.
5. GitHub -> Actions -> **Genshin market scan** -> Run workflow.

Der Scan besitzt jetzt einen eigenen Worker-Kompatibilitaetscheck. Falls der Worker nicht v0.8 ist, bricht der Job mit einer klaren Meldung ab, bevor Chromium installiert wird.

## Woran wir den v0.8-Test messen

Besonders interessant sind:

- ZeusX `seller_pct`
- ZeusX `detail_verified_pct`, `identity_verified_pct`, `strict_live_pct`
- `blocked_pages` bei ZeusX/PlayerUp (sollten bei normalen Seiten nicht mehr durch Script-Texte falsch positiv sein)
- `historical_pool.total` und `historical_pool.sold_confirmed`
- `candidate_comparable_coverage_pct`
- `worker_api.compatible`
- `requests_avoided` / Circuit-Breaker-Laufzeit
