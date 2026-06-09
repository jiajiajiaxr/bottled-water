param(
  [string]$WebAppUrl = "http://127.0.0.1:5174"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$env:AGENTHUB_DESKTOP_WEB_URL = $WebAppUrl

Push-Location $root
try {
  if (-not (Test-Path "node_modules")) {
    npm install
  }
  npm run dev
}
finally {
  Pop-Location
}
