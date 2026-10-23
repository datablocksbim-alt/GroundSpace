# GS-030 safe queue release gate tests. No live ASUS access, no production writes.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'activate_gs030_asus.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw 'GS-030 activation script did not parse.' }
foreach ($functionName in @('CanonicalValue','StableJson','Verify','SafeJobs','SafeAllQueueFiles')) {
  $node = $ast.Find({
    param($item)
    $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $item.Name -eq $functionName
  }, $true)
  if (-not $node) { throw "Missing $functionName" }
  . ([scriptblock]::Create($node.Extent.Text))
}
# The production Python process and a restored canary may enumerate object keys
# differently. This must NOT block a release. Content, missing fields and
# message/order changes must still block the release.
$baseline = @'
{
  "backend_release": "GS-029",
  "workspaces": {
    "projects": [{"id":"project-one","name":"Ground Space","path":"D:\\Projects\\Ground Space"}],
    "groups": [{"id":"group-one","project_id":"project-one","approval_modes":{"qwen":"manual","codex":"off"}}]
  },
  "conversations": {
    "room-b": [{"role":"user","content":"hello","timestamp":"T1","nested":{"b":2,"a":1}},
               {"role":"assistant","content":"there","timestamp":"T2"}],
    "room-a": []
  },
  "tasks": [{"task_id":"T1","approval":{"status":"approved","owner":"owner"},"status":"completed"}],
  "collaborations": [],
  "agent_configs": {"schema_version":1,"profiles":{"codex":{"access":["read","review"]}}},
  "codex": {"jobs": [], "project_modes":{"project-one":{"write_enabled":false}}}
}
'@ | ConvertFrom-Json
$restored = @'
{
 "codex":{"project_modes":{"project-one":{"write_enabled":false}},"jobs":[]},
 "agent_configs":{"profiles":{"codex":{"access":["read","review"]}},"schema_version":1},
 "collaborations":[],
 "tasks":[{"status":"completed","approval":{"owner":"owner","status":"approved"},"task_id":"T1"}],
 "conversations":{"room-a":[],"room-b":[
   {"nested":{"a":1,"b":2},"timestamp":"T1","content":"hello","role":"user"},
   {"timestamp":"T2","content":"there","role":"assistant"}]},
 "workspaces":{"groups":[{"approval_modes":{"codex":"off","qwen":"manual"},"project_id":"project-one","id":"group-one"}],
               "projects":[{"path":"D:\\Projects\\Ground Space","name":"Ground Space","id":"project-one"}]},
 "backend_release":"GS-030"
}
'@ | ConvertFrom-Json
Verify $restored $baseline 'GS-030'
function Assert-VerifyReject($item,[string]$category) {
  $blocked = $false
  try { Verify $item $baseline 'GS-030' } catch { $blocked = $true }
  if (-not $blocked) { throw "Unsafe release accepted: $category" }
}
$modified = $restored | ConvertTo-Json -Depth 70 | ConvertFrom-Json
$modified.conversations.'room-b'[0].content = 'changed!'
Assert-VerifyReject $modified 'modified message'
$modified = $restored | ConvertTo-Json -Depth 70 | ConvertFrom-Json
$modified.conversations.'room-b' = @($modified.conversations.'room-b'[1],$modified.conversations.'room-b'[0])
Assert-VerifyReject $modified 'reordered messages'
$modified = $restored | ConvertTo-Json -Depth 70 | ConvertFrom-Json
$modified.conversations.PSObject.Properties.Remove('room-a')
Assert-VerifyReject $modified 'missing conversation'
$modified = $restored | ConvertTo-Json -Depth 70 | ConvertFrom-Json
$modified.workspaces.groups[0].approval_modes.qwen = 'auto'
Assert-VerifyReject $modified 'changed approval settings'
$modified = $restored | ConvertTo-Json -Depth 70 | ConvertFrom-Json
$modified.agent_configs.profiles.codex.access = @('review','read')
Assert-VerifyReject $modified 'changed permission ordering'
$modified = $restored | ConvertTo-Json -Depth 70 | ConvertFrom-Json
$modified.tasks[0].status = 'running'
Assert-VerifyReject $modified 'changed queued task state'
Write-Host 'GS-030 CANONICAL SNAPSHOT PASS: reordered keys allowed, modified values/arrays refused.' -ForegroundColor Green

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
