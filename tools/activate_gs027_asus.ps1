# GS-027 guarded ASUS release; default is non-disruptive preflight.
[CmdletBinding()]
param([switch]$Activate)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$oldRepo='D:\000_AI Project\GroundSpace-GS026-Preview'
$state=Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace'
$canaryPort=8779
if (-not (Test-Path (Join-Path $repo '.git') -PathType Leaf)) { throw 'Use separate GS-027 Git worktree.' }
$head=(@(& git -C $repo rev-parse HEAD) -join '').Trim()
$remote=(@(& git -C $repo rev-parse 'refs/remotes/origin/feature/gs-027-unified-agent-configuration') -join '').Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $remote) { throw 'GS-027 HEAD must equal fetched remote.' }
$dirty=@(& git -C $repo status --porcelain | Where-Object { $_ })
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'GS-027 worktree must be clean.' }
$oldApp=Join-Path $oldRepo 'ground_space\webapp.py'
if (-not (Test-Path $oldApp) -or (Get-Content $oldApp -Raw) -notmatch 'BACKEND_RELEASE = "GS-026"') {
  throw 'Unmodified GS-026 fallback checkout unavailable.'
}
function Bootstrap([int]$port) { Invoke-RestMethod "http://127.0.0.1:$port/api/bootstrap" -TimeoutSec 8 }
function Verify($item,$baseline,[string]$release) {
  if ([string]$item.backend_release -ne $release) { throw "Expected $release; observed $($item.backend_release)" }
  foreach($name in @('projects','groups')) {
    if (@($item.workspaces.$name).Count -ne @($baseline.workspaces.$name).Count) { throw "$release $name count changed" }
  }
  if (@($item.tasks).Count -ne @($baseline.tasks).Count) { throw "$release task count changed" }
  if (@($item.codex.jobs).Count -ne @($baseline.codex.jobs).Count) { throw "$release Codex jobs count changed" }
  if (@($item.conversations.PSObject.Properties).Count -ne @($baseline.conversations.PSObject.Properties).Count) {
    throw "$release conversations count changed"
  }
}
function SafeJobs($item) {
  if (-not $item.PSObject.Properties['codex'] -or -not $item.codex.PSObject.Properties['jobs']) {
    throw 'Codex job status unavailable'
  }
  if (@($item.codex.jobs | Where-Object { $_.status -eq 'running' }).Count -gt 0) {
    throw 'Codex job is running: cutover refused'
  }
}
function LivePid {
  $ids=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
  if ($ids.Count -ne 1) { throw 'Ground Space listener PID count is not one' }
  $procId=$ids[0]
  $proc=Get-CimInstance Win32_Process -Filter "ProcessId = $procId"
  if (-not $proc -or $proc.CommandLine -notmatch 'ground_space\.webapp') {
    throw "Refusing unverified listener $procId"
  }
  return $procId
}
function StartApp([string]$dir,[int]$port,[string]$root,[string]$origin,[string]$name) {
  $python='D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe'
  $prefix=@()
  if (-not (Test-Path $python)) {
    $py=Get-Command py -ErrorAction SilentlyContinue
    if (-not $py) { throw 'No Python runtime found' }
    $python=$py.Source
    $prefix=@('-3')
  }
  $env:GROUND_SPACE_DEPLOYMENT_MODE='owner_private'
  $env:GROUND_SPACE_CODEX_WRITE_ENABLED='0'
  $env:GROUND_SPACE_OWNER_CHATGPT_LINK_ENABLED='0'
  if ($origin) { $env:GROUND_SPACE_TAILSCALE_ORIGIN=$origin }
  else { Remove-Item Env:GROUND_SPACE_TAILSCALE_ORIGIN -ErrorAction SilentlyContinue }
  foreach($v in @('GROUND_SPACE_PUBLIC_USERS','GROUND_SPACE_ENABLE_MULTI_USER','GROUND_SPACE_PUBLIC_HOSTING')) {
    Remove-Item ('Env:'+$v) -ErrorAction SilentlyContinue
  }
  $logs=Join-Path $env:LOCALAPPDATA 'GroundSpace\logs'
  New-Item -ItemType Directory -Force -Path $logs | Out-Null
  $stamp=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+$port
  $argsList=@($prefix)+@('-m','ground_space.webapp','--port',"$port",'--state-dir',$root,'--no-browser')
  Start-Process -FilePath $python -ArgumentList $argsList -WorkingDirectory $dir -PassThru -RedirectStandardOutput (Join-Path $logs "$name-$stamp-out.log") -RedirectStandardError (Join-Path $logs "$name-$stamp-err.log")
}
function Healthy($proc,[int]$port,[string]$release,$baseline) {
  for($i=0;$i -lt 35;$i++) {
    Start-Sleep -Milliseconds 500
    if($proc.HasExited) { throw "$release process exited" }
    try {
      $data=Bootstrap $port
      Verify $data $baseline $release
      return $data
    } catch {
      if($i -eq 34) { throw "$release check failed: $($_.Exception.Message)" }
    }
  }
}
$live=Bootstrap 8765
Verify $live $live 'GS-026'
SafeJobs $live
$oldPid=LivePid
$raw=& tailscale status --json
if($LASTEXITCODE -ne 0) { throw 'Tailscale status unavailable' }
$tail=$raw | ConvertFrom-Json
$hostname=([string]$tail.Self.DNSName).TrimEnd('.')
if($hostname -notmatch '^([a-z0-9-]+\.){2,}ts\.net$') { throw 'Unrecognised Tailscale hostname' }
$origin='https://' + $hostname + ':8443'
$served=(& tailscale serve status | Out-String)
if($LASTEXITCODE -ne 0 -or $served -notmatch '127\.0\.0\.1:8765') { throw 'Private route does not target 8765' }
Verify (Invoke-RestMethod ($origin+'/api/bootstrap') -TimeoutSec 8) $live 'GS-026'
if(Get-NetTCPConnection -LocalPort $canaryPort -State Listen -ErrorAction SilentlyContinue) {
  throw 'Canary test port 8779 is occupied'
}
$backupOutput=@(& (Join-Path $PSScriptRoot 'backup_ground_space_state.ps1') -ExpectedRelease GS-026 -Port 8765 -StateRoot $state)
$backup=[string]$backupOutput[-1]
$manifestFile=Join-Path $backup 'BACKUP_MANIFEST.json'
if(-not (Test-Path $manifestFile)) { throw 'Verified backup manifest missing' }
$manifest=Get-Content $manifestFile -Raw | ConvertFrom-Json
if($manifest.source_release -ne 'GS-026') { throw 'Wrong backup release' }
$testRoot=Join-Path $env:TEMP ('gs027-restore-'+[guid]::NewGuid().ToString('N'))
$testPrivate=Join-Path $testRoot 'private'
New-Item -ItemType Directory -Force -Path $testPrivate | Out-Null
Get-ChildItem -LiteralPath $backup -Force | Where-Object { $_.Name -ne 'BACKUP_MANIFEST.json' } |
  Copy-Item -Destination $testPrivate -Recurse -Force
