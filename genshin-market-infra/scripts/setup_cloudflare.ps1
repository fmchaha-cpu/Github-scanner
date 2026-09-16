$ErrorActionPreference = "Stop"
Write-Host "=== Genshin Market Infra: Cloudflare setup ===" -ForegroundColor Cyan

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm fehlt. Installiere zuerst Node.js LTS von nodejs.org."
}

Set-Location "$PSScriptRoot\..\cloudflare"
npm install

Write-Host "`n1) Cloudflare Login wird im Browser geoeffnet..." -ForegroundColor Yellow
npx wrangler login

Write-Host "`n2) D1 Datenbank anlegen..." -ForegroundColor Yellow
Write-Host "Falls die Datenbank schon existiert, brich diesen Schritt mit Ctrl+C ab und nutze die bestehende ID."
npx wrangler d1 create genshin-market

Write-Host "`nWICHTIG: Kopiere die ausgegebene database_id in cloudflare/wrangler.toml anstelle von REPLACE_WITH_D1_DATABASE_ID." -ForegroundColor Magenta
Read-Host "Druecke Enter, nachdem du wrangler.toml gespeichert hast"

Write-Host "`n3) Schema einspielen..." -ForegroundColor Yellow
npx wrangler d1 execute genshin-market --remote --file=./schema.sql

$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$token = [Convert]::ToHexString($bytes).ToLower()
$token | Set-Content -NoNewline "$PSScriptRoot\..\.generated_ingest_token.txt"

Write-Host "`n4) Schreib-Token als Worker Secret setzen..." -ForegroundColor Yellow
$token | npx wrangler secret put INGEST_TOKEN

Write-Host "`n5) Worker deployen..." -ForegroundColor Yellow
npx wrangler deploy

Write-Host "`nFERTIG." -ForegroundColor Green
Write-Host "Notiere die workers.dev URL aus der Ausgabe."
Write-Host "Dein MARKET_API_TOKEN liegt lokal in .generated_ingest_token.txt. Diese Datei NIEMALS committen."
