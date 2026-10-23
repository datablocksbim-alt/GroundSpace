# GS-030 owner-approved guarded ASUS release. Default preflight leaves production running.
[CmdletBinding()]
param([switch]$Activate)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$oldRepo=$null
$state=Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace'
$canaryPort=8784
if (-not (Test-Path (Join-Path $repo '.git') -PathType Leaf)) { throw 'Use separate GS-030 Git worktree.' }
$head=(@(& git -C $repo rev-parse HEAD) -join '').Trim()
$remote=(@(& git -C $repo rev-parse 'refs/remotes/origin/feature/gs-030-chat-project-management') -join '').Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $remote) { throw 'GS-030 HEAD must equal fetched remote.' }
$dirty=@(& git -C $repo status --porcelain | Where-Object { $_ })
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'GS-030 worktree must be clean.' }
$candidateCode=Get-Content -LiteralPath (Join-Path $repo 'ground_space\webapp.py') -Raw
if (-not $candidateCode.Contains('BACKEND_RELEASE = "GS-030"') -or
    -not $candidateCode.Contains('if path == "/api/projects/rename"') -or
    -not $candidateCode.Contains('if path == "/api/groups/rename"') -or
    -not $candidateCode.Contains('if path == "/api/groups/remove"')) {
  throw 'This GS-030 checkout is missing required project/chat management routes.'
}
$initial=Invoke-RestMethod 'http://127.0.0.1:8765/api/bootstrap' -TimeoutSec 10
$oldRelease=[string]$initial.backend_release
if ($oldRelease -eq 'GS-030') {
  $caps=$initial.capabilities
  if ($caps -and $caps.project_rename -eq $true -and
      $caps.group_rename -eq $true -and $caps.group_remove -eq $true) {
    Write-Host 'GS-030 project/chat management already loaded. No restart.' -ForegroundColor Green
    return
  }
  throw 'GS-030 label exists but required routes are not loaded. Use a separately tested same-version refresh, not this cutover.'
}
if ($oldRelease -notin @('GS-027','GS-028','GS-029')) {
  throw "Unexpected live release '$oldRelease'; cutover refused."
}
if ($oldRelease -eq 'GS-029') {
  # A pinned tested GS-029 release is a stable rollback even if the original
  # GS-029 worktree was subsequently updated while Python remained resident.
  $rollbackSha='396cb87cc78bde40a93060a40ddfd06f7465b4b1'
  $rollbackDir='D:\000_AI Project\GroundSpace-GS029-Rollback-GS030'
  $validated=(@(& git -C $repo rev-parse $rollbackSha) -join '').Trim()
  if ($LASTEXITCODE -ne 0 -or $validated -ne $rollbackSha) {
    throw 'Cannot resolve pinned validated GS-029 rollback commit.'
  }
  if (-not (Test-Path -LiteralPath $rollbackDir)) {
    & git -C $repo worktree add --detach $rollbackDir $rollbackSha
    if ($LASTEXITCODE -ne 0) { throw 'Rollback worktree creation failed.' }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $rollbackDir '.git') -PathType Leaf)) {
    throw 'Rollback folder is not a detached Git worktree.'
  }
  $rollbackHead=(@(& git -C $rollbackDir rev-parse HEAD) -join '').Trim()
  $rollbackDirty=@(& git -C $rollbackDir status --porcelain | Where-Object { $_ })
  if ($LASTEXITCODE -ne 0 -or $rollbackHead -ne $rollbackSha -or $rollbackDirty.Count) {
    throw 'GS-029 rollback worktree differs from the pinned known release.'
  }
  $oldRepo=$rollbackDir
} else {
  foreach ($name in @('GroundSpace-GS028-Preview','GroundSpace-GS027-Preview')) {
    $candidate=Join-Path 'D:\000_AI Project' $name
    $oldApp=Join-Path $candidate 'ground_space\webapp.py'
    if ((Test-Path -LiteralPath $oldApp -PathType Leaf) -and
        ((Get-Content -LiteralPath $oldApp -Raw).Contains('BACKEND_RELEASE = "'+$oldRelease+'"'))) {
      $oldRepo=$candidate
      break
    }
  }
  if (-not $oldRepo) { throw "No intact $oldRelease fallback checkout found." }
}
$oldApp=Join-Path $oldRepo 'ground_space\webapp.py'
if (-not (Test-Path -LiteralPath $oldApp -PathType Leaf) -or
    -not ((Get-Content -LiteralPath $oldApp -Raw).Contains('BACKEND_RELEASE = "'+$oldRelease+'"'))) {
  throw 'Fallback checkout release identity could not be verified.'
}

