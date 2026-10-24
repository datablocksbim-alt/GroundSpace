param(
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$bundled = Join-Path $projectRoot 'runtime\python\python.exe'
$python = if (Test-Path -LiteralPath $bundled) { $bundled } else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) { $command = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $command) { throw 'Python is unavailable. Use the future packaged Community Edition build or install Python 3.11+.' }
    $command.Source
}

Set-Location -LiteralPath $projectRoot
$arguments = @('-m', 'ground_space.webapp', '--port', $Port)
if ($NoBrowser) { $arguments += '--no-browser' }
& $python @arguments
