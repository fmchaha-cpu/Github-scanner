$ErrorActionPreference = "Stop"
Write-Host "=== Genshin Market Infra: v0.2 Upgrade ===" -ForegroundColor Cyan

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm fehlt. Installiere zuerst Node.js LTS."
}

Set-Location "$PSScriptRoot\..\cloudflare"
npm install

Write-Host "`n1) Quality/Feedback-Tabellen sicherstellen..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./migrations/0002_quality_feedback.sql

Write-Host "`n2) TypeScript pruefen..." -ForegroundColor Yellow
npm run typecheck

Write-Host "`n3) Worker deployen..." -ForegroundColor Yellow
npx wrangler deploy

Write-Host "`nFERTIG. Teste danach /health und /v1/quality/recent?hours=24" -ForegroundColor Green
