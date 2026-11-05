function Get-Mk61NativePayloadPairs {
    param([string]$ProjectRoot, [string]$Target)
    . (Join-Path $ProjectRoot 'tools/firmware/stm32/sdk.ps1')
    $sdk = Get-NativeSdkPath $ProjectRoot (Join-Path $ProjectRoot 'third_party/stm32f4')
    $metadata = ConvertFrom-Json ([IO.File]::ReadAllText(
        (Join-Path $ProjectRoot 'tools/arduino/payload.json')))
    if ($metadata.schema -ne 1) { throw 'unsupported Arduino native payload schema' }
    $files = @{}
    foreach ($entry in $metadata.files.PSObject.Properties) {
        # This Unix sealer is never used by the Windows build/upload path.
        if ($env:OS -eq 'Windows_NT' -and $entry.Value -eq 'tools/seal-firmware-elf.py') { continue }
        $files[[string]$entry.Name] = [string]$entry.Value
    }
    $sdkManifest = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $sdk 'manifest.json')))
    foreach ($name in @('manifest.json') + @($sdkManifest.files.PSObject.Properties.Name)) {
        $files["third_party/stm32f4/$name"] = "system/stm32f4/$name"
    }
    foreach ($source in $files.Keys) {
        $destination = [string]$files[$source]
        foreach ($name in @($source, $destination)) {
            if ($name -match '(^/|(^|/)\.\.(/|$)|\\|:)') { throw "invalid native payload path: $name" }
        }
        [pscustomobject]@{ Source = Join-Path $ProjectRoot $source; Target = Join-Path $Target $destination }
    }
}

function Assert-Mk61CompilerHeaders {
    param([string]$Bin)
    # A relocated or incomplete GCC can report the right version while
    # failing to find its target C++ headers, particularly on Windows.
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    "#include <cstdlib>`n#include <cstdint>" | & (Join-Path $Bin "arm-none-eabi-g++$suffix") `
        -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard `
        -x c++ -std=gnu++17 -fsyntax-only - 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GNU Arm C++ header probe failed: $Bin" }
}

function Find-Mk61ArduinoCompiler {
    param([string]$ProjectRoot, [string]$Version, [string]$DataDirectory)
    if ([string]::IsNullOrWhiteSpace($DataDirectory)) {
        $DataDirectory = $env:ARDUINO_DIRECTORIES_DATA
    }
    if ([string]::IsNullOrWhiteSpace($DataDirectory)) {
        $DataDirectory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Arduino15'
    }
    $packages = Join-Path $DataDirectory 'packages'
    if (-not [IO.Directory]::Exists($packages)) { return }
    # Inspect only package/tool/version directories, never recurse through a Core.
    foreach ($vendor in Get-ChildItem -LiteralPath $packages -Directory -ErrorAction SilentlyContinue | Sort-Object Name) {
        $tools = Join-Path $vendor.FullName 'tools'
        if (-not [IO.Directory]::Exists($tools)) { continue }
        foreach ($tool in Get-ChildItem -LiteralPath $tools -Directory -ErrorAction SilentlyContinue | Sort-Object Name) {
            foreach ($candidate in Get-ChildItem -LiteralPath $tool.FullName -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending) {
                try {
                    $bin = Get-NativeGnuArmBin $ProjectRoot $Version $candidate.FullName
                    Assert-NativeGnuArmVersion $bin $Version 2>$null
                    Assert-Mk61CompilerHeaders $bin
                    return $bin
                } catch {
                    # Wrong version, incomplete tools, unsafe Windows path or
                    # a compiler for another host: try the next installation.
                }
            }
        }
    }
}

