$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$requiredFiles = @(
    '.env.example'
    'Makefile'
    'docker-compose.yml'
    'docs/ADR-000-starter-base.md'
    'evidence/m01-data-contract.json'
    '.github/workflows/cdrl-feedback.yml'
)

foreach ($required in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "missing required file: $required"
    }
}
if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw 'docker compose configuration is invalid'
    }
}

$payload = Get-Content -LiteralPath 'evidence/m01-data-contract.json' -Raw | ConvertFrom-Json
$requiredFields = @('assignmentId', 'commitSha', 'commands', 'results', 'assumptions', 'limitations')
$missing = @($requiredFields | Where-Object { $null -eq $payload.PSObject.Properties[$_] })
if ($missing.Count -gt 0) {
    throw "missing evidence fields: $($missing -join ', ')"
}

New-Item -ItemType Directory -Path 'artifacts' -Force | Out-Null
$result = [ordered]@{
    status        = 'starter_base_valid'
    scope         = 'structure_and_contract_only'
    nextMilestone = 'm01-data-contract'
}
$result | ConvertTo-Json | Set-Content -LiteralPath 'artifacts/base-verify.json' -Encoding utf8

Write-Output 'CDRL starter base verification passed'
