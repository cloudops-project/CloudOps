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
        @{ Name = "API health"; Uri = "http://localhost:8000/health" },
        @{ Name = "API readiness"; Uri = "http://localhost:8000/ready" },
        @{ Name = "Mailpit"; Uri = "http://localhost:8025/api/v1/info" }
    )

    foreach ($check in $checks) {
        Wait-HttpOk -Name $check.Name -Uri $check.Uri
    }

    Wait-HttpOk -Name "CloudOps web" -Uri "http://localhost:5173"

    docker compose -f compose.demo.yml ps
} finally {
    Pop-Location
}
