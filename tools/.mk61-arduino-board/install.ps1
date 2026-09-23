[CmdletBinding()]
param(
    [string]$Sketchbook,
    [switch]$Check,
    [Alias('h')]
    [switch]$Help
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$requiredStm32Core = '2.12.0'

function ConvertFrom-ArduinoYamlScalar {
    param([string]$Value)

    $result = $Value.Trim()
    if ($result.Length -lt 2) {
        return $result
    }
    $first = $result.Substring(0, 1)
    $last = $result.Substring($result.Length - 1, 1)
    if ($first -eq "'" -and $last -eq "'") {
        return $result.Substring(1, $result.Length - 2).Replace("''", "'")
    }
    if ($first -eq '"' -and $last -eq '"') {
        try {
            return (ConvertFrom-Json -InputObject $result)
        } catch {
            return $result.Substring(1, $result.Length - 2)
        }
    }
    return $result
}

function Get-ArduinoConfigDirectory {
    param(
        [string]$ConfigPath,
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($ConfigPath) -or
        -not [IO.File]::Exists($ConfigPath)) {
        return $null
    }

    $insideDirectories = $false
    $pattern = '^\s+' + [regex]::Escape($Name) + ':\s*(.*?)\s*$'
    foreach ($line in [IO.File]::ReadAllLines($ConfigPath)) {
        if ($line -match '^directories:\s*$') {
            $insideDirectories = $true
            continue
        }
        if ($insideDirectories -and $line -match '^\S') {
            break
        }
        if ($insideDirectories -and $line -match $pattern) {
            return ConvertFrom-ArduinoYamlScalar $Matches[1]
        }
    }
    return $null
}

function Get-ArduinoConfigBuildCacheDirectory {
    param([string]$ConfigPath)

    if ([string]::IsNullOrWhiteSpace($ConfigPath) -or
        -not [IO.File]::Exists($ConfigPath)) {
        return $null
    }

    $insideBuildCache = $false
    foreach ($line in [IO.File]::ReadAllLines($ConfigPath)) {
        if ($line -match '^build_cache:\s*$') {
            $insideBuildCache = $true
            continue
        }
        if ($insideBuildCache -and $line -match '^\S') {
            break
        }
        if ($insideBuildCache -and $line -match '^\s+path:\s*(.*?)\s*$') {
            return ConvertFrom-ArduinoYamlScalar $Matches[1]
        }
    }
    return $null
}

function Test-Mk61AsciiPath {
    param([string]$Path)

    return (-not [string]::IsNullOrWhiteSpace($Path) -and
            -not [regex]::IsMatch($Path, '[^\x20-\x7e]'))
}

function Get-Mk61SafeBuildCacheDirectory {
    $publicDirectory = $env:PUBLIC
    if (Test-Mk61AsciiPath $publicDirectory) {
        $publicDirectory = Join-Path $publicDirectory 'Documents'
    } else {
        $systemDrive = $env:SystemDrive
        if ([string]::IsNullOrWhiteSpace($systemDrive)) {
            $systemDrive = 'C:'
        }
        $publicDirectory = Join-Path $systemDrive 'Users\Public\Documents'
    }
    if (-not (Test-Mk61AsciiPath $publicDirectory)) {
        throw 'Cannot construct an ASCII-only public build-cache path.'
    }

    $identity = [Environment]::GetFolderPath('UserProfile')
    if ([string]::IsNullOrWhiteSpace($identity)) {
        $identity = "$($env:USERDOMAIN)\$($env:USERNAME)"
    }
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($identity))
    } finally {
        $sha256.Dispose()
    }
    $token = [BitConverter]::ToString($digest, 0, 6).Replace('-', '').ToLower()
    return Join-Path $publicDirectory "MK61Arduino\build-cache-$token"
}