function Bootstrap([int]$port) { Invoke-RestMethod "http://127.0.0.1:$port/api/bootstrap" -TimeoutSec 8 }
# Stable data comparison: preserve every array element and its order, but sort
# object keys recursively. A loaded Python process and a disk-reloaded canary
# can enumerate conversation IDs in different orders even when all messages match.
function CanonicalValue($value) {
  if ($null -eq $value) { return $null }
  if ($value -is [pscustomobject] -or $value -is [System.Collections.IDictionary]) {
    $map=[System.Collections.Generic.SortedDictionary[string,object]]::new(
      [System.StringComparer]::Ordinal)
    if ($value -is [System.Collections.IDictionary]) {
      foreach($key in $value.Keys) {
        $map.Add([string]$key, (CanonicalValue $value[$key]))
      }
    } else {
      foreach($property in $value.PSObject.Properties) {
        $map.Add([string]$property.Name, (CanonicalValue $property.Value))
      }
    }
    return ,$map
  }
  if ($value -is [System.Collections.IEnumerable] -and $value -isnot [string]) {
    $elements=[System.Collections.Generic.List[object]]::new()
    foreach($element in $value) { $elements.Add((CanonicalValue $element)) }
    return ,$elements.ToArray()
  }
  return $value
}
function StableJson($value) {
  ConvertTo-Json -InputObject (CanonicalValue $value) -Depth 70 -Compress
}
function Verify($item,$baseline,[string]$release) {
  if ([string]$item.backend_release -ne $release) {
    throw "Expected $release, found $($item.backend_release)"
  }
  foreach($name in @('projects','groups')) {
    $before=StableJson @($baseline.workspaces.$name)
    $after=StableJson @($item.workspaces.$name)
    if ($before -cne $after) {
      throw "$release $name IDs/metadata changed (canonical values differ)"
    }
  }
  foreach($name in @('conversations','tasks','collaborations','agent_configs')) {
    $before=StableJson $baseline.$name
    $after=StableJson $item.$name
    if ($before -cne $after) {
      throw "$release $name data changed (canonical values differ)"
    }
  }
  foreach($name in @('jobs','project_modes')) {
    $before=StableJson $baseline.codex.$name
    $after=StableJson $item.codex.$name
    if ($before -cne $after) {
      throw "$release Codex $name changed (canonical values differ)"
    }
  }
}

function SafeJobs($item) {
  if (-not $item.PSObject.Properties['codex'] -or -not $item.codex.PSObject.Properties['jobs']) {
    throw 'Codex job state unavailable'
  }
  foreach ($task in @($item.tasks)) {
    # Group rejections remain stored as status=queued with approval=rejected.
    # They are non-executable (OrchestratorAdapter.process requires approved).
    # Never treat an explicit owner rejection as pending work.
    if ([string]$task.status -eq 'queued' -and
        [string]$task.approval.status -eq 'rejected') { continue }
    $status=[string]$task.status
    $approval=[string]$task.approval.status
    if ($status -eq 'queued' -and $approval -eq 'pending') {
      throw 'Task awaiting owner approval; approve or reject it before cutover.'
    }
    if ($status -eq 'queued' -and $approval -eq 'approved') {
      throw 'Approved task is waiting for execution; process it before cutover.'
    }
    if ($status -in @('claimed','running','in_progress','processing','leased')) {
      throw 'Task is running or leased; wait for it to finish before cutover.'
    }
    if ($status -in @('retrying','retry_pending','pending','pending_approval')) {
      throw 'Task is stalled or retryable; resolve it before cutover.'
    }
    if ($status -eq 'queued') {
      throw "Queued task has unknown approval state '$approval'; cutover refused."
    }
  }
  foreach ($job in @($item.codex.jobs)) {
    if ([string]$job.status -in @('queued','running','retrying','pending_approval')) {
      throw 'Codex has pending or active work; cutover refused.'
    }
  }
}

