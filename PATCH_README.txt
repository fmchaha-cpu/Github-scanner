Genshin Market Tracker v0.6.0 cumulative overlay

Copy all files in this archive over the existing Github-scanner repository and replace existing files.
Do NOT delete the repository first; keep .git and .generated_ingest_token.txt.

GitHub Desktop summary:
  Upgrade market tracker to v0.6.0

After push, run in PowerShell from the repo root:
  Set-ExecutionPolicy -Scope Process Bypass
  .\scripts\deploy_v06.ps1

Then start a NEW Genshin market scan workflow run.
