# GS-011: optional offline candidate gate; never imports Qwen code on Windows.
[CmdletBinding()]
param(
    [string]$CandidatePath = "",
    [switch]$FullSuite
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    Write-Host "[GS-011] Running trusted scheduler and validator unit tests"
    & py -3 -m unittest tests.test_gs011_scheduler tests.test_gs011_validation -v
    if ($LASTEXITCODE -ne 0) { throw "Trusted GS-011 tests failed." }

    if ($CandidatePath) {
        $source = (Resolve-Path -LiteralPath $CandidatePath -ErrorAction Stop).Path
        Write-Host "[GS-011] Candidate evaluation requested. Host Python will NOT execute candidate."
        & py -3 -m ground_space.proposal_validation "$source"
        if ($LASTEXITCODE -eq 2) { throw "Candidate BLOCKED. Docker sandbox unavailable; no unsafe fallback." }
        if ($LASTEXITCODE -ne 0) { throw "Candidate FAILED independent acceptance tests." }
        Write-Host "[GS-011] Candidate PASSED independent acceptance tests in container."
    }
    else {
        Write-Host "[GS-011] Candidate execution skipped (no -CandidatePath supplied)."
    }

    if ($FullSuite) {
        Write-Host "[GS-011] Full Ground Space tests requested"
        & py -3 -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw "Full Ground Space test suite failed." }
    }
    Write-Host "[GS-011] Finished; no project-write authority enabled."
}
finally {
    Pop-Location
}
