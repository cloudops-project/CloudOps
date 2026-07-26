Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
    docker compose -f compose.demo.yml config | Out-Null
    docker compose -f compose.demo.yml build
    docker compose -f compose.demo.yml up -d
    docker compose -f compose.demo.yml ps
    & "$PSScriptRoot\demo_check.ps1"
} finally {
    Pop-Location
}
