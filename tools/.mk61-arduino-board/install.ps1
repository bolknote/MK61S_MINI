[CmdletBinding()]
param(
    [string]$Sketchbook,
    [Alias('Toolchain')][string]$ToolchainDirectory,
    [switch]$Check,
    [Alias('h')]
    [switch]$Help
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'payload.ps1')

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

    if (-not [string]::IsNullOrWhiteSpace($env:ARDUINO_DIRECTORIES_DATA)) {
        return [IO.Path]::GetFullPath($env:ARDUINO_DIRECTORIES_DATA)
    }
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

function Show-Usage {
    Write-Host 'Install native MK61s F401 + APP and MK61s F411 + APP boards into Arduino IDE.'
    Write-Host 'Options: -Sketchbook DIR, -ToolchainDirectory DIR, -Check, -Help'
    Write-Host 'No STM32 Core, Arduino libraries, Python or host C++ compiler is required.'
    Write-Host 'Compatible GNU Arm GCC in Arduino15 is reused; the pinned compiler is downloaded only when needed.'
    Write-Host 'This installer does not install Arduino CLI; the MK61s board is not in Boards Manager.'
}

function Test-InstalledPlatform {
    param([string]$Path)
    return [IO.File]::Exists((Join-Path $Path 'boards.txt')) -and
        [IO.File]::Exists((Join-Path $Path 'platform.txt'))
}

function Get-Mk61BoardPackageVersion {
    param([string]$PlatformPath)
    $metadata = Join-Path $PlatformPath 'platform.txt'
    if ([IO.File]::Exists($metadata)) {
        foreach ($line in [IO.File]::ReadAllLines($metadata)) {
            if ($line -match '^version=(.+)$') { return $Matches[1].Trim() }
        }
    }
    return 'not installed / unknown'
}

function Test-InstalledPlatformCurrent {
    param([string]$SourcePlatform, [string]$ProjectRoot, [string]$Target)
    return Test-Mk61NativePayload $ProjectRoot $Target
}

function Install-Mk61FontSettingsCompatibility {
    param(
        [string]$Source,
        [string]$Target
    )

    $marker = '# MK61_FONT_SETTINGS_COMPAT_BEGIN'
    if ([IO.File]::Exists($Target)) {
        $existing = [IO.File]::ReadAllText($Target)
        if ($existing.Contains($marker)) {
            return
        }
        if ($existing.Length -gt 0 -and
            -not $existing.EndsWith("`n")) {
            $existing += [Environment]::NewLine
        }
        $compatibility = [IO.File]::ReadAllText($Source)
        [IO.File]::WriteAllText(
            $Target,
            $existing + [Environment]::NewLine + $compatibility,
            [Text.UTF8Encoding]::new($false))
        return
    }
    Copy-Item -LiteralPath $Source -Destination $Target
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
    $fontSettingsCompatibilitySource = Join-Path $PSScriptRoot `
        'font-settings-compat.boards.local.txt'
    $projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    $target = Join-Path $Sketchbook 'hardware\mk61\stm32'
    $sourceVersion = Get-Mk61BoardPackageVersion $sourcePlatform
    $installedVersion = Get-Mk61BoardPackageVersion $target
    $installCommand = '& "' + (Join-Path $projectRoot 'tools\mk61-arduino-board.cmd') +
        '" -Sketchbook "' + $Sketchbook + '"'
    $fontSettingsCompatibilityTarget = Join-Path $target 'boards.local.txt'
    $installFontSettingsCompatibility =
        [IO.File]::Exists((Join-Path $target 'boards.txt'))
    if ([IO.File]::Exists($fontSettingsCompatibilityTarget) -and
        [IO.File]::ReadAllText($fontSettingsCompatibilityTarget).Contains(
            '# MK61_FONT_SETTINGS_COMPAT_BEGIN')) {
        $installFontSettingsCompatibility = $true
    }

    if ($Check) {
        Write-Host "MK61s board package: installed $installedVersion; project $sourceVersion"
        if (Test-InstalledPlatform $target) {
            if (-not (Test-InstalledPlatformCurrent `
                    $sourcePlatform $projectRoot $target)) {
                [Console]::Error.WriteLine(
                    "MK61s Arduino boards are installed but stale in:`n  $target`n" +
                    "Close Arduino IDE, run in PowerShell:`n  $installCommand`n" +
                    'Then restart Arduino IDE.')
                exit 1
            }
            Write-Host 'MK61s F401/F411 boards are installed in:'
            Write-Host "  $target"
            Write-Host "Arduino IDE sketchbook source: $sketchbookSource"
            if (-not [string]::IsNullOrWhiteSpace($buildCacheDirectory)) {
                Write-Host "Arduino IDE build cache: $buildCacheDirectory"
            }
            Write-Host 'Do not search for this manually installed board in Boards Manager; use Board Selector / Tools > Board.'
    Write-Host 'Runtime and header SDK belong to MK61s; STM32 Core is not required.'
            exit 0
        }
        [Console]::Error.WriteLine(
            "MK61s F401/F411 board installation is missing or incomplete in:`n  $target`n" +
            "Close Arduino IDE, run in PowerShell:`n  $installCommand`n" +
            'Then restart Arduino IDE.')
        exit 1
    }

    Install-Mk61NativePayload $projectRoot $target $ToolchainDirectory $dataDirectory
    if ($installFontSettingsCompatibility) {
        Install-Mk61FontSettingsCompatibility $fontSettingsCompatibilitySource $fontSettingsCompatibilityTarget
    }
    if (-not (Test-InstalledPlatformCurrent $sourcePlatform $projectRoot $target)) {
        throw "installed native board verification failed: $target"
    }
    Write-Host 'MK61s F401/F411 boards installed in:'
    Write-Host "  $target"
    Write-Host "MK61s board package version: $sourceVersion"
    Write-Host "Arduino IDE sketchbook source: $sketchbookSource"
    if (-not [string]::IsNullOrWhiteSpace($buildCacheDirectory)) {
        Write-Host "Arduino IDE build cache: $buildCacheDirectory"
    }
    if ($env:OS -eq 'Windows_NT') { Write-Host 'Windows build/upload tools: PowerShell/.NET (no Python).' }
    Write-Host 'Verified uploader: mk61Upload (standalone DFU + automatic /System install).'
    if ($installFontSettingsCompatibility) {
        Write-Host 'Accepted obsolete Arduino IDE font options saved by an earlier installation.'
    }
    Write-Host "Restart Arduino IDE, then select MK61s F401 + APP ($sourceVersion) or MK61s F411 + APP ($sourceVersion)."
    Write-Host 'Do not search for this manually installed board in Boards Manager; use Board Selector / Tools > Board.'
    Write-Host 'Runtime and header SDK belong to MK61s; STM32 Core is not required.'
} catch {
    [Console]::Error.WriteLine("MK61s Arduino board: $($_.Exception.Message)")
    exit 1
}
