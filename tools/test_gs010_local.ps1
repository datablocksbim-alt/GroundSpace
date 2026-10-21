# Safe, read-only developer checks for GS-010.
# Run from Windows PowerShell after checking out the draft branch.
# Nothing in this script starts Ollama, calls a paid API, or changes project files.
[CmdletBinding()]
param(
    [switch]$FullSuite
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot

try {
    Write-Host "[GS-010] Repository: $repoRoot"
    Write-Host "[1/4] Testing local Coordinator routing and GS-008 goal planning"
    & py -3 -m unittest tests.test_gs010_coordinator tests.test_gs008_planning -v
    if ($LASTEXITCODE -ne 0) {
        throw "Coordinator/planning regression tests failed. Stop before merging."
    }

    Write-Host "[2/4] Checking JavaScript syntax"
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($null -ne $node) {
        & node --check web/public/app.js
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend syntax test failed. Stop before merging."
        }
    }
    else {
        Write-Warning "Node.js not installed; frontend syntax test skipped (CI checks this)."
    }

    Write-Host "[3/4] Checking linked Administrator queue"
    $adminRoot = if ($env:DATABLOCKS_ADMIN_ROOT) {
        $env:DATABLOCKS_ADMIN_ROOT
    }
    else {
        'D:\000_AI Project\AI Agents Datablocks'
    }
    $queuePath = Join-Path $adminRoot "orchestrator\task_queue.py"
    $queueAvailable = Test-Path -LiteralPath $queuePath -PathType Leaf
    if ($queueAvailable) {
        Write-Host "Administrator queue found: $queuePath"
    }
    else {
        Write-Warning "Administrator queue not found at $queuePath. Full suite cannot run here."
    }

    if ($FullSuite) {
        if (-not $queueAvailable) {
            throw "FullSuite requires the existing Administrator queue. No substitute queue will be installed."
        }
        Write-Host "[3b] Running the entire test suite against the linked Administrator queue"
        & py -3 -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) {
            throw "Full Windows test suite failed. Review output before release."
        }
    }
    else {
        Write-Host "Full suite not requested. Re-run with -FullSuite when the Administrator queue is available."
    }

    Write-Host "[4/4] Probing LOCAL Ollama installation (no generation requests)"
    try {
        $catalog = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 4
        $models = @($catalog.models | ForEach-Object { $_.name })
        if ($models.Count -eq 0) {
            Write-Warning "Ollama is responding, but it reports no installed models."
        }
        else {
            Write-Host "Installed Ollama models: $($models -join ', ')"
        }
    }
    catch {
        Write-Warning "No responding Ollama server on 127.0.0.1:11434; live chat still needs a separate test."
    }

    Write-Host "Checks finished. The real browser conversation QA is NOT verified by this script."
    Write-Host "See docs/GS-010.md for live conversation checks."
}
finally {
    Pop-Location
}
