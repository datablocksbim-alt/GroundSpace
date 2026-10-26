param(
    [int]$Port = 8765,
    [switch]$NoBrowser,
    [string]$TailscaleOrigin = $env:GROUND_SPACE_TAILSCALE_ORIGIN
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Data Blocks Python runtime not found: $python"
}

# The backend intentionally trusts only an exact, explicitly configured private
# Tailscale HTTPS origin for state-changing requests. Discover the local node's
# MagicDNS name when the normal launcher is used so a reboot/manual restart does
# not silently leave the mobile UI in read-only mode.
if (-not $TailscaleOrigin) {
    $tailscale = Get-Command 'tailscale.exe' -ErrorAction SilentlyContinue
    $tailscalePath = if ($tailscale) { $tailscale.Source } else { $null }
    if (-not $tailscale) {
        $installedTailscale = 'C:\Program Files\Tailscale\tailscale.exe'
        if (Test-Path -LiteralPath $installedTailscale) {
            $tailscalePath = $installedTailscale
        }
    }

    if ($tailscalePath) {
        try {
            $tailscaleStatus = (& $tailscalePath status --json | ConvertFrom-Json)
            $dnsName = [string]$tailscaleStatus.Self.DNSName
            if ($tailscaleStatus.BackendState -eq 'Running' -and $dnsName) {
                $TailscaleOrigin = 'https://' + $dnsName.TrimEnd('.') + ':8443'
            }
        }
        catch {
            Write-Warning "Tailscale origin discovery failed; continuing in localhost-only mode: $($_.Exception.Message)"
        }
    }
}

if ($TailscaleOrigin) {
    if ($TailscaleOrigin -notmatch '^https://(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.){2,}ts\.net:8443$') {
        throw "Invalid Tailscale origin: $TailscaleOrigin"
    }
    $env:GROUND_SPACE_TAILSCALE_ORIGIN = $TailscaleOrigin
    Write-Host "Ground Space private mobile origin: $TailscaleOrigin"
}
else {
    Remove-Item Env:\GROUND_SPACE_TAILSCALE_ORIGIN -ErrorAction SilentlyContinue
    Write-Host 'Ground Space mobile origin not configured; localhost-only writes are enabled.'
}

Set-Location -LiteralPath $projectRoot
$arguments = @('-m', 'ground_space.webapp', '--port', $Port)
if ($NoBrowser) { $arguments += '--no-browser' }
& $python @arguments
