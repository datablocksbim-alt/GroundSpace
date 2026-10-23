# GS-030 safe queue release gate tests. No live ASUS access, no production writes.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'activate_gs030_asus.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw 'GS-030 activation script did not parse.' }
foreach ($functionName in @('SafeJobs','SafeAllQueueFiles')) {
  $node = $ast.Find({
    param($item)
    $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $item.Name -eq $functionName
  }, $true)
  if (-not $node) { throw "Missing $functionName" }
  . ([scriptblock]::Create($node.Extent.Text))
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('gs030-queue-gate-'+[guid]::NewGuid().ToString('N'))
$state = $root
$queueDir = Join-Path $state 'private\queue'
New-Item -ItemType Directory -Force -Path $queueDir | Out-Null
function Set-Record([string]$status,[string]$approval) {
  [pscustomobject]@{
    task_id='GS-test'
    status=$status
    approval=[pscustomobject]@{status=$approval}
  } | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $queueDir 'GS-test.json') -Encoding UTF8
}
function Check-Blocked([string]$status,[string]$approval) {
  Set-Record $status $approval
  $refused = $false
  try { SafeAllQueueFiles } catch { $refused = $true }
  if (-not $refused) { throw "Unsafe task was allowed: $status, $approval" }
}
try {
  Set-Record 'completed' 'approved'
  SafeAllQueueFiles
  Set-Record 'failed' 'approved'
  SafeAllQueueFiles
  Set-Record 'queued' 'rejected'
  SafeAllQueueFiles
  foreach ($case in @(
      @('queued','approved'), @('queued','pending'), @('running','approved'),
      @('claimed','approved'), @('retry_pending','approved'), @('leased','approved'))) {
    Check-Blocked $case[0] $case[1]
  }
  Set-Content -LiteralPath (Join-Path $queueDir 'GS-test.json') -Value '{' -Encoding UTF8
  $refused = $false
  try { SafeAllQueueFiles } catch { $refused = $true }
  if (-not $refused) { throw 'Malformed queue record must block cutover.' }
  Remove-Item (Join-Path $queueDir 'GS-test.json')
  foreach ($case in @(
      @('queued','approved'), @('running','approved'), @('queued','pending'))) {
    $item=[pscustomobject]@{
      tasks=@([pscustomobject]@{
        status=$case[0]; approval=[pscustomobject]@{status=$case[1]}
      })
      codex=[pscustomobject]@{jobs=@()}
    }
    $blocked=$false
    try { SafeJobs $item } catch { $blocked=$true }
    if (-not $blocked) { throw 'Snapshot gate allowed active task.' }
  }
  Write-Host 'GS-030 CUTOVER SAFETY PASS: active tasks blocked; completed/rejected work preserved.' -ForegroundColor Green
}
finally {
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
