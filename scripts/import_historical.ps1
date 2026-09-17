param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [Parameter(Mandatory=$true)][string]$JsonPath
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$TokenPath = Join-Path $Root ".generated_ingest_token.txt"
if (-not (Test-Path $TokenPath)) { throw "Token file not found: $TokenPath" }
if (-not (Test-Path $JsonPath)) { throw "JSON file not found: $JsonPath" }

$token = (Get-Content $TokenPath -Raw).Trim()
$records = Get-Content $JsonPath -Raw | ConvertFrom-Json
if ($records.records) { $records = $records.records }
$body = @{ records = @($records) } | ConvertTo-Json -Depth 12
$headers = @{ Authorization = "Bearer $token" }
$result = Invoke-RestMethod -Method Post -Uri ($ApiUrl.TrimEnd('/') + '/v1/historical/import') -Headers $headers -ContentType 'application/json' -Body $body
$result | ConvertTo-Json -Depth 8
