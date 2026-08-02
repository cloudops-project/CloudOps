param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
python (Join-Path $RepositoryRoot "scripts/aws_sandbox.py") @Arguments
exit $LASTEXITCODE
