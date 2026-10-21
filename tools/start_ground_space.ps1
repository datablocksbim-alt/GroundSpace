param(
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = 'D:\000_AI Project\AI Agents Datablocks\runtime\python\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Data Blocks Python runtime not found: $python"
}

Set-Location -LiteralPath $projectRoot
$arguments = @('-m', 'ground_space.webapp', '--port', $Port)
if ($NoBrowser) { $arguments += '--no-browser' }
& $python @arguments