function SafeAllQueueFiles {
  $queueDir=Join-Path $state 'private\queue'
  if (-not (Test-Path -LiteralPath $queueDir -PathType Container)) {
    throw 'Production queue directory not found. Do not switch.'
  }
  foreach ($file in @(Get-ChildItem -LiteralPath $queueDir -Filter '*.json' -File -Force)) {
    try { $record=Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json }
    catch { throw "Cannot parse task queue file $($file.Name); cutover refused." }
    $status=[string]$record.status
    $approval=[string]$record.approval.status
    if ($status -eq 'queued' -and $approval -eq 'rejected') { continue }
    if ($status -notin @('completed','failed','cancelled','blocked','rejected')) {
      throw "Unfinished task in full queue ledger $($file.Name): $status / $approval. Finish before cutover."
    }
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
  # PowerShell Start-Process joins ArgumentList items; quote state paths containing spaces.
  $quotedRoot='"'+($root -replace '"','')+'"'
  $argsList=@($prefix)+@('-m','ground_space.webapp','--port',"$port",'--state-dir',$quotedRoot,'--no-browser')
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
Verify $live $live $oldRelease
SafeJobs $live
SafeAllQueueFiles
$oldPid=LivePid
$raw=& tailscale status --json
if($LASTEXITCODE -ne 0) { throw 'Tailscale status unavailable' }
$tail=$raw | ConvertFrom-Json
$hostname=([string]$tail.Self.DNSName).TrimEnd('.')
if($hostname -notmatch '^([a-z0-9-]+\.){2,}ts\.net$') { throw 'Unrecognised Tailscale hostname' }
$origin='https://' + $hostname + ':8443'
$served=(& tailscale serve status | Out-String)
if($LASTEXITCODE -ne 0 -or $served -notmatch '127\.0\.0\.1:8765') { throw 'Private route does not target 8765' }
Verify (Invoke-RestMethod ($origin+'/api/bootstrap') -TimeoutSec 8) $live $oldRelease
if(Get-NetTCPConnection -LocalPort $canaryPort -State Listen -ErrorAction SilentlyContinue) {
  throw "Canary test port $canaryPort is occupied"
}
$backupOutput=@(& (Join-Path $PSScriptRoot 'backup_ground_space_state.ps1') -ExpectedRelease $oldRelease -Port 8765 -StateRoot $state)
$backup=[string]$backupOutput[-1]
$manifestFile=Join-Path $backup 'BACKUP_MANIFEST.json'
if(-not (Test-Path $manifestFile)) { throw 'Verified backup manifest missing' }
$manifest=Get-Content $manifestFile -Raw | ConvertFrom-Json
if($manifest.source_release -ne $oldRelease) { throw 'Wrong backup release' }
function Assert-LiveUnchanged {
  $root=Join-Path $state 'private'
  $all=@(Get-ChildItem -LiteralPath $root -Recurse -File -Force | Where-Object { $_.Name -notlike '*.tmp' -and $_.Name -ne 'BACKUP_MANIFEST.json' })
  $entries=@($manifest.files)
  if($all.Count -ne $entries.Count) { throw 'Private-state file count changed since backup' }
  foreach($entry in $entries) {
    $path=Join-Path $root $entry.path
    if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Missing private state: '+$entry.path) }
    if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne [string]$entry.sha256) {
      throw ('Private state changed since backup: '+$entry.path)
    }
  }
}
$testRoot=Join-Path $env:TEMP ('gs030-restore-'+[guid]::NewGuid().ToString('N'))
$testPrivate=Join-Path $testRoot 'private'
New-Item -ItemType Directory -Force -Path $testPrivate | Out-Null
Get-ChildItem -LiteralPath $backup -Force | Where-Object { $_.Name -ne 'BACKUP_MANIFEST.json' } |
  Copy-Item -Destination $testPrivate -Recurse -Force
$testProcess=$null
try {
  $testProcess=StartApp $repo $canaryPort $testRoot '' 'gs030-canary'
  $canary=Healthy $testProcess $canaryPort 'GS-030' $live
  if (-not $canary.PSObject.Properties['capabilities'] -or
      $canary.capabilities.project_remove -ne $true -or
      $canary.capabilities.project_rename -ne $true -or
      $canary.capabilities.group_rename -ne $true -or
      $canary.capabilities.group_remove -ne $true) {
    throw 'GS-030 canary lacks the exact project/chat management capabilities. No production restart.'
  }
} finally {
  if($testProcess -and -not $testProcess.HasExited) {
    Stop-Process -Id $testProcess.Id -ErrorAction SilentlyContinue
    $testProcess.WaitForExit(5000) | Out-Null
  }
  Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Verified backup: $backup"
Write-Host 'GS-030 restored-state canary PASS' -ForegroundColor Green
if(-not $Activate) {
  Write-Host "PREFLIGHT PASS: $oldRelease still running. Rerun with -Activate." -ForegroundColor Green
  return
}
$before=Bootstrap 8765
Verify $before $live $oldRelease
SafeJobs $before
SafeAllQueueFiles
Assert-LiveUnchanged
if((LivePid) -ne $oldPid) { throw 'Production PID changed; refusing cutover' }
$newProcess=$null
$stopped=$false
try {
  Stop-Process -Id $oldPid -ErrorAction Stop
  $stopped=$true
  Assert-LiveUnchanged
  for($i=0;$i -lt 12;$i++) {
    if(-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
  }
  if(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8765 occupied after stop' }
  $newProcess=StartApp $repo 8765 $state $origin 'gs030-production'
  $active=Healthy $newProcess 8765 'GS-030' $live
  if (-not $active.PSObject.Properties['capabilities'] -or
      $active.capabilities.project_remove -ne $true -or
      $active.capabilities.project_rename -ne $true -or
      $active.capabilities.group_rename -ne $true -or
      $active.capabilities.group_remove -ne $true) {
    throw 'GS-030 backend management capabilities missing after cutover.'
  }
  $remoteCheck=Invoke-RestMethod ($origin+'/api/bootstrap') -TimeoutSec 8
  Verify $remoteCheck $live 'GS-030'
  if (-not $remoteCheck.PSObject.Properties['capabilities'] -or
      $remoteCheck.capabilities.project_remove -ne $true -or
      $remoteCheck.capabilities.project_rename -ne $true -or
      $remoteCheck.capabilities.group_rename -ne $true -or
      $remoteCheck.capabilities.group_remove -ne $true) {
    throw 'Private Tailscale endpoint did not expose the updated GS-030 management routes.'
  }
  Write-Host "GS-030 ACTIVATED AND VERIFIED: PID $($newProcess.Id)" -ForegroundColor Green
  Write-Host 'Private Tailscale route unchanged; Codex workspace-write disabled.'
  Write-Host "Retained $oldRelease backup: $backup"
} catch {
  $why=$_.Exception.Message
  Write-Warning "GS-030 activation error: $why"
  if($newProcess -and -not $newProcess.HasExited) {
    Stop-Process -Id $newProcess.Id -ErrorAction SilentlyContinue
    $newProcess.WaitForExit(5000) | Out-Null
  }
  if($stopped) {
    if(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
      throw 'Unknown listener owns 8765: manual recovery required. Do not kill it.'
    }
    try {
      $rollback=StartApp $oldRepo 8765 $state $origin 'gs030-rollback'
      $null=Healthy $rollback 8765 $oldRelease $live
      Write-Warning "$oldRelease application rollback succeeded. Inspect state before new tasks."
    } catch {
      throw "GS-030 failed ($why); rollback also failed: $($_.Exception.Message). Backup: $backup"
    }
  }
  throw "GS-030 NOT ACTIVATED: $why"
}
