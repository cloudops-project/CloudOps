<#
.SYNOPSIS
    Start a Cloudflare Quick Tunnel to the demo web service and print the URL.

.DESCRIPTION
    Starts the `cloudflared` Compose service (profile `tunnel`), waits for the
    random *.trycloudflare.com hostname to appear in its logs, prints it with the
    invitation instructions, then streams the tunnel log in the foreground so the
    tunnel stays up.

    Quick Tunnel requires no Cloudflare account, API token, or credentials.

    The URL is temporary: it is random, it changes every time the tunnel
    restarts, and it stops working the moment cloudflared exits. Nothing in the
    application depends on it -- the frontend calls relative /api/v1 paths and the
    API recognises the tunnel origin as same-origin, so a new URL needs no code
    edit, image rebuild, CORS change, or API restart.

.PARAMETER Restart
    Recreate the tunnel to obtain a fresh URL.

.PARAMETER NoFollow
    Print the URL and exit instead of streaming logs. The tunnel keeps running
    in the background.

.EXAMPLE
    .\scripts\demo_tunnel.ps1
#>
[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$NoFollow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$compose = @("-f", "compose.demo.yml", "--profile", "tunnel")

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
    # The tunnel is useless without a reachable web service.
    $webState = (docker compose -f compose.demo.yml ps --format "{{.Service}} {{.State}}" |
        Select-String -SimpleMatch "web" | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($webState)) {
        throw "The 'web' service is not running. Start the demo first: .\scripts\demo_bootstrap.ps1 -Reset"
    }

    if ($Restart) {
        Write-Host "==> Recreating the tunnel for a fresh URL" -ForegroundColor Cyan
        docker compose @compose rm -sf cloudflared | Out-Null
    }

    Write-Host "==> Starting Cloudflare Quick Tunnel" -ForegroundColor Cyan
    docker compose @compose up -d cloudflared

    Write-Host "==> Waiting for the public URL" -ForegroundColor Cyan
    $publicUrl = $null
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        $logs = docker compose @compose logs --no-color cloudflared 2>&1 | Out-String
        $match = [regex]::Match($logs, "https://[a-z0-9-]+\.trycloudflare\.com")
        if ($match.Success) {
            $publicUrl = $match.Value
            break
        }
        if ($logs -match "failed to (request|connect)") {
            throw "cloudflared reported a connection failure. Inspect: docker compose $($compose -join ' ') logs cloudflared"
        }
        Start-Sleep -Seconds 2
    }

    if (-not $publicUrl) {
        throw "Timed out waiting for a trycloudflare.com URL. Inspect: docker compose $($compose -join ' ') logs cloudflared"
    }

    Write-Host ""
    Write-Host "Demo is publicly reachable." -ForegroundColor Green
    Write-Host "--------------------------------------------------"
    Write-Host "Public URL : $publicUrl" -ForegroundColor Yellow
    Write-Host "Login page : $publicUrl/login"
    Write-Host "Mailpit    : http://localhost:8025  (local only, NOT tunnelled)"
    Write-Host "--------------------------------------------------"
    Write-Host "TEMPORARY URL -- READ THIS" -ForegroundColor Yellow
    Write-Host "  * Random hostname, assigned by Cloudflare."
    Write-Host "  * It CHANGES every time the tunnel restarts."
    Write-Host "  * It STOPS WORKING as soon as cloudflared exits."
    Write-Host "  * No uptime guarantee. Demo use only."
    Write-Host "  * Do not send sensitive or production data through it."
    Write-Host "  * Share it only with intended demo participants."
    Write-Host "  * To get a new URL:  .\scripts\demo_tunnel.ps1 -Restart"
    Write-Host "    No rebuild, CORS edit, or API restart is needed."
    Write-Host "--------------------------------------------------"
    Write-Host "Inviting additional demo members:"
    Write-Host "  1. Sign in at $publicUrl as owner@cloudops-demo.testmail.com"
    Write-Host "  2. Members -> Invite, enter the guest's email, choose a CloudOps"
    Write-Host "     application role (admin / security_analyst / cloud_engineer /"
    Write-Host "     auditor / viewer)."
    Write-Host "  3. Copy the invitation link shown on screen (built from this URL"
    Write-Host "     plus the invitation token) and send it to the guest directly."
    Write-Host "     It also appears in Mailpit (http://localhost:8025) as a backup."
    Write-Host "  4. The guest opens that link in their OWN browser, registers/accepts,"
    Write-Host "     and logs in separately. Sessions are per-browser; nobody inherits"
    Write-Host "     another user's session or organization."
    Write-Host ""
    Write-Host "  A CloudOps application role is NOT an AWS IAM permission. Inviting"
    Write-Host "  someone grants no access whatsoever to any AWS account."
    Write-Host "--------------------------------------------------"

    if ($NoFollow) {
        Write-Host "Tunnel is running in the background. Stop it with:"
        Write-Host "  docker compose -f compose.demo.yml --profile tunnel stop cloudflared"
        return
    }

    Write-Host "Streaming tunnel logs. Ctrl+C stops following (the tunnel keeps running)."
    Write-Host "To stop the tunnel entirely:"
    Write-Host "  docker compose -f compose.demo.yml --profile tunnel stop cloudflared"
    Write-Host ""
    docker compose @compose logs -f cloudflared
} finally {
    Pop-Location
}
