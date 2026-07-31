[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Command,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "PRECHECK_PYTHON_UNAVAILABLE: Python 3.12+ is required. Install Python and rerun."
    exit 2
}

$previousErrorPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $python.Source "$root\scripts\selfhost\cloudops.py" $Command @RemainingArguments
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorPreference
exit $exitCode
