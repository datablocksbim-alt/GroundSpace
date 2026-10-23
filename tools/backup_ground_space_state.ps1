# Create a consistency-checked snapshot of the owner-local Ground Space state.
# This does not stop or mutate the running service. It succeeds only when the
# live release matches, no Codex job is running, and source hashes remain stable
# for the complete copy window.
[CmdletBinding()]
param(
    [string]$ExpectedRelease = 'GS-021',
    [ValidateRange(1025, 65535)][int]$Port = 8765,
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace'),
    [string]$BackupRoot = (Join-Path $env:LOCALAPPDATA 'DataBlocks\GroundSpace-Backups')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath((Join-Path $StateRoot 'private')).TrimEnd('\')
if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Ground Space private state is missing: $source"
}
$live = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/bootstrap" -TimeoutSec 8
if ([string]$live.backend_release -ne $ExpectedRelease) {
    throw "Expected live release $ExpectedRelease; found '$($live.backend_release)'."
}
$running = @($live.codex.jobs | Where-Object { $_.status -eq 'running' })
if ($running.Count -gt 0) { throw 'Codex jobs are running; snapshot refused.' }

function Get-StateManifest([string]$Root) {
    @(
        Get-ChildItem -LiteralPath $Root -File -Recurse -Force |
            Where-Object { $_.Name -notlike '*.tmp' -and $_.Name -ne 'BACKUP_MANIFEST.json' } |
            ForEach-Object {
                [pscustomobject]@{
                    path = $_.FullName.Substring($Root.Length).TrimStart('\')
                    length = $_.Length
                    sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                }
            } | Sort-Object path
    )
}

$before = Get-StateManifest $source
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$destination = Join-Path $BackupRoot ("$ExpectedRelease-$stamp")
New-Item -ItemType Directory -Path $destination -Force:$false | Out-Null
Get-ChildItem -LiteralPath $source -Force |
    Copy-Item -Destination $destination -Recurse -Force
$after = Get-StateManifest $source
$copied = Get-StateManifest $destination

$beforeJson = $before | ConvertTo-Json -Compress
if ($beforeJson -ne ($after | ConvertTo-Json -Compress)) {
    throw "Source changed during snapshot. Do not use the retained diagnostic copy: $destination"
}
if ($beforeJson -ne ($copied | ConvertTo-Json -Compress)) {
    throw "Copied hashes differ. Do not use the retained diagnostic copy: $destination"
}

$jsonFiles = @(Get-ChildItem -LiteralPath $destination -File -Recurse -Filter '*.json')
foreach ($file in $jsonFiles) {
    $null = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
}
$jsonlRecords = 0
foreach ($file in @(Get-ChildItem -LiteralPath $destination -File -Recurse -Filter '*.jsonl')) {
    foreach ($line in Get-Content -LiteralPath $file.FullName) {
        if ($line.Trim()) { $null = $line | ConvertFrom-Json; $jsonlRecords++ }
    }
}

$metadata = [pscustomobject]@{
    schema_version = 1
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    source_release = $ExpectedRelease
    source_path = $source
    file_count = $before.Count
    jsonl_record_count = $jsonlRecords
    files = $before
}
$metadata | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $destination 'BACKUP_MANIFEST.json') -Encoding utf8
Write-Host "CONSISTENT BACKUP PASS: $destination" -ForegroundColor Green
Write-Output $destination
