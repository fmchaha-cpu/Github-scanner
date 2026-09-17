# Upgrade auf v0.9.0

1. ZIP entpacken und **nur den Inhalt** ueber das bestehende `Github-scanner` Repository kopieren. `.git` nicht loeschen.
2. In GitHub Desktop committen und pushen.
3. PowerShell im Repository starten:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\deploy_v09.ps1
```

4. Danach einen neuen **Genshin market scan** starten.

Der Historical-Seed muss ab v0.9 nicht mehr zwingend separat gestartet werden. Der Collector prueft den persistenten D1-Pool vor dem Scan und importiert den idempotenten Tracker-Seed automatisch, wenn er fehlt.

Empfohlener Commit:

- Summary: `Upgrade market tracker to v0.9.0`
- Description: `Preserve PlayerAuctions card evidence, improve server and seller hydration, deepen merit verification and auto-repair historical seeds.`
