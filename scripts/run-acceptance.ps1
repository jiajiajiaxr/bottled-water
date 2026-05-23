param(
  [string]$ApiBaseUrl = $env:AGENTHUB_API_BASE_URL,
  [string]$WebBaseUrl = $env:AGENTHUB_E2E_BASE_URL
)

$ErrorActionPreference = "Stop"

if ($ApiBaseUrl) {
  python -m pytest tests --live-base-url $ApiBaseUrl
} else {
  python -m pytest tests
}

if (Test-Path "frontend/package.json") {
  Push-Location frontend
  try {
    npm test -- --run
  } finally {
    Pop-Location
  }
}

if ($WebBaseUrl) {
  Push-Location e2e
  try {
    npx playwright test --config playwright.config.ts
  } finally {
    Pop-Location
  }
}