$testProcess=$null
try {
  $testProcess=StartApp $repo $canaryPort $testRoot '' 'gs027-canary'
  $null=Healthy $testProcess $canaryPort 'GS-027' $live
} finally {
  if($testProcess -and -not $testProcess.HasExited) {
    Stop-Process -Id $testProcess.Id -ErrorAction SilentlyContinue
    $testProcess.WaitForExit(5000) | Out-Null
  }
  Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Verified backup: $backup"
Write-Host 'GS-027 restored-state canary PASS' -ForegroundColor Green
if(-not $Activate) {
  Write-Host 'PREFLIGHT PASS: GS-026 production untouched. Rerun with -Activate to cut over.' -ForegroundColor Green
  return
}
$before=Bootstrap 8765
Verify $before $live 'GS-026'
SafeJobs $before
if((LivePid) -ne $oldPid) { throw 'Production PID changed; refusing cutover' }
$newProcess=$null
$stopped=$false
try {
  Stop-Process -Id $oldPid -ErrorAction Stop
  $stopped=$true
  for($i=0;$i -lt 12;$i++) {
    if(-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
  }
  if(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8765 occupied after stop' }
  $newProcess=StartApp $repo 8765 $state $origin 'gs027-production'
  $null=Healthy $newProcess 8765 'GS-027' $live
  Verify (Invoke-RestMethod ($origin+'/api/bootstrap') -TimeoutSec 8) $live 'GS-027'
  Write-Host "GS-027 ACTIVATED AND VERIFIED: PID $($newProcess.Id)" -ForegroundColor Green
  Write-Host 'Private Tailscale route unchanged; Codex workspace-write disabled.'
  Write-Host "GS-026 backup retained: $backup"
} catch {
  $why=$_.Exception.Message
  Write-Warning "GS-027 activation error: $why"
  if($newProcess -and -not $newProcess.HasExited) {
    Stop-Process -Id $newProcess.Id -ErrorAction SilentlyContinue
    $newProcess.WaitForExit(5000) | Out-Null
  }
  if($stopped) {
    if(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
      throw 'Unknown listener owns 8765: manual recovery required. Do not kill it.'
    }
    try {
      $rollback=StartApp $oldRepo 8765 $state $origin 'gs026-rollback'
      $null=Healthy $rollback 8765 'GS-026' $live
      Write-Warning 'GS-026 application rollback succeeded. Inspect state before new tasks.'
    } catch {
      throw "GS-027 failed ($why); rollback also failed: $($_.Exception.Message). Backup: $backup"
    }
  }
  throw "GS-027 NOT ACTIVATED: $why"
}