function Get-Mk61NativeCompiler {
    param([string]$ProjectRoot, [string]$Target, [string]$Explicit,
        [switch]$Install, [string]$ArduinoDataDirectory)
    . (Join-Path $ProjectRoot 'tools/firmware/stm32/sdk.ps1')
    $version = (ConvertFrom-Json ([IO.File]::ReadAllText(
        (Join-Path $ProjectRoot 'tools/firmware/stm32/toolchain-lock.json')))).version
    $selected = $Explicit
    if ($Install -and [string]::IsNullOrWhiteSpace($selected)) { $selected = $env:MK61_ARDUINO_TOOLCHAIN }
    if ($Install -and [string]::IsNullOrWhiteSpace($selected)) { $selected = $env:MK61_GCC_TOOLCHAIN }
    $local = Join-Path $Target 'platform.local.txt'
    if ([string]::IsNullOrWhiteSpace($selected) -and [IO.File]::Exists($local)) {
        foreach ($line in [IO.File]::ReadAllLines($local)) {
            if ($line -match '^compiler\.path=(.+)$') {
                $registered = $Matches[1]
                if (-not $Install) { $selected = $registered }
                else {
                    try {
                        $registeredBin = Get-NativeGnuArmBin $ProjectRoot $version $registered
                        Assert-NativeGnuArmVersion $registeredBin $version 2>$null
                        Assert-Mk61CompilerHeaders $registeredBin
                        $selected = $registeredBin
                    } catch { }
                }
            }
        }
    }
    if ($Install -and [string]::IsNullOrWhiteSpace($selected)) {
        $selected = Find-Mk61ArduinoCompiler $ProjectRoot $version $ArduinoDataDirectory
        if (-not [string]::IsNullOrWhiteSpace($selected)) {
            Write-Host "Reusing GNU Arm GCC from Arduino: $selected"
        }
    }
    if ([string]::IsNullOrWhiteSpace($selected)) {
        $installRoot = Get-NativeGnuArmInstallRoot (Join-Path $Target 'tools/toolchains')
        $selected = Join-Path $installRoot "xpack-arm-none-eabi-gcc-$version"
        if (-not [IO.Directory]::Exists($selected)) {
            if (-not $Install) { throw 'native GNU Arm compiler is missing; reinstall the MK61s board' }
            $powerShell = (Get-Process -Id $PID).Path
            & $powerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $ProjectRoot 'tools/firmware/stm32/install_gcc_dependencies.ps1') -InstallRoot $installRoot | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "GNU Arm installation failed ($LASTEXITCODE)" }
        }
    }
    $binary = Get-NativeGnuArmBin $ProjectRoot $version $selected
    Assert-NativeGnuArmVersion $binary $version
    return $binary
}

function Install-Mk61NativePayload {
    param([string]$ProjectRoot, [string]$Target, [string]$ToolchainDirectory,
        [string]$ArduinoDataDirectory)
    foreach ($pair in Get-Mk61NativePayloadPairs $ProjectRoot $Target) {
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($pair.Target)) | Out-Null
        Copy-Item -LiteralPath $pair.Source -Destination $pair.Target -Force
    }
    $binary = Get-Mk61NativeCompiler $ProjectRoot $Target $ToolchainDirectory -Install `
        -ArduinoDataDirectory $ArduinoDataDirectory
    $local = Join-Path $Target 'platform.local.txt'
    $lines = @()
    if ([IO.File]::Exists($local)) {
        $lines = @([IO.File]::ReadAllLines($local) | Where-Object { $_ -notmatch '^compiler\.path=' })
    }
    $lines += 'compiler.path=' + $binary.Replace('\', '/') + '/'
    [IO.File]::WriteAllLines($local, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
    foreach ($name in @('library.properties', 'src/USBDevice.h', 'src/USBDevice.cpp')) {
        $old = Join-Path $Target "libraries/USBDevice/$name"
        if ([IO.File]::Exists($old)) { Remove-Item -LiteralPath $old -Force }
    }
    # An empty retired shim still appears as an invalid Arduino library.
    foreach ($name in @('libraries/USBDevice/src', 'libraries/USBDevice', 'libraries')) {
        $old = Join-Path $Target $name
        if ([IO.Directory]::Exists($old) -and [IO.Directory]::GetFileSystemEntries($old).Length -eq 0) {
            try { [IO.Directory]::Delete($old, $false) }
            catch [IO.DirectoryNotFoundException] { }
            catch [IO.IOException] {
                if ([IO.Directory]::Exists($old) -and [IO.Directory]::GetFileSystemEntries($old).Length -eq 0) { throw }
            }
        }
    }
    $oldPython = Join-Path $Target 'tools/seal-firmware-elf.py'
    if ($env:OS -eq 'Windows_NT' -and [IO.File]::Exists($oldPython)) { Remove-Item -LiteralPath $oldPython -Force }
    Write-Host "Native GNU Arm: $binary"
}

function Test-Mk61NativePayload {
    param([string]$ProjectRoot, [string]$Target)
    try {
        . (Join-Path $ProjectRoot 'tools/firmware/stm32/sdk.ps1')
        if ($env:OS -eq 'Windows_NT' -and [IO.File]::Exists((Join-Path $Target 'tools/seal-firmware-elf.py'))) {
            throw 'Retired Python sealer remains in the Windows board package'
        }
        foreach ($pair in Get-Mk61NativePayloadPairs $ProjectRoot $Target) {
            if (-not [IO.File]::Exists($pair.Target)) { throw "Installed native package file is missing: $($pair.Target)" }
            if ((Get-NativeFileSha256 $pair.Source) -ne
                (Get-NativeFileSha256 $pair.Target)) {
                throw "Installed native package file differs from this checkout: $($pair.Target)"
            }
        }
        $null = Get-Mk61NativeCompiler $ProjectRoot $Target ''
        return $true
    } catch {
        # Arduino suppresses ordinary hook stdout unless verbose is selected.
        # Keep the underlying reason alongside the reinstall instruction.
        [Console]::Error.WriteLine('MK61s native package check: ' + $_.Exception.Message)
        return $false
    }
}
