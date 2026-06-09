param(
  [int]$Port = 5190,
  [string]$ApiBase = "http://127.0.0.1:8000/api/v1"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:VITE_AGENTHUB_API_BASE = $ApiBase

Push-Location $root
try {
  if (-not (Test-Path "node_modules")) {
    npm install
  }
  npm run dev -- --port $Port
}
finally {
  Pop-Location
}
