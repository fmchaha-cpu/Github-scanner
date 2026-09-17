$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\cloudflare"

Write-Host "=== Genshin Market Tracker v0.5 deploy ===" -ForegroundColor Cyan
Write-Host "1) Applying v0.2 quality tables (safe if already present)..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0002_quality_feedback.sql

Write-Host "2) Applying v0.5 historical/comparable tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0003_historical_comparables.sql

Write-Host "3) Type checking Worker..." -ForegroundColor Yellow
npm install
npm run typecheck

Write-Host "4) Deploying Worker..." -ForegroundColor Yellow
npx wrangler deploy

Write-Host "v0.5 deployed. Existing D1 data and INGEST_TOKEN remain in place." -ForegroundColor Green
