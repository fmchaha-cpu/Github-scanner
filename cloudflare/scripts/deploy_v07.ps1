$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\cloudflare"

Write-Host "=== Genshin Market Tracker v0.7 deploy ===" -ForegroundColor Cyan
Write-Host "1) Ensuring v0.2 quality tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0002_quality_feedback.sql

Write-Host "2) Ensuring v0.5 historical/comparable tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0003_historical_comparables.sql

Write-Host "3) Ensuring v0.6 observability tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0004_observability.sql

Write-Host "4) Applying v0.7 source-health/provenance tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0005_source_health_provenance.sql

Write-Host "5) Type checking Worker..." -ForegroundColor Yellow
npm install
npm run typecheck

Write-Host "6) Deploying Worker..." -ForegroundColor Yellow
npx wrangler deploy

Write-Host "v0.7 deployed. Existing D1 data and INGEST_TOKEN remain unchanged." -ForegroundColor Green
Write-Host "After pushing to GitHub, run 'Import tracker historical seed' once, then start a fresh market scan." -ForegroundColor Green
