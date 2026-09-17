param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [int]$Hours = 24
)
$ErrorActionPreference = "Stop"
$url = $ApiUrl.TrimEnd('/') + "/v1/quality/recent?hours=$Hours"
$data = Invoke-RestMethod -Method Get -Uri $url
Write-Host "=== Market Quality ($Hours h) ===" -ForegroundColor Cyan
Write-Host "Listings: $($data.completeness.n)"
Write-Host "Price: $($data.completeness.price_pct)% | Server: $($data.completeness.server_pct)% | Seller: $($data.completeness.seller_pct)%"
Write-Host "Identity verified: $($data.completeness.identity_verified_pct)% | Strict live: $($data.completeness.strict_live_pct)%"
Write-Host "Historical pool: $($data.historical_pool.n) | Sold confirmed: $($data.historical_pool.sold_confirmed)"
Write-Host "Probable duplicate groups: $($data.probable_duplicate_groups)"
Write-Host ""
Write-Host "Suggestions:" -ForegroundColor Yellow
foreach ($s in $data.suggestions) {
  Write-Host "[$($s.priority)] $($s.code): $($s.message)"
}