function Set-ArduinoConfigBuildCacheDirectory {
    param(
        [string]$ConfigPath,
        [string]$Directory
    )

    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        throw 'Cannot locate the Arduino IDE configuration file.'
    }
    $parent = Split-Path -Parent $ConfigPath
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        [IO.Directory]::CreateDirectory($parent) | Out-Null
    }

    $lines = New-Object 'System.Collections.Generic.List[string]'
    if ([IO.File]::Exists($ConfigPath)) {
        foreach ($line in [IO.File]::ReadAllLines($ConfigPath)) {
            $lines.Add($line)
        }
    }

    $sectionIndex = -1
    $pathIndex = -1
    $insertIndex = -1
    for ($index = 0; $index -lt $lines.Count; ++$index) {
        if ($lines[$index] -match '^build_cache:\s*$') {
            $sectionIndex = $index
            $insertIndex = $index + 1
            for ($child = $index + 1; $child -lt $lines.Count; ++$child) {
                if ($lines[$child] -match '^\S') {
                    $insertIndex = $child
                    break
                }
                $insertIndex = $child + 1
                if ($lines[$child] -match '^\s+path:\s*') {
                    $pathIndex = $child
                }
            }
            break
        }
    }

    $quoted = "'" + $Directory.Replace("'", "''") + "'"
    $pathLine = "  path: $quoted"
    if ($pathIndex -ge 0) {
        $lines[$pathIndex] = $pathLine
    } elseif ($sectionIndex -ge 0) {
        $lines.Insert($insertIndex, $pathLine)
    } else {
        if ($lines.Count -gt 0 -and
            -not [string]::IsNullOrWhiteSpace($lines[$lines.Count - 1])) {
            $lines.Add('')
        }
        $lines.Add('build_cache:')
        $lines.Add($pathLine)
    }
    [IO.File]::WriteAllLines(
        $ConfigPath, $lines.ToArray(), [Text.UTF8Encoding]::new($false))
}

function Get-ArduinoIdeConfigPath {
    if (-not [string]::IsNullOrWhiteSpace(
        $env:MK61_ARDUINO_CONFIG_FILE)) {
        return [IO.Path]::GetFullPath($env:MK61_ARDUINO_CONFIG_FILE)
    }
    $profile = [Environment]::GetFolderPath('UserProfile')
    if ([string]::IsNullOrWhiteSpace($profile)) {
        return $null
    }
    return Join-Path $profile '.arduinoIDE\arduino-cli.yaml'
}

function Get-DefaultArduinoDataDirectory {
    param([string]$ConfigPath)

    $configured = Get-ArduinoConfigDirectory $ConfigPath 'data'
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return [IO.Path]::GetFullPath($configured)
    }
    $localData = [Environment]::GetFolderPath('LocalApplicationData')
    if ([string]::IsNullOrWhiteSpace($localData)) {
        return $null
    }
    return Join-Path $localData 'Arduino15'
}

function Get-DefaultArduinoBuildCacheDirectory {
    param([string]$ConfigPath)

    $configured = Get-ArduinoConfigBuildCacheDirectory $ConfigPath
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        $expanded = [Environment]::ExpandEnvironmentVariables($configured)
        return [IO.Path]::GetFullPath($expanded)
    }
    $localData = [Environment]::GetFolderPath('LocalApplicationData')
    if ([string]::IsNullOrWhiteSpace($localData)) {
        return $null
    }
    return Join-Path $localData 'arduino'
}

function Initialize-Mk61ArduinoBuildCache {
    param(
        [string]$ConfigPath,
        [switch]$ReadOnly
    )

    $current = Get-DefaultArduinoBuildCacheDirectory $ConfigPath
    if (($env:OS -ne 'Windows_NT') -or
        (Test-Mk61AsciiPath $current)) {
        return $current
    }
    if ($ReadOnly) {
        Write-Host ('WARNING: Arduino IDE build cache contains non-ASCII ' +
                    'characters:')
        Write-Host "  $current"
        Write-Host ('Run tools\mk61-arduino-board.cmd without -Check to ' +
                    'select a safe build-cache directory for GNU Arm LTO.')
        return $current
    }

    $safe = Get-Mk61SafeBuildCacheDirectory
    [IO.Directory]::CreateDirectory($safe) | Out-Null
    Set-ArduinoConfigBuildCacheDirectory $ConfigPath $safe
    Write-Host ('Arduino IDE build cache contained non-ASCII characters; ' +
                'selected a separate ASCII-only directory:')
    Write-Host "  $safe"
    return $safe
}

function Write-Stm32CoreStatus {
    param([string]$DataDirectory)

    if ([string]::IsNullOrWhiteSpace($DataDirectory)) {
        Write-Host ("WARNING: cannot locate Arduino IDE data directory; " +
                    "cannot verify STM32 core $requiredStm32Core.")
        return
    }
    $corePath = Join-Path $DataDirectory (
        "packages\STMicroelectronics\hardware\stm32\$requiredStm32Core")
    if ([IO.File]::Exists((Join-Path $corePath 'platform.txt'))) {
        Write-Host "STM32 MCU based boards $requiredStm32Core found in:"
        Write-Host "  $corePath"
        return
    }
    Write-Host ("WARNING: STM32 MCU based boards $requiredStm32Core was not " +
                "found in:")
    Write-Host "  $DataDirectory"
    Write-Host ('Install that exact version in Arduino IDE Boards Manager ' +
                'before compiling.')
}

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
2.12.0 must be installed from Arduino IDE's Boards Manager.  The MK61s board
itself appears in Board Selector / Tools > Board, not in Boards Manager.
'@ | Write-Host
}

