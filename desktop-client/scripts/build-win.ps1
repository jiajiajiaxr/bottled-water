param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $root
try {
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required to build AgentHub Desktop."
  }
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required to build AgentHub Desktop."
  }

  if (-not $SkipInstall -and -not (Test-Path "node_modules")) {
    npm install
  }

  npm run check
  npm run pack:win

  Write-Host ""
  Write-Host "AgentHub Desktop build completed." -ForegroundColor Green
  Get-ChildItem -Path "release" -Recurse -File |
    Where-Object { $_.Extension -in ".exe", ".msi", ".zip" } |
    Select-Object FullName, Length
}
finally {
  Pop-Location
}
