param(
  [int]$Port = 4188,
  [string]$HostName = "127.0.0.1",
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:AGENTHUB_DEMO_HOST = $HostName
$env:AGENTHUB_DEMO_PORT = "$Port"

Write-Host "AgentHub platform demo starting..." -ForegroundColor Cyan
Write-Host "Static files: $root\public"
Write-Host "URL         : http://$HostName`:$Port"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js is required for local API mode. For static mode, publish platform-demo/public directly."
}

if (-not $NoOpen) {
  Start-Job -ScriptBlock {
    param($Url)
    Start-Sleep -Seconds 2
    Start-Process $Url
  } -ArgumentList "http://$HostName`:$Port" | Out-Null
}

Push-Location $root
try {
  node server.mjs
}
finally {
  Pop-Location
}
