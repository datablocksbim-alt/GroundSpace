# GS-027 isolated ASUS candidate check; never restart the existing Ground Space server.
[CmdletBinding()]
param([switch]$StartPreview, [ValidateRange(1025,65535)][int]$Port = 8768)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$gitMarker = Join-Path $repo '.git'
if (-not (Test-Path -LiteralPath $gitMarker -PathType Leaf)) {
    throw 'Use a separate GS-027 detached Git worktree; never the live Ground Space checkout.'
}
$head = (@(& git -C $repo rev-parse HEAD) -join '').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Unable to read preview HEAD' }
$remote = (@(& git -C $repo rev-parse 'refs/remotes/origin/feature/gs-027-unified-agent-configuration') -join '').Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $remote) {
    throw 'Preview is not the fetched GS-027 feature branch. Fetch and update before testing.'
}
$dirty = @(& git -C $repo status --porcelain | Where-Object { $_ })
if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) {
    throw 'Preview checkout has uncommitted changes. No automated reset will be performed.'
}
if ($Port -in @(8765,8766,8767)) {
    throw 'Port is reserved for the live service or an existing preview.'
}

Push-Location $repo
try {
    Write-Host 'GS-027 portable agent/security preflight' -ForegroundColor Cyan
    & py -3 -m unittest tests.test_gs027_agent_configs tests.test_gs026_model_controls tests.test_gs025_public_security tests.test_gs023_collaboration tests.test_gs017_group_approvals -v
    if ($LASTEXITCODE -ne 0) { throw 'GS-027 Python regression tests failed' }
    & node --check web/public/app.js
    if ($LASTEXITCODE -ne 0) { throw 'GS-027 frontend syntax failed' }
    Write-Host 'GS-027 PREVIEW PRECHECK PASS. Existing Ground Space untouched.' -ForegroundColor Green
    if (-not $StartPreview) { return }

    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port already has a listener; no existing process will be stopped."
    }
    $previewState = Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace-GS027-Preview'
    $env:GROUND_SPACE_DEPLOYMENT_MODE = 'owner_private'
    $env:GROUND_SPACE_CODEX_WRITE_ENABLED = '0'
    $env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED = '0'
    foreach ($variable in @('GROUND_SPACE_TAILSCALE_ORIGIN','GROUND_SPACE_PUBLIC_USERS',
        'GROUND_SPACE_ENABLE_MULTI_USER','GROUND_SPACE_PUBLIC_HOSTING')) {
        Remove-Item ('Env:' + $variable) -ErrorAction SilentlyContinue
    }
    Write-Host "Desktop-only preview: http://127.0.0.1:$Port" -ForegroundColor Cyan
    Write-Host 'Do not point Tailscale at this preview. Ctrl+C stops only this preview.'
    & py -3 -m ground_space.webapp --port $Port --state-dir $previewState --no-browser
    if ($LASTEXITCODE -ne 0) { throw 'GS-027 preview exited with an error' }
}
finally {
    Pop-Location
}
