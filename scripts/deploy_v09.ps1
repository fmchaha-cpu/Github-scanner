$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\cloudflare"

Write-Host "=== Genshin Market Tracker v0.9 deploy ===" -ForegroundColor Cyan
Write-Host "1) Ensuring v0.2 quality tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0002_quality_feedback.sql

Write-Host "2) Ensuring v0.5 historical/comparable tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0003_historical_comparables.sql

Write-Host "3) Ensuring v0.6 observability tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0004_observability.sql

Write-Host "4) Ensuring v0.7 source-health/provenance tables..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0005_source_health_provenance.sql

Write-Host "5) Type checking Worker..." -ForegroundColor Yellow
npm install
npm run typecheck

Write-Host "6) Deploying Worker v0.9..." -ForegroundColor Yellow
npx wrangler deploy

Write-Host "7) Verifying deployed Worker..." -ForegroundColor Yellow
$ApiBase = $env:MARKET_API_URL
if ([string]::IsNullOrWhiteSpace($ApiBase)) {
    $ApiBase = "https://genshin-market-api.piet-genshin-market-260917.workers.dev"
}
$HealthUrl = $ApiBase.TrimEnd('/') + "/health"
$Health = $null
for ($i = 1; $i -le 5; $i++) {
    try {
        $Health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 20
        if ($Health.version -eq "0.9") { break }
    } catch {
        if ($i -eq 5) { throw }
    }
    Start-Sleep -Seconds 2
}
if ($null -eq $Health -or $Health.version -ne "0.9") {
    $Got = if ($null -eq $Health) { "no response" } else { [string]$Health.version }
    throw "Worker verification failed. Expected version 0.9, got: $Got"
}
Write-Host ("Worker v0.9 confirmed. Historical records currently visible: " + $Health.historical_count) -ForegroundColor Green
Write-Host "v0.9 deployed. Existing D1 data and INGEST_TOKEN remain unchanged." -ForegroundColor Green
Write-Host "Next: start a fresh Genshin market scan. v0.9 will auto-import the tracker historical seed if D1 is missing it." -ForegroundColor Green
