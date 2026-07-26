Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
    docker compose -f compose.demo.yml down
} finally {
    Pop-Location
}
