[CmdletBinding()] param([switch]$Restart, [switch]$EnableCodexWrite, [switch]$EnableChatGPTConnect)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo = Split-Path -Parent $PSScriptRoot
$expected = 'feature/gs-026-mobile-agent-model-controls'
# The ASUS activation checkout is intentionally a detached Git worktree.
# Never restart production from the original GS-021 checkout or an unverified ref.
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git') -PathType Leaf)) {
    throw 'GS-026 production activation requires the isolated preview Git worktree; never switch the original GS-021 installation.'
}
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine GS-026 checkout branch.' }
if ($branch -and $branch -ne $expected) {
    throw "Unexpected GS-026 checkout branch: $branch"
}
$head = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine GS-026 checkout commit.' }
$remoteHead = (& git -C $repo rev-parse "refs/remotes/origin/$expected").Trim()
if ($LASTEXITCODE -ne 0 -or -not $remoteHead -or $head -ne $remoteHead) {
    throw 'GS-026 worktree commit does not match the fetched remote feature branch; fetch and verify before activation.'
}
$dirty = & git -C $repo status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Uncommitted local changes or unreadable Git status. Protect files before restart.' }
$python = 'D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $command=Get-Command py -ErrorAction SilentlyContinue
    if (-not $command) { throw "Python runtime not found: $python" }
    $python = $command.Source
}
$tail = (& tailscale status --json | ConvertFrom-Json)
if (-not $tail.Self.DNSName) { throw 'Tailscale DNS hostname unavailable' }
$hostname = ([string]$tail.Self.DNSName).TrimEnd('.')
if ($hostname -notmatch '^([a-z0-9-]+\.){2,}ts\.net$') { throw 'Unexpected Tailscale hostname' }
$origin = 'https://' + $hostname + ':8443'
$served = (& tailscale serve status | Out-String)
if ($served -notmatch ':8443(?:\b|/)') { throw 'Ground Space Tailscale Serve endpoint 8443 not active' }
$listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
$serverPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
Write-Host "Codex bridge: $origin"
Write-Host "Ground Space listener count: $($serverPids.Count)"
foreach ($processId in $serverPids) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    Write-Host "PID $processId : $($p.CommandLine)"
    if (-not $p -or $p.CommandLine -notmatch 'ground_space\.webapp') {
        throw "PID $processId is not verified as the Ground Space service; refusing to stop it"
    }
}
if ($serverPids.Count -gt 0) {
    try {
        $existing = Invoke-RestMethod 'http://127.0.0.1:8765/api/bootstrap' -TimeoutSec 8
    } catch {
        throw 'Cannot inspect running Codex jobs; refusing restart until current server is healthy.'
    }
    if ([string]$existing.backend_release -notin @('GS-021', 'GS-025', 'GS-026')) {
        throw "Unrecognized running Ground Space release '$($existing.backend_release)'; refusing to stop this process."
    }
    if (-not $existing.PSObject.Properties['codex'] -or -not $existing.codex.PSObject.Properties['jobs']) {
        throw 'Codex job status is unavailable; refusing to stop this process.'
    }
    $activeCodex = @($existing.codex.jobs | Where-Object { $_.status -eq 'running' })
    if ($activeCodex.Count -gt 0) {
        throw 'A Codex review or workspace edit is running. Wait for it to finish before restarting Ground Space.'
    }
}
if (-not $Restart) { Write-Host 'Preflight only. Add -Restart to restart Ground Space. Add -EnableCodexWrite only if you accept approved Codex edits/runs/deletes in registered projects.'; return }
if ($serverPids.Count -gt 1) { throw 'Multiple processes on 8765; manual investigation required' }
foreach ($processId in $serverPids) { Stop-Process -Id $processId -ErrorAction Stop }
Start-Sleep -Milliseconds 500
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8765 is still occupied' }
$env:GROUND_SPACE_TAILSCALE_ORIGIN = $origin
$env:GROUND_SPACE_DEPLOYMENT_MODE = 'owner_private'
foreach ($publicVar in @('GROUND_SPACE_PUBLIC_USERS','GROUND_SPACE_ENABLE_MULTI_USER','GROUND_SPACE_PUBLIC_HOSTING')) {
    Remove-Item ('Env:'+ $publicVar) -ErrorAction SilentlyContinue
}
if ($EnableChatGPTConnect) {
    $env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED = '1'
    Write-Host 'Owner-only ChatGPT device login enabled. This is NOT multi-user authentication.' -ForegroundColor Yellow
} else {
    Remove-Item Env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED -ErrorAction SilentlyContinue
}

if ($EnableCodexWrite) {
    $env:GROUND_SPACE_CODEX_WRITE_ENABLED = '1'
    Write-Host 'Codex workspace-write explicitly ENABLED for owner-approved project jobs.' -ForegroundColor Yellow
} else {
    Remove-Item Env:GROUND_SPACE_CODEX_WRITE_ENABLED -ErrorAction SilentlyContinue
    Write-Host 'Codex workspace-write disabled. Use -EnableCodexWrite for writable agent tasks.'
}
$logs = Join-Path $env:LOCALAPPDATA 'GroundSpace\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$stdout = Join-Path $logs 'gs016-codex-stdout.log'
$stderr = Join-Path $logs 'gs016-codex-stderr.log'
if ($python -like '*\py.exe') { $args=@('-3','-m','ground_space.webapp','--port','8765','--no-browser') }
else { $args=@('-m','ground_space.webapp','--port','8765','--no-browser') }
$process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $repo -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$ready=$false
for ($attempt=0; $attempt -lt 25; $attempt++) {
    Start-Sleep -Milliseconds 450
    try {
        $data=Invoke-RestMethod 'http://127.0.0.1:8765/api/bootstrap' -TimeoutSec 3
        if ($data.codex.scope -eq 'single_owner_pilot' -and $data.backend_release -eq 'GS-026') { $ready=$true; break }
    } catch { if ($process.HasExited) { break } }
}
if (-not $ready) { throw "Ground Space/Codex failed healthcheck. Check $stderr (Tailscale routes unchanged)." }
Write-Host "Ground Space Codex pilot ready (PID $($process.Id)): $origin" -ForegroundColor Green
Write-Host ('Codex CLI found: '+[bool](Get-Command codex -ErrorAction SilentlyContinue))
Write-Host 'Approval default: Ask every time. Add Codex under Agents; group approvals under Members.'
