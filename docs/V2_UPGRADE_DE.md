# Upgrade auf v0.2 – Quality + Recall

Diese Version ist absichtlich rueckwaertskompatibel mit der bestehenden D1-Datenbank.

## 1. Dateien uebernehmen

Den v0.2-Patch in den Root-Ordner `Github-scanner` entpacken und vorhandene Dateien ersetzen.

GitHub Desktop sollte danach mehrere Aenderungen zeigen.

Commit-Vorschlag:

```text
Upgrade collector to v0.2 quality and recall
```

Dann **Push origin**.

## 2. CI pruefen

GitHub -> Actions -> **Quality checks**.

Erwartet:

- Python unit tests: gruen
- Worker TypeScript typecheck: gruen

Der normale Markt-Scan laeuft ab v0.2 einmal pro Stunde bei Minute 17.

## 3. Cloudflare Worker upgraden

Im Repo-Root PowerShell oeffnen:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v2.ps1
```

Das Skript:

1. stellt die neuen Quality-/Feedback-Tabellen sicher,
2. prueft TypeScript,
3. deployt den Worker.

Der bestehende `INGEST_TOKEN` wird **nicht** geaendert.

## 4. API testen

Danach im Browser:

```text
https://DEIN-WORKER.workers.dev/health
https://DEIN-WORKER.workers.dev/v1/quality/recent?hours=24
https://DEIN-WORKER.workers.dev/v1/review-queue?limit=20
```

## 5. Ersten v0.2 Scan starten

GitHub -> Actions -> **Genshin market scan** -> **Run workflow**.

Im Log sollte die Schlusszeile jetzt auch `identity=`, `strict_live=` und `review_gate=` enthalten.

## Wichtig

`review_gate` ist nur ein Signal fuer tiefe manuelle/ChatGPT-Pruefung. Kein Listing wird allein durch den Collector zu einem Kauf-/Kronjuwel-Alarm.
