# Upgrade auf v0.6 – kurz und sicher

## 1. Dateien kopieren

Den Inhalt des v0.6-ZIPs ueber deinen bestehenden Ordner

```text
C:\Users\pietf\Documents\GitHub\Github-scanner
```

kopieren und **Dateien ersetzen** bestaetigen.

Den bestehenden Repo-Ordner vorher **nicht loeschen**. Dadurch bleiben `.git`, deine lokale `.generated_ingest_token.txt` und deine bestehende Cloudflare-Konfiguration erhalten.

## 2. GitHub Desktop

Commit-Vorschlag:

```text
Upgrade market tracker to v0.6.0
```

Dann **Commit to main -> Push origin**.

Unter GitHub Actions sollten die `Quality checks` gruen werden.

## 3. D1 migrieren + Worker deployen

PowerShell im Repo-Root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v06.ps1
```

Das Script:

1. stellt die bisherigen Quality-Tabellen sicher,
2. stellt Historical-/Comparable-Tabellen sicher,
3. legt die v0.6 Observability-/Verification-Tabellen an,
4. typecheckt den Worker,
5. deployt ihn.

Der bestehende `INGEST_TOKEN` und vorhandene D1-Daten werden nicht ersetzt.

## 4. Neuen Scan starten

GitHub -> Actions -> **Genshin market scan -> Run workflow**.

Wichtig: einen **neuen** Run starten, nicht einen alten Run per `Re-run jobs` wiederholen. Ein Re-run nutzt weiterhin den alten Commit.

## 5. Danach auswerten

Besonders relevant:

```text
/v1/quality/recent?hours=24
/v1/coverage/diagnostics?hours=24
/v1/verification/events?hours=24
/v1/quality/trends?limit=20
```

Anhand dieser Daten wird die naechste Parser-/Recall-Runde gezielt geplant.
