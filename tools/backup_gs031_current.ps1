# GS-031 owner-local production data baseline.
# READS the running server; WRITES only a new, verified backup under BackupRoot.
# Never mutates production state, task approvals, Tailscale or project files.
[CmdletBinding()]
param(
  [ValidateRange(1025,65535)][int]$Port = 8765,
  [string]$StateRoot = (Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace'),
  [string]$BackupRoot = (Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace-Backups')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$server = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/bootstrap" -TimeoutSec 12
$release = [string]$server.backend_release
if ($release -notin @('GS-027','GS-028','GS-029','GS-030')) {
  throw "Unexpected live Ground Space release '$release'. No backup attempted."
}
$privateDir = Join-Path $StateRoot 'private'
$queueDir = Join-Path $privateDir 'queue'
if (-not (Test-Path -LiteralPath $privateDir -PathType Container) -or
    -not (Test-Path -LiteralPath $queueDir -PathType Container)) {
  throw 'Expected owner-private state or task queue folder is missing.'
}
# Do not snapshot while workers are actively processing; queued tasks are captured
# if no one approves them during the verified source/copy/source hash comparison.
$runningStatuses = @('running','claimed','processing','leased','in_progress','retrying')
$activeTaskCount = 0
$waitingTaskCount = 0
foreach($file in @(Get-ChildItem -LiteralPath $queueDir -File -Filter '*.json' -Force)) {
  try { $task=Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json }
  catch { throw "Queue record is unreadable: $($file.Name). No backup attempted." }
  $status=[string]$task.status
  if ($status -in $runningStatuses) { $activeTaskCount++ }
  if ($status -eq 'queued' -and [string]$task.approval.status -ne 'rejected') {
    $waitingTaskCount++
  }
}
$codexJobsFile = Join-Path $privateDir 'codex_jobs.json'
$activeCodex = 0
if (Test-Path -LiteralPath $codexJobsFile -PathType Leaf) {
  try { $jobs=Get-Content -LiteralPath $codexJobsFile -Raw | ConvertFrom-Json }
  catch { throw 'Codex job ledger is unreadable. No backup attempted.' }
  foreach ($job in @($jobs)) {
    if ([string]$job.status -in $runningStatuses) { $activeCodex++ }
  }
}
Write-Host "Detected live server: $release" -ForegroundColor Cyan
Write-Host "Running tasks: $activeTaskCount; running Codex jobs: $activeCodex; queued tasks: $waitingTaskCount"
if ($activeTaskCount -ne 0 -or $activeCodex -ne 0) {
  throw 'A worker is executing. Backup deliberately refused; finish running jobs first.'
}
if ($waitingTaskCount -gt 0) {
  Write-Warning 'Queued tasks will be included in the backup. Do not approve or process them during the snapshot.'
}
$originalHelper=Join-Path $PSScriptRoot 'backup_ground_space_state.ps1'
if (-not (Test-Path -LiteralPath $originalHelper -PathType Leaf)) {
  throw 'Verified Ground Space backup helper missing.'
}
$output=@(& $originalHelper -ExpectedRelease $release -Port $Port -StateRoot $StateRoot -BackupRoot $BackupRoot)
if ($output.Count -lt 1) { throw 'Backup helper did not return a location.' }
$backup=[string]$output[-1]
$manifestPath=Join-Path $backup 'BACKUP_MANIFEST.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
  throw "Backup manifest missing: $backup"
}
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([string]$manifest.source_release -ne $release) {
  throw "Backup release did not match the running process. Retained folder: $backup"
}
if (@($manifest.files).Count -ne [int]$manifest.file_count) {
  throw "Manifest file count mismatch. Retained folder: $backup"
}
foreach($entry in @($manifest.files)) {
  $file=Join-Path $backup ([string]$entry.path)
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
    throw "Backup file missing: $($entry.path)"
  }
  $hash=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
  if ($hash -ne [string]$entry.sha256) {
    throw "Backup hash mismatch: $($entry.path)"
  }
}
Write-Host "GS-031 OWNER DATA BACKUP VERIFIED: $backup" -ForegroundColor Green
Write-Host 'Private data stays on the ASUS. Nothing is uploaded to GitHub.' -ForegroundColor Cyan
Write-Host 'Preserve an additional encrypted copy on a separate disk for disaster recovery.'
