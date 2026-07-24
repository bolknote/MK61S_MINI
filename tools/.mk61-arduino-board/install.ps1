[CmdletBinding()]
param(
    [string]$Sketchbook,
    [switch]$Check,
    [Alias('h')]
    [switch]$Help
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Show-Usage {
    @'
Install the "MK61s F401 + APP" board into an Arduino IDE sketchbook.

Usage:
  tools\mk61-arduino-board.cmd [-Sketchbook DIR]
  tools\mk61-arduino-board.cmd -Check [-Sketchbook DIR]

Options:
  -Sketchbook DIR  Arduino IDE sketchbook directory
  -Check           only check whether the board is already installed
  -Help            show this help

The installer does not install Arduino CLI.  The STM32 MCU based boards core
2.12.0 must be installed from Arduino IDE's Boards Manager.
'@ | Write-Host
}

function Test-InstalledPlatform {
    param([string]$Path)
    return (
        [IO.File]::Exists((Join-Path $Path 'boards.txt')) -and
        [IO.File]::Exists((Join-Path $Path 'platform.txt')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61-app-postbuild.sh')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61-app-postbuild.ps1')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61_module.ld'))
    )
}

try {
    if ($Help) {
        Show-Usage
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace($Sketchbook)) {
        if (-not [string]::IsNullOrWhiteSpace(
            $env:MK61_ARDUINO_SKETCHBOOK)) {
            $Sketchbook = $env:MK61_ARDUINO_SKETCHBOOK
        } else {
            $documents = [Environment]::GetFolderPath('MyDocuments')
            if ([string]::IsNullOrWhiteSpace($documents)) {
                throw 'Cannot locate the Windows Documents directory.'
            }
            $Sketchbook = Join-Path $documents 'Arduino'
        }
    }

    $sourcePlatform = Join-Path $PSScriptRoot 'hardware\mk61\stm32'
    $target = Join-Path $Sketchbook 'hardware\mk61\stm32'

    if ($Check) {
        if (Test-InstalledPlatform $target) {
            Write-Host 'MK61s F401 + APP is installed in:'
            Write-Host "  $target"
            exit 0
        }
        [Console]::Error.WriteLine(
            "MK61s F401 + APP is not installed in:`n  $target")
        exit 1
    }

    if (-not [IO.File]::Exists(
        (Join-Path $sourcePlatform 'boards.txt')) -or
        -not [IO.File]::Exists(
        (Join-Path $sourcePlatform 'platform.txt'))) {
        throw 'The MK61s board package is incomplete.'
    }

    $targetTools = Join-Path $target 'tools'
    [IO.Directory]::CreateDirectory($targetTools) | Out-Null
    Copy-Item -LiteralPath (Join-Path $sourcePlatform 'boards.txt') `
        -Destination (Join-Path $target 'boards.txt') -Force
    Copy-Item -LiteralPath (Join-Path $sourcePlatform 'platform.txt') `
        -Destination (Join-Path $target 'platform.txt') -Force
    foreach ($name in @(
        'mk61_module.ld',
        'mk61-app-postbuild.sh',
        'mk61-app-postbuild.ps1'
    )) {
        Copy-Item -LiteralPath (Join-Path $sourcePlatform "tools\$name") `
            -Destination (Join-Path $targetTools $name) -Force
    }

    Write-Host 'MK61s F401 + APP installed in:'
    Write-Host "  $target"
    Write-Host ('Restart Arduino IDE, then select Tools > Board > ' +
                'MK61s F401 + APP.')
    Write-Host 'STM32 MCU based boards core 2.12.0 is required.'
} catch {
    [Console]::Error.WriteLine("MK61s Arduino board: $($_.Exception.Message)")
    exit 1
}
