#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BuildPath,
    [string]$ResidentElf,
    [string]$CompileCommands,
    [string]$OutputDirectory,
    [string]$CatalogDirectory,
    [string]$ModulePacker,
    [ValidateSet('0', '1')][string]$Graphics = '1',
    [ValidateSet('0', '1')][string]$UiFonts = '1',
    [ValidateSet('0', '1')][string]$Focal = '1',
    [ValidateSet('0', '1')][string]$Basic = '1',
    [ValidateSet('0', '1')][string]$Wbmp = '1',
    [ValidateSet('0', '1')][string]$Markdown = '1',
    [ValidateSet('0', '1')][string]$Chip8 = '1',
    [ValidateSet('0', '1')][string]$Setup = '1',
    [ValidateSet('0', '1')][string]$UsbDisk = '1',
    [ValidateSet('0', '1')][string]$Explorer = '0',
    [ValidateSet('0', '1')][string]$LocalFloatMath = '0',
    [switch]$KeepBuild
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Stop-SystemAppsBuild {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s System APP: $Message"
}

function Find-SingleArtifact {
    param([string]$Directory, [string]$Extension, [string]$Description)
    $items = @(Get-ChildItem -LiteralPath $Directory -File |
        Where-Object { $_.Extension -ieq $Extension })
    if ($items.Count -ne 1) {
        Stop-SystemAppsBuild (
            "expected one $Description in $Directory, found $($items.Count)")
    }
    return $items[0].FullName
}

function Get-PythonInterpreter {
    foreach ($name in @('python3', 'python')) {
        $command = Get-Command $name -CommandType Application `
            -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) { return $command.Source }
    }
    Stop-SystemAppsBuild 'python3 is required to build APP'
}

function Get-ArmToolchainFromDatabase {
    param([string]$Path)
    if (-not [IO.File]::Exists($Path)) {
        Stop-SystemAppsBuild "compile database not found: $Path"
    }
    $entries = @(ConvertFrom-Json -InputObject (
        [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)))
    foreach ($entry in $entries) {
        $compiler = $null
        $argumentsProperty = $entry.PSObject.Properties['arguments']
        $commandProperty = $entry.PSObject.Properties['command']
        if ($null -ne $argumentsProperty -and
            @($argumentsProperty.Value).Count -gt 0) {
            $compiler = [string]@($argumentsProperty.Value)[0]
        } elseif ($null -ne $commandProperty -and
                  -not [string]::IsNullOrWhiteSpace(
                      [string]$commandProperty.Value)) {
            $command = [string]$commandProperty.Value
            if ($command -match '^"([^"]+)"') {
                $compiler = $Matches[1]
            } elseif ($command -match '^(\S+)') {
                $compiler = $Matches[1]
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($compiler)) {
            $candidate = $compiler
            if (-not [IO.File]::Exists($candidate) -and
                [IO.File]::Exists("$candidate.exe")) {
                $candidate = "$candidate.exe"
            }
            if ([IO.File]::Exists($candidate) -and
                [IO.Path]::GetFileName($candidate) -match
                    '^arm-none-eabi-(?:gcc|g\+\+)(?:\.exe)?$') {
                return [IO.Path]::GetDirectoryName(
                    [IO.Path]::GetFullPath($candidate))
            }
        }
    }
    Stop-SystemAppsBuild (
        "ARM compiler is missing from compile database: $Path")
}

try {
    # Kept for command-line compatibility. The common builder owns its private
    # temporary directory and always removes it after atomic publish.
    $null = $KeepBuild
    $BuildPath = [IO.Path]::GetFullPath($BuildPath)
    if (-not [IO.Directory]::Exists($BuildPath)) {
        Stop-SystemAppsBuild "resident build directory not found: $BuildPath"
    }
    if ([string]::IsNullOrWhiteSpace($ResidentElf)) {
        $ResidentElf = Find-SingleArtifact $BuildPath '.elf' 'resident ELF'
    }
    if ([string]::IsNullOrWhiteSpace($CompileCommands)) {
        $CompileCommands = Join-Path $BuildPath 'compile_commands.json'
    }
    if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
        $appsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
        $OutputDirectory = Join-Path $appsRoot 'System'
    }

    $projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    if ($env:OS -eq 'Windows_NT') {
        if (-not [string]::IsNullOrWhiteSpace($ModulePacker)) {
            Stop-SystemAppsBuild (
                '-ModulePacker is not used on Windows; the PowerShell/.NET ' +
                'packer is built in')
        }
        $builder = Join-Path $projectRoot `
            'tools/build-system-app-bundle.ps1'
        $toolchain = Get-ArmToolchainFromDatabase `
            ([IO.Path]::GetFullPath($CompileCommands))
        $arguments = @(
            '-NoLogo', '-NoProfile', '-File', $builder,
            '-ResidentElf', [IO.Path]::GetFullPath($ResidentElf),
            '-ArmToolchainBin', $toolchain,
            '-OutputDirectory', [IO.Path]::GetFullPath($OutputDirectory),
            '-Graphics', $Graphics, '-UiFonts', $UiFonts,
            '-Focal', $Focal, '-Basic', $Basic, '-Wbmp', $Wbmp,
            '-Markdown', $Markdown, '-Chip8', $Chip8,
            '-Setup', $Setup, '-UsbDisk', $UsbDisk,
            '-Explorer', $Explorer, '-LocalFloatMath', $LocalFloatMath)
        if (-not [string]::IsNullOrWhiteSpace($CatalogDirectory)) {
            $arguments += @(
                '-CatalogDirectory', [IO.Path]::GetFullPath($CatalogDirectory))
        }
        $powerShell = (Get-Process -Id $PID).Path
        & $powerShell @arguments
    } else {
        $arguments = @(
            (Join-Path $projectRoot 'tools/build_system_app_bundle.py'),
            '--resident-elf', [IO.Path]::GetFullPath($ResidentElf),
            '--compile-commands', [IO.Path]::GetFullPath($CompileCommands),
            '--output-dir', [IO.Path]::GetFullPath($OutputDirectory),
            '--graphics', $Graphics, '--ui-fonts', $UiFonts,
            '--focal', $Focal, '--basic', $Basic, '--wbmp', $Wbmp,
            '--markdown', $Markdown, '--chip8', $Chip8,
            '--setup', $Setup, '--usbdisk', $UsbDisk,
            '--explorer', $Explorer,
            '--local-float-math', $LocalFloatMath)
        if (-not [string]::IsNullOrWhiteSpace($CatalogDirectory)) {
            $arguments += @(
                '--catalog-dir', [IO.Path]::GetFullPath($CatalogDirectory))
        }
        if (-not [string]::IsNullOrWhiteSpace($ModulePacker)) {
            $arguments += @('--packer', [IO.Path]::GetFullPath($ModulePacker))
        }
        $python = Get-PythonInterpreter
        & $python @arguments
    }
    if ($LASTEXITCODE -ne 0) {
        Stop-SystemAppsBuild "unified builder failed with exit code $LASTEXITCODE"
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
