# Upgrade auf v0.7.0

1. Den Inhalt der v0.7-ZIP ueber den vorhandenen `Github-scanner`-Ordner kopieren. Den `.git`-Ordner **nicht loeschen**.
2. GitHub Desktop:
   - Summary: `Upgrade market tracker to v0.7.0`
   - Description: `Add source circuit breakers, persistent source-health cooldowns, field provenance, benchmark tests and historical comparable seeds.`
   - Commit + Push.
3. PowerShell im Repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v07.ps1
```

4. GitHub -> Actions -> **Import tracker historical seed** -> `Run workflow` einmal ausfuehren. Der Import ist idempotent (`source_key` wird upserted).
5. Danach **Genshin market scan** als neuen Run starten.

## Danach pruefen

- `/v1/source-health`
- `/v1/quality/recent?hours=24`
- `/v1/quality/by-version?limit=50`
- `/v1/coverage/diagnostics?hours=24`
- `/v1/verification/events?hours=24`

Beim ersten v0.7-Run kann eine blockierte Quelle noch einmal getestet werden. Nach wiederholtem bestaetigten Block wird sie temporaer gekuehlt und spaeter automatisch erneut sondiert.
