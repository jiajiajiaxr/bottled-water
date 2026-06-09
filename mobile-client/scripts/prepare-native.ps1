param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $root
try {
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required."
  }
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required."
  }

  if (-not $SkipInstall -and -not (Test-Path "node_modules")) {
    npm install
  }

  npm run pwa:installable

  if (-not (Test-Path "android")) {
    npx cap add android
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to create Android project."
    }
  }
  npx cap sync android
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to sync Android project."
  }

  Write-Host ""
  if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Host "Java was not found. Install JDK 17+ before building APK/AAB." -ForegroundColor Yellow
  }
  if (-not $env:ANDROID_HOME -and -not $env:ANDROID_SDK_ROOT) {
    Write-Host "ANDROID_HOME / ANDROID_SDK_ROOT is not set. Install Android Studio and SDK." -ForegroundColor Yellow
  }
  Write-Host "AgentHub Mobile native project is prepared." -ForegroundColor Green
  Write-Host "Next: npm run open:android"
}
finally {
  Pop-Location
}
