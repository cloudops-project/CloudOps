Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
    docker compose -f compose.demo.yml exec -T api python /app/scripts/demo_seed.py --reset --deliver-email
} finally {
    Pop-Location
}
