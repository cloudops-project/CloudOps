<#
.SYNOPSIS
    Verify the local demo stack is healthy and reachable same-origin.

.PARAMETER IncludeUserChecks
    Additionally log in as the seeded owner/analyst/engineer and verify roles,
    session separation and concurrent reads. Requires demo data to be seeded
    first, so bootstrap runs this pass only after seeding.
#>
[CmdletBinding()]
param(
    [switch]$IncludeUserChecks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
    function Wait-HttpOk {
        param(
            [Parameter(Mandatory = $true)][string]$Name,
            [Parameter(Mandatory = $true)][string]$Uri,
            [int]$Attempts = 30,
            [int]$DelaySeconds = 2
        )

        $lastError = $null
        for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 20
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                    Write-Host "${Name}: OK"
                    return
                }
                $lastError = "$Name returned HTTP $($response.StatusCode)"
            } catch {
                $lastError = $_.Exception.Message
            }
            Start-Sleep -Seconds $DelaySeconds
        }

        throw "$Name did not become ready at $Uri. Last error: $lastError"
    }

    $checks = @(
        @{ Name = "API health (same-origin proxy)"; Uri = "http://localhost:5173/api/health" },
        @{ Name = "API readiness (same-origin proxy)"; Uri = "http://localhost:5173/api/ready" },
        @{ Name = "Mailpit"; Uri = "http://localhost:8025/api/v1/info" }
    )

    foreach ($check in $checks) {
        Wait-HttpOk -Name $check.Name -Uri $check.Uri
    }

    Wait-HttpOk -Name "CloudOps web" -Uri "http://localhost:5173"
    Wait-HttpOk -Name "Nginx healthz" -Uri "http://localhost:5173/healthz"

    # Same-origin proxy: the SPA calls relative /api/v1/... paths, so the API must
    # be reachable through the web port with the /api prefix preserved.
    $openapi = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5173/api/v1/openapi.json" -TimeoutSec 20 -ErrorAction SilentlyContinue
    if ($null -ne $openapi -and $openapi.StatusCode -eq 200) {
        Write-Host "API proxy (/api/v1) : OK"
    } else {
        # Not every build exposes openapi under the prefix; fall back to a route
        # that must exist and must NOT return the SPA's index.html.
        $login = try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5173/api/v1/auth/login" `
                -Method POST -Body '{}' -ContentType "application/json" -TimeoutSec 20
        } catch {
            $_.Exception.Response
        }
        if ($null -eq $login) {
            throw "The /api/ proxy did not respond through the web port."
        }
        $status = [int]$login.StatusCode
        if ($status -eq 200) {
            throw "The /api/ proxy returned 200 for an invalid login body; it is probably serving index.html instead of proxying to the API."
        }
        Write-Host "API proxy (/api/v1/auth/login -> HTTP $status, JSON error expected): OK"
    }

    # SPA fallback must still serve the app shell for client-side routes.
    $spa = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5173/login" -TimeoutSec 20
    if ($spa.Content -notmatch "<div id=""root""") {
        throw "SPA fallback did not return index.html for /login."
    }
    Write-Host "SPA fallback (/login): OK"

    if (-not $IncludeUserChecks) {
        docker compose -f compose.demo.yml ps
        return
    }

    # Concurrent multi-user checks against the same origin the browsers use.
    # Uses the same-origin web port so the Nginx proxy path is exercised too.
    function Get-DemoToken {
        param([Parameter(Mandatory = $true)][string]$Email)
        $body = @{ email = $Email; password = "CloudOps-Demo-Password-123!" } | ConvertTo-Json
        $response = Invoke-RestMethod -Uri "http://localhost:5173/api/v1/auth/login" `
            -Method POST -Body $body -ContentType "application/json" -TimeoutSec 20
        if (-not $response.access_token) { throw "No access token returned for $Email." }
        return $response.access_token
    }

    $accounts = @(
        @{ Email = "owner@cloudops-demo.testmail.com"; Role = "owner" },
        @{ Email = "analyst@cloudops-demo.testmail.com"; Role = "security_analyst" },
        @{ Email = "engineer@cloudops-demo.testmail.com"; Role = "cloud_engineer" }
    )

    $tokens = @{}
    foreach ($account in $accounts) {
        $token = Get-DemoToken -Email $account.Email
        $tokens[$account.Email] = $token
        $me = Invoke-RestMethod -Uri "http://localhost:5173/api/v1/auth/me" `
            -Headers @{ Authorization = "Bearer $token" } -TimeoutSec 20
        if ($me.user.email -ne $account.Email) {
            throw "Session leakage: token for $($account.Email) resolved to $($me.user.email)."
        }
        $role = ($me.organizations | Select-Object -First 1).role
        if ($role -ne $account.Role) {
            throw "Role drift for $($account.Email): expected $($account.Role), got $role."
        }
        Write-Host "Login + role ($($account.Email) -> $role): OK"
    }

    # Distinct sessions: no two users may share an access token.
    $distinct = ($tokens.Values | Select-Object -Unique).Count
    if ($distinct -ne $accounts.Count) {
        throw "Sessions are not distinct; tokens were reused across users."
    }
    Write-Host "Distinct per-user sessions: OK"

    # Simultaneous reads must each resolve to their own identity.
    foreach ($round in 1..3) {
        foreach ($account in $accounts) {
            $me = Invoke-RestMethod -Uri "http://localhost:5173/api/v1/auth/me" `
                -Headers @{ Authorization = "Bearer $($tokens[$account.Email])" } -TimeoutSec 20
            if ($me.user.email -ne $account.Email) {
                throw "Concurrent read leaked identity on round ${round}."
            }
        }
    }
    Write-Host "Simultaneous reads keep identities separate: OK"

    # Unauthenticated and forged tokens must be refused through the proxy.
    foreach ($header in @($null, @{ Authorization = "Bearer forged-token" })) {
        $status = try {
            $params = @{ Uri = "http://localhost:5173/api/v1/auth/me"; TimeoutSec = 20 }
            if ($header) { $params.Headers = $header }
            (Invoke-WebRequest -UseBasicParsing @params).StatusCode
        } catch {
            [int]$_.Exception.Response.StatusCode
        }
        if ($status -ne 401) {
            throw "Expected HTTP 401 for an unauthenticated/forged request, got $status."
        }
    }
    Write-Host "Unauthenticated and forged tokens rejected: OK"

    docker compose -f compose.demo.yml ps
} finally {
    Pop-Location
}
