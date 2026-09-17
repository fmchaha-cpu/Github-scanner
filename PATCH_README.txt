Genshin Market Tracker v0.9.0 cumulative overlay

Copy the CONTENTS of this archive over the existing Github-scanner repository.
Do NOT delete the repository first and do NOT delete the hidden .git directory.

After commit + push:
  Set-ExecutionPolicy -Scope Process Bypass
  .\scripts\deploy_v09.ps1

Then start a fresh GitHub Actions -> Genshin market scan.
The v0.9 collector automatically imports/verifies the evidence-backed tracker historical seed if D1 is missing it.
