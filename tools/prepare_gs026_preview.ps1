# GS-026 safe preview verification. Does not touch GS-025 or Tailscale Serve.
[CmdletBinding()]
param(
    [switch]$StartPreview,
    [ValidateRange(1025, 65535)][int]$Port = 8766
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$expectedBranch = 'origin/feature/gs-026-mobile-agent-model-controls'
$gitMarker = Join-Path $repo '.git'

# Git worktrees have a .git *file*. The primary checkout has a .git directory.
if (-not (Test-Path -LiteralPath $gitMarker -PathType Leaf)) {
    throw 'For safety this script runs only from a separate GS-026 Git worktree, not the GS-025 primary checkout.'
}
$current = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Git HEAD could not be checked.' }
$expected = (& git -C $repo rev-parse $expectedBranch).Trim()
if ($LASTEXITCODE -ne 0 -or -not $expected -or $current -ne $expected) {
    throw 'Preview checkout differs from the fetched GS-026 branch. Do not run an unverified revision.'
}
if ($Port -eq 8765) { throw 'Port 8765 is reserved for the working GS-025 installation.' }
$dirty = @(& git -C $repo status --porcelain)
if ($dirty.Count -gt 0 -and ($dirty | Where-Object { $_ -ne '' }).Count -gt 0) {
    throw 'Preview checkout has uncommitted changes; verify the worktree before proceeding.'
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Windows Python launcher (py) is required for local verification.'
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js is required for the frontend syntax verification.'
}

Push-Location -LiteralPath $repo
try {
    Write-Host 'Verifying GS-026 model, approval and GS-025 portable compatibility tests...'
    & py -3 -m unittest tests.test_gs026_model_profiles tests.test_gs026_model_controls tests.test_gs025_public_security tests.test_gs024_device_login tests.test_gs023_collaboration tests.test_gs018_codex_agent tests.test_gs017_group_approvals tests.test_gs016_codex -v
    if ($LASTEXITCODE -ne 0) { throw 'GS-026 Python regression tests failed. GS-025 is unchanged.' }
    & node --check web/public/app.js
    if ($LASTEXITCODE -ne 0) { throw 'GS-026 JavaScript syntax validation failed. GS-025 is unchanged.' }
    Write-Host 'GS-026 PREVIEW PRECHECK PASS. GS-025 has not been restarted.' -ForegroundColor Green

    if (-not $StartPreview) { return }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $Port is already in use. Refusing to stop or replace its listener."
    }
    $previewState = Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace-GS026-Preview'
    $env:GROUND_SPACE_DEPLOYMENT_MODE = 'owner_private'
    $env:GROUND_SPACE_CODEX_WRITE_ENABLED = '0'
    $env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED = '0'
    Remove-Item Env:GROUND_SPACE_TAILSCALE_ORIGIN -ErrorAction SilentlyContinue
    foreach ($flag in @('GROUND_SPACE_PUBLIC_USERS','GROUND_SPACE_ENABLE_MULTI_USER','GROUND_SPACE_PUBLIC_HOSTING')) {
        Remove-Item ('Env:' + $flag) -ErrorAction SilentlyContinue
    }

    Write-Host "Starting isolated local-only GS-026 UI preview: http://127.0.0.1:$Port" -ForegroundColor Cyan
    Write-Host "Preview state: $previewState"
    Write-Host 'GS-025 port 8765 and Tailscale settings are not changed. Press Ctrl+C to stop preview.'
    & py -3 -m ground_space.webapp --port $Port --state-dir $previewState --no-browser
    if ($LASTEXITCODE -ne 0) { throw 'GS-026 preview server exited with an error.' }
}
finally {
    Pop-Location
}
