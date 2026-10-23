[CmdletBinding()] param([switch]$Browser)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$adminRoot='D:\000_AI Project\AI Agents Datablocks'
$taskQueue=Join-Path $adminRoot 'orchestrator\task_queue.py'
if (-not (Test-Path -LiteralPath $taskQueue)) {
    throw "GS-022 full integration suite needs the ASUS-only Data Blocks Administrator runtime at $taskQueue"
}
Push-Location $repo
try {
    Write-Host '=== Entire Ground Space Python test suite including local Administrator ==='
    py -3 -m unittest discover -s tests -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'GS-022 full local test suite failed; do not mark ready or merge.' }
    Write-Host '=== JavaScript syntax ==='
    node --check web/public/app.js
    if ($LASTEXITCODE -ne 0) { throw 'Ground Space frontend parse check failed.' }
    if ($Browser) {
        Write-Host '=== Browser tests require Playwright on this developer machine ==='
        node tools/test_gs015_browser.mjs
        if ($LASTEXITCODE -ne 0) { throw 'Ground Space browser QA failed.' }
    }
    Write-Host 'GS-022 LOCAL RELEASE GATE PASSED' -ForegroundColor Green
} finally {
    Pop-Location
}
