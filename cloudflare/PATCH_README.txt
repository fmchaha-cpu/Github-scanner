Genshin Market Tracker v0.8.0 cumulative overlay

Copy the CONTENTS of this archive over the existing Github-scanner repository.
Do NOT delete the repository first and do NOT delete the hidden .git directory.

After commit + push:
  Set-ExecutionPolicy -Scope Process Bypass
  .\scripts\deploy_v08.ps1

Then in GitHub Actions:
  1) Import tracker historical seed
  2) Genshin market scan

The scan now refuses to run against an outdated Worker, so a missing deploy is obvious instead of silently degrading diagnostics.
