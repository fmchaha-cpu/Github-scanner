param(
  [Parameter(Mandatory=$true)]
  [string]$ListingUrl,

  [Parameter(Mandatory=$true)]
  [ValidateSet(
    "true_positive","false_positive","missed_candidate","bad_parse","good_parse",
    "wrong_price","wrong_server","wrong_seller","security_concern","duplicate"
  )]
  [string]$Label,

  [string]$Notes = "",

  [string]$ApiUrl = $env:MARKET_API_URL
)

$ErrorActionPreference = "Stop"

if (-not $ApiUrl) {
  $ApiUrl = Read-Host "MARKET_API_URL (z.B. https://genshin-market-api....workers.dev)"
}

$tokenPath = Join-Path $PSScriptRoot "..\.generated_ingest_token.txt"
if (-not (Test-Path $tokenPath)) {
  throw "Token-Datei fehlt: $tokenPath"
}

$token = (Get-Content $tokenPath -Raw).Trim()
$body = @{
  listing_url = $ListingUrl
  label = $Label
  reviewer = "manual"
  notes = $Notes
  detector_version = "v2.0"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri ($ApiUrl.TrimEnd("/") + "/v1/review-feedback") `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body $body

Write-Host "Feedback gespeichert: $Label" -ForegroundColor Green
