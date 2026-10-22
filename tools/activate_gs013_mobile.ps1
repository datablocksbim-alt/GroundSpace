[CmdletBinding()]
param([switch]$CheckOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe'
$port = 8765
$httpsPort = 8443
$targetBranch = 'feature/gs-013-coordinator-tailnet-mobile'

if (-not (Test-Path -LiteralPath $python)) { throw "Ground Space Python runtime missing: $python" }
$actualBranch = (& git -C $repoRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $actualBranch -ne $targetBranch) {
    throw "Use the integrated Ground Space branch first: $targetBranch (currently '$actualBranch')"
}

$ts = Get-Command tailscale -ErrorAction Stop
$tailscaleJson = & tailscale status --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $tailscaleJson.Self.DNSName) {
    throw 'Tailscale is offline or cannot determine its private DNS hostname.'
}
$hostname = ([string]$tailscaleJson.Self.DNSName).TrimEnd('.')
$origin = 'https://' + $hostname + ':' + $httpsPort
if ($origin -notmatch '^https://(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.){2,}ts\.net:8443$') {
    throw "Unexpected Tailscale hostname: $hostname"
}
$oldRoutes = (& tailscale serve status | Out-String)
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Tailscale Serve routes. No changes made.' }
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
Write-Host "Existing Tailscale routes:" -ForegroundColor Cyan
Write-Host $oldRoutes
Write-Host "Ground Space planned address: $origin" -ForegroundColor Cyan
Write-Host "Local Ground Space listeners on ${port}: $($listeners.Count)"

if ($CheckOnly) {
    Write-Host 'Read-only preflight complete; nothing was started or reconfigured.' -ForegroundColor Green
    return
}
if ($oldRoutes -match ':8443(?:\b|/)') {
    throw 'HTTPS port 8443 already appears in Tailscale Serve status. Refusing to overwrite an existing application.'
}
if ($listeners.Count -gt 0) {
    throw 'Ground Space is still running on 8765. Stop ONLY its existing PowerShell server with Ctrl+C, then rerun this script. No changes made.'
}

# Child inherits this environment value on Windows without changing any global or machine setting.
$env:GROUND_SPACE_TAILSCALE_ORIGIN = $origin
$logFolder = Join-Path $env:LOCALAPPDATA 'GroundSpace\logs'
New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
$stdout = Join-Path $logFolder 'gs013-mobile-stdout.log'
$stderr = Join-Path $logFolder 'gs013-mobile-stderr.log'
$server = Start-Process -FilePath $python -ArgumentList @('-m', 'ground_space.webapp', '--port', "$port", '--no-browser') -WorkingDirectory $repoRoot -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Host "Started Ground Space process PID $($server.Id)"

$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $page = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $port + '/') -UseBasicParsing -TimeoutSec 3
        if ($page.StatusCode -eq 200 -and $page.Content.Contains('Ground Space')) {
            $ready = $true
            break
        }
    } catch {
        if ($server.HasExited) { break }
    }
}
if (-not $ready) {
    throw "The updated Ground Space did not become healthy. Check $stderr and $stdout. Existing dashboard routes were not changed."
}

Write-Host 'Ground Space is serving its expected UI on localhost.' -ForegroundColor Green
& tailscale serve --bg --https=8443 8765
if ($LASTEXITCODE -ne 0) {
    throw "Tailscale refused the new 8443 route. Ground Space is still local. Existing dashboard routes were not changed by this script."
}
$newRoutes = (& tailscale serve status | Out-String)
Write-Host $newRoutes
if ($newRoutes -notmatch ':8443(?:\b|/)') {
    throw 'Port 8443 was not found in Serve status. Inspect output; do not remove the existing dashboard routes.'
}
Write-Host "GROUND SPACE PRIVATE MOBILE ADDRESS: $origin" -ForegroundColor Green
Write-Host 'Open this URL in iPhone Safari with Tailscale connected; verify /goal note and old /dashboard separately.'
Write-Host "Server log files: $stdout and $stderr"
