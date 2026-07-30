<#
.SYNOPSIS
    One command to build, start, migrate, seed and verify the local CloudOps demo.

.DESCRIPTION
    Wraps the individual demo helpers so a presenter needs a single command.
    Every step fails loudly; nothing is silently skipped.

    Safety: the demo stack pins APP_ENV=development and a cloudops_demo database.
    demo_seed.py independently refuses to run against staging/production or any
    database outside cloudops_demo*, so a mistargeted DATABASE_URL cannot be
    seeded or truncated by this script.

.PARAMETER Reset
    Truncate and reseed the demo database. Required when demo data already
    exists, because the seed is not additive.

.PARAMETER SkipBuild
    Reuse existing images instead of rebuilding.

.PARAMETER Tunnel
    After the stack is healthy and seeded, start a Cloudflare Quick Tunnel and
    print the temporary public URL. Requires no Cloudflare account or token.

.EXAMPLE
    .\scripts\demo_bootstrap.ps1 -Reset

.EXAMPLE
    .\scripts\demo_bootstrap.ps1 -Reset -Tunnel
#>
[CmdletBinding()]
param(
    [switch]$Reset,
    [switch]$SkipBuild,
    [switch]$Tunnel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
    Write-Host "==> Validating Compose configuration" -ForegroundColor Cyan
    docker compose -f compose.demo.yml config | Out-Null

    if (-not $SkipBuild) {
        Write-Host "==> Building demo images" -ForegroundColor Cyan
        docker compose -f compose.demo.yml build
    }

    Write-Host "==> Starting demo stack" -ForegroundColor Cyan
    # No --profile flag needed: scheduler-worker and job-worker start by default.
    docker compose -f compose.demo.yml up -d

    Write-Host "==> Waiting for services to become healthy" -ForegroundColor Cyan
    # The api service applies `alembic upgrade head` before uvicorn starts, so a
    # healthy API means migrations already succeeded.
    & "$PSScriptRoot\demo_check.ps1"

    Write-Host "==> Seeding synthetic demo data" -ForegroundColor Cyan
    $seedArgs = @("--deliver-email")
    if ($Reset) { $seedArgs = @("--reset") + $seedArgs }
    docker compose -f compose.demo.yml exec -T api python /app/scripts/demo_seed.py @seedArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Demo seeding failed (exit code $LASTEXITCODE). If it reported existing demo data, re-run with -Reset."
    }

    Write-Host "==> Verifying concurrent multi-user access and roles" -ForegroundColor Cyan
    & "$PSScriptRoot\demo_check.ps1" -IncludeUserChecks

    Write-Host "==> Confirming demo workers are running" -ForegroundColor Cyan
    foreach ($service in @("scheduler-worker", "job-worker")) {
        $state = (docker compose -f compose.demo.yml ps --format "{{.Service}} {{.State}}" |
            Select-String -SimpleMatch $service | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($state)) {
            throw "$service is not running; 'Run now' would never leave PENDING."
        }
        Write-Host "$service : $state"
    }

    Write-Host ""
    Write-Host "CloudOps demo is ready." -ForegroundColor Green
    Write-Host "--------------------------------------------------"
    Write-Host "Dashboard : http://localhost:5173"
    Write-Host "Mailpit   : http://localhost:8025"
    Write-Host "API health: http://localhost:5173/api/health"
    Write-Host ""
    Write-Host "Synthetic demo credentials (NOT production defaults):"
    Write-Host "  owner    : owner@cloudops-demo.testmail.com"
    Write-Host "  analyst  : analyst@cloudops-demo.testmail.com"
    Write-Host "  engineer : engineer@cloudops-demo.testmail.com"
    Write-Host "  password : CloudOps-Demo-Password-123!"
    Write-Host "--------------------------------------------------"
    Write-Host "Logs:"
    Write-Host "  docker compose -f compose.demo.yml logs --tail=100 api"
    Write-Host "  docker compose -f compose.demo.yml logs --tail=100 web"
    Write-Host "  docker compose -f compose.demo.yml logs --tail=100 scheduler-worker"
    Write-Host "  docker compose -f compose.demo.yml logs --tail=100 job-worker"
    Write-Host "Stop: docker compose -f compose.demo.yml down"

    if ($Tunnel) {
        Write-Host ""
        & "$PSScriptRoot\demo_tunnel.ps1"
    } else {
        Write-Host ""
        Write-Host "Local only. For temporary public access run:"
        Write-Host "  .\scripts\demo_tunnel.ps1"
    }
} finally {
    Pop-Location
}