function Test-InstalledPlatform {
    param([string]$Path)
    return (
        [IO.File]::Exists((Join-Path $Path 'boards.txt')) -and
        [IO.File]::Exists((Join-Path $Path 'platform.txt')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61-app-postbuild.sh')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61-app-postbuild.ps1')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61-app-upload.ps1')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61_firmware_seal.cpp')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\resident_firmware_format.hpp')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\rust_types.h')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\seal-firmware.ps1')) -and
        [IO.File]::Exists((Join-Path $Path 'tools\mk61_module.ld'))
    )
}

try {
    if ($Help) {
        Show-Usage
        exit 0
    }
    $configPath = Get-ArduinoIdeConfigPath
    $sketchbookSource = 'command line'
    if ([string]::IsNullOrWhiteSpace($Sketchbook)) {
        if (-not [string]::IsNullOrWhiteSpace(
            $env:MK61_ARDUINO_SKETCHBOOK)) {
            $Sketchbook = $env:MK61_ARDUINO_SKETCHBOOK
            $sketchbookSource = 'MK61_ARDUINO_SKETCHBOOK'
        } else {
            $configuredSketchbook = Get-ArduinoConfigDirectory `
                $configPath 'user'
            if (-not [string]::IsNullOrWhiteSpace($configuredSketchbook)) {
                $Sketchbook = $configuredSketchbook
                $sketchbookSource = $configPath
            } else {
                $documents = [Environment]::GetFolderPath('MyDocuments')
                if ([string]::IsNullOrWhiteSpace($documents)) {
                    throw 'Cannot locate the Windows Documents directory.'
                }
                $Sketchbook = Join-Path $documents 'Arduino'
                $sketchbookSource = 'Windows Documents fallback'
            }
        }
    }
    $Sketchbook = [IO.Path]::GetFullPath($Sketchbook)
    $dataDirectory = Get-DefaultArduinoDataDirectory $configPath
    $buildCacheDirectory = Initialize-Mk61ArduinoBuildCache `
        $configPath -ReadOnly:$Check

    $sourcePlatform = Join-Path $PSScriptRoot 'hardware\mk61\stm32'
    $projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    $target = Join-Path $Sketchbook 'hardware\mk61\stm32'

    if ($Check) {
        if (Test-InstalledPlatform $target) {
            Write-Host 'MK61s F401 + APP is installed in:'
            Write-Host "  $target"
            Write-Host "Arduino IDE sketchbook source: $sketchbookSource"
            if (-not [string]::IsNullOrWhiteSpace($buildCacheDirectory)) {
                Write-Host "Arduino IDE build cache: $buildCacheDirectory"
            }
            Write-Stm32CoreStatus $dataDirectory
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
        'mk61-app-postbuild.ps1',
        'mk61-app-upload.ps1'
    )) {
        Copy-Item -LiteralPath (Join-Path $sourcePlatform "tools\$name") `
            -Destination (Join-Path $targetTools $name) -Force
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot `
        'tools/.mk61-firmware-seal/mk61_firmware_seal.cpp') `
        -Destination (Join-Path $targetTools 'mk61_firmware_seal.cpp') -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot `
        'code/resident_firmware_format.hpp') `
        -Destination (Join-Path $targetTools 'resident_firmware_format.hpp') -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'code/rust_types.h') `
        -Destination (Join-Path $targetTools 'rust_types.h') -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot 'tools/seal-firmware.ps1') `
        -Destination (Join-Path $targetTools 'seal-firmware.ps1') -Force

    Write-Host 'MK61s F401 + APP installed in:'
    Write-Host "  $target"
    Write-Host "Arduino IDE sketchbook source: $sketchbookSource"
    if (-not [string]::IsNullOrWhiteSpace($buildCacheDirectory)) {
        Write-Host "Arduino IDE build cache: $buildCacheDirectory"
    }
    Write-Stm32CoreStatus $dataDirectory
    Write-Host 'Close every Arduino IDE window, then start Arduino IDE again.'
    Write-Host ('Open Board Selector (or Tools > Board > Select Other Board ' +
                'and Port) and search for the exact name:')
    Write-Host '  MK61s F401 + APP'
    Write-Host ('Do not search for this manually installed board in Boards ' +
                'Manager; only the STM32 core is listed there.')
} catch {
    [Console]::Error.WriteLine("MK61s Arduino board: $($_.Exception.Message)")
    exit 1
}
