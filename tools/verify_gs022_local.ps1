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
        $bundledPlaywright = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright\index.mjs'
        $chromeCandidates = @(
            (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
            (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
            (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
        $setBundledModule = -not $env:GROUND_SPACE_PLAYWRIGHT_MODULE -and (Test-Path -LiteralPath $bundledPlaywright -PathType Leaf)
        $setSystemBrowser = -not $env:GROUND_SPACE_CHROMIUM_EXECUTABLE -and $chromeCandidates.Count -gt 0
        try {
            if ($setBundledModule) { $env:GROUND_SPACE_PLAYWRIGHT_MODULE = $bundledPlaywright }
            if ($setSystemBrowser) { $env:GROUND_SPACE_CHROMIUM_EXECUTABLE = $chromeCandidates[0] }
            node tools/test_gs015_browser.mjs
            if ($LASTEXITCODE -ne 0) { throw 'Ground Space browser QA failed.' }
        } finally {
            if ($setBundledModule) { Remove-Item Env:GROUND_SPACE_PLAYWRIGHT_MODULE -ErrorAction SilentlyContinue }
            if ($setSystemBrowser) { Remove-Item Env:GROUND_SPACE_CHROMIUM_EXECUTABLE -ErrorAction SilentlyContinue }
        }
    }
    Write-Host 'GS-022 LOCAL RELEASE GATE PASSED' -ForegroundColor Green
} finally {
    Pop-Location
}
