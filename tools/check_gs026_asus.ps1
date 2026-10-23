# GS-026 ASUS acceptance preflight. Read-only: no service restart, state migration, or Tailscale changes.
[CmdletBinding()]
param([switch]$Browser)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

Write-Host 'GS-026 ASUS acceptance preflight — existing GS-025 remains live' -ForegroundColor Cyan
$previewCheck = Join-Path $PSScriptRoot 'prepare_gs026_preview.ps1'
if (-not (Test-Path -LiteralPath $previewCheck)) {
    throw 'GS-026 preview verification script is missing.'
}
& $previewCheck
if (-not $?) { throw 'GS-026 preview precheck failed.' }

# Check the currently running owner-only service without changing its process or settings.
$existing = try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/bootstrap' -TimeoutSec 8
} catch {
    throw 'Cannot read the existing GS-025 server on localhost:8765. Do not cut over yet.'
}
if ($existing.backend_release -ne 'GS-025') {
    throw "Expected approved GS-025 on port 8765, found: $($existing.backend_release). Do not change a running unknown version."
}
if ($existing.security.public_ready -eq $true) {
    throw 'Unexpected public-ready security flag; inspect deployment before proceeding.'
}
$running = @($existing.codex.jobs | Where-Object { $_.status -eq 'running' })
if ($running.Count -gt 0) {
    throw 'Codex jobs are running on GS-025. Do not restart until they finish.'
}
Write-Host 'PASS: existing GS-025 backend detected, no Codex jobs running.' -ForegroundColor Green

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    throw 'Tailscale CLI unavailable. Cannot confirm the established owner-only route.'
}
$tailStatus = & tailscale status --json
if ($LASTEXITCODE -ne 0) { throw 'Tailscale status check failed.' }
$tail = $tailStatus | ConvertFrom-Json
if (-not $tail.Self.DNSName) { throw 'Tailscale private DNS name is missing.' }
$hostname = ([string]$tail.Self.DNSName).TrimEnd('.')
if ($hostname -notmatch '^([a-z0-9-]+\.){2,}ts\.net$') {
    throw 'Unrecognized Tailnet DNS name; stopping before activation.'
}
$serve = & tailscale serve status
if ($LASTEXITCODE -ne 0 -or (($serve | Out-String) -notmatch ':8443(?:\b|/)')) {
    throw 'Expected Tailscale Serve 8443 mapping is not active. No changes were made.'
}
Write-Host 'PASS: expected private Tailscale Serve entry exists. No Tailscale settings changed.' -ForegroundColor Green

$localSuite = Join-Path $PSScriptRoot 'verify_gs022_local.ps1'
if (-not (Test-Path -LiteralPath $localSuite)) { throw 'Full ASUS-local test suite script is missing.' }
if ($Browser) {
    & $localSuite -Browser
} else {
    & $localSuite
}
if (-not $?) { throw 'Full ASUS-local integration verification failed.' }

Write-Host ''
Write-Host 'GS-026 ASUS AUTOMATED PREFLIGHT PASSED (not live activation).' -ForegroundColor Green
Write-Host 'Next: verify a real signed-in Codex model in a disposable project, then physical iPhone Safari.'
Write-Host 'GS-025 remains running; no laptop reboot, process stop, merge, or Tailscale mutation occurred.'
