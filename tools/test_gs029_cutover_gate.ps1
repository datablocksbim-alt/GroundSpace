# Unit checks for the GS-029 activation gate without starting or stopping Ground Space.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot 'activate_gs029_asus.ps1'
$tokens=$null; $errors=$null
$tree=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Release helper has parse errors.' }
$fn=$tree.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'SafeJobs'},$true)
if (-not $fn) { throw 'SafeJobs release gate missing.' }
. ([scriptblock]::Create($fn.Extent.Text))
function Sample([string]$status,[string]$approval){
  [pscustomobject]@{
    codex=[pscustomobject]@{jobs=@()}
    tasks=@([pscustomobject]@{status=$status;approval=[pscustomobject]@{status=$approval}})
  }
}
SafeJobs (Sample 'queued' 'rejected') # Explicitly rejected group work is not executable.
SafeJobs (Sample 'completed' 'approved')
SafeJobs (Sample 'failed' 'approved')
foreach($case in @(@('queued','pending'),@('queued','approved'),@('claimed','approved'),
                 @('running','approved'),@('leased','approved'))) {
  $blocked=$false
  try { SafeJobs (Sample $case[0] $case[1]) } catch { $blocked=$true }
  if (-not $blocked) { throw "Unsafe work was accepted: $($case[0])/$($case[1])" }
}
Write-Host 'GS-029 release gate rejects active queues and permits rejected group replies.'
