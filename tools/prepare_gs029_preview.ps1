# GS-029 project-centric navigation preview only: never restart production.
[CmdletBinding()]
param([switch]$StartPreview, [ValidateRange(1025,65535)][int]$Port = 8781)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $repo '.git') -PathType Leaf)) {
  throw 'Run from a separate detached GS-029 worktree, not a live checkout.'
}
$head = (@(& git -C $repo rev-parse HEAD) -join '').Trim()
$remote = (@(& git -C $repo rev-parse 'refs/remotes/origin/feature/gs-029-project-folder-picker') -join '').Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $remote) {
  throw 'Preview checkout must match the fetched origin GS-029 feature commit.'
}
$dirty = @(& git -C $repo status --porcelain | Where-Object { $_ })
if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) { throw 'Uncommitted changes detected; stop.' }
if ($Port -in @(8765,8766,8767,8768,8779)) { throw 'This port is reserved for production or an earlier isolated test.' }
Push-Location $repo
try {
  & py -3 -m unittest tests.test_gs029_folder_picker tests.test_gs014_mobile_ui tests.test_gs027_agent_configs tests.test_gs026_model_controls tests.test_gs025_public_security tests.test_gs017_group_approvals -v
  if ($LASTEXITCODE -ne 0) { throw 'GS-029 Python regression failed.' }
  & node --check web/public/app.js
  if ($LASTEXITCODE -ne 0) { throw 'GS-029 JavaScript syntax failed.' }
  Write-Host 'GS-029 PREVIEW CHECK PASS. Working Ground Space untouched.' -ForegroundColor Green
  if (-not $StartPreview) { return }
  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already occupied. No processes were stopped."
  }
  $previewState = Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace-GS028-Preview'
  $env:GROUND_SPACE_DEPLOYMENT_MODE = 'owner_private'
  $env:GROUND_SPACE_CODEX_WRITE_ENABLED = '0'
  $env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED = '0'
  foreach ($name in @('GROUND_SPACE_TAILSCALE_ORIGIN','GROUND_SPACE_PUBLIC_USERS',
                      'GROUND_SPACE_ENABLE_MULTI_USER','GROUND_SPACE_PUBLIC_HOSTING')) {
    Remove-Item ('Env:' + $name) -ErrorAction SilentlyContinue
  }
  Write-Host "GS-029 preview: http://127.0.0.1:$Port" -ForegroundColor Cyan
  Write-Host 'Loopback only; do not route Tailscale to this preview. Ctrl+C stops only the preview.'
  & py -3 -m ground_space.webapp --port $Port --state-dir $previewState --no-browser
  if ($LASTEXITCODE -ne 0) { throw 'GS-029 preview failed to start.' }
} finally {
  Pop-Location
}
