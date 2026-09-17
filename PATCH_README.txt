Genshin Market Tracker v0.7.0 cumulative overlay

Copy the CONTENTS of this package over the existing Github-scanner repository.
Do NOT delete the repository first and do NOT delete its hidden .git folder.
Replace existing files when Windows asks.

GitHub Desktop summary:
  Upgrade market tracker to v0.7.0

Description:
  Add source circuit breakers, persistent source-health cooldowns, field provenance, benchmark tests and historical comparable seeds.

Then deploy Cloudflare from the repository root:
  Set-ExecutionPolicy -Scope Process Bypass
  .\scripts\deploy_v07.ps1

After deployment, run the GitHub Action "Import tracker historical seed" once, then start a NEW "Genshin market scan" run.
