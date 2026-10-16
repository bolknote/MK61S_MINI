#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$BuildPath,
    [string]$Fqbn,
    [string]$ConfigFile,
    [string]$PlatformToolsDirectory,
    [string]$Stm32ToolsDirectory,
    [string]$PublishedSystem,
    [switch]$Fixture,
    [ValidateSet('f401', 'f411')][string]$FixtureMcu = 'f401'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61-arduino-e2e-' + [Guid]::NewGuid().ToString('N'))
$sourceTools = Join-Path $root 'tools/.mk61-arduino-board/hardware/mk61/stm32/tools'
$powerShell = (Get-Process -Id $PID).Path
$windowsHost = $env:OS -eq 'Windows_NT'
$savedEnvironment = @{}
foreach ($name in @('PATH', 'MK61_E2E_ROOT', 'MK61_E2E_DEVICE_SOURCE', 'MK61_E2E_POWERSHELL', 'MK61_HOST_CXX', 'TEMP', 'TMP')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
}
$backups = @{}
$currentLocation = Get-Location
. (Join-Path $PSScriptRoot 'fixtures/arduino_serial_adapter.ps1')
. (Join-Path $sourceTools 'mk61-system-bundle.ps1')

function Invoke-TestCommand {
    param([string]$Executable, [string[]]$Arguments, [string]$Log)
    $ErrorActionPreference = 'Continue'
    try {
        & $Executable @Arguments *> $Log
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
}

function Assert-DeviceContents {
    foreach ($file in @(Get-ChildItem -LiteralPath $system -Recurse -File)) {
        $relative = $file.FullName.Substring($system.Length + 1).Replace('\', '/')
        [byte[]]$expected = [IO.File]::ReadAllBytes($file.FullName)
        if ($relative -match '\.TXT$') { $expected = [Mk61.ArduinoE2E.Device]::M8($expected) }
        $actual = Join-Path $env:MK61_E2E_ROOT "fs/System/$relative"
        if (-not [IO.File]::Exists($actual) -or
            [Convert]::ToBase64String([IO.File]::ReadAllBytes($actual)) -cne [Convert]::ToBase64String($expected)) {
            throw "Wrong bytes installed through C6: $relative"
        }
    }
    foreach ($retained in @('USER.TXT', 'VMCache/VMC-0042.APP')) {
        if ([IO.File]::ReadAllText((Join-Path $env:MK61_E2E_ROOT "fs/System/$retained")) -cne 'keep') {
            throw "Installer damaged retained file: $retained"
        }
    }
    foreach ($name in $script:Mk61SystemFiles) {
        if (-not [IO.File]::Exists((Join-Path $system $name)) -and
            [IO.File]::Exists((Join-Path $env:MK61_E2E_ROOT "fs/System/$name"))) {
            throw "Installer kept disabled System file: $name"
        }
    }
    $commands = [IO.File]::ReadAllText((Join-Path $env:MK61_E2E_ROOT 'commands.log'))
    if ($commands -notmatch 'fsput begin' -or $commands -notmatch 'fsput data' -or $commands -notmatch 'fsget ') {
        throw 'Test bypassed the real C6 transfer or verification'
    }
}

try {
    [void][IO.Directory]::CreateDirectory($work)
    $env:MK61_E2E_DEVICE_SOURCE = Join-Path $PSScriptRoot 'fixtures/arduino_cdc_device.cs'
    try { [Text.Encoding]::RegisterProvider([Text.CodePagesEncodingProvider]::Instance) } catch {}
    if ($Fixture) {
        . (Join-Path $PSScriptRoot 'fixtures/arduino_bundle.ps1')
        $BuildPath = Join-Path $work 'build with spaces'
        $bundle = "mk61s-M-mini-v2-lcd1602-a00-$FixtureMcu"
        $stage = Join-Path (Join-Path $BuildPath 'mk61-system-apps') $bundle
        $system = Join-Path $stage 'System'
        [void][IO.Directory]::CreateDirectory((Join-Path $system 'VMCache'))
        Copy-Item -LiteralPath (Join-Path $root 'tools/.mkc/mkc.ps1') (Join-Path $stage 'mk61-system-installer.ps1')
        foreach ($name in @('VMCache/VMSTORE.APP', 'LANGVM.APP', 'LANGIN.APP')) {
            [IO.File]::WriteAllBytes((Join-Path $system $name), [byte[]]::new(64))
        }
        $text = 'M8 ' + [char]0x0416 + ' ' + [char]0x2192 + "`n"
        [IO.File]::WriteAllText((Join-Path $system 'HELP0.TXT'), $text, [Text.UTF8Encoding]::new($false))
        $null = New-Mk61TestArduinoBundle $BuildPath $bundle $FixtureMcu -ResidentUsbDisk:($FixtureMcu -eq 'f411')
        if ([string]::IsNullOrEmpty($Fqbn)) {
            $PlatformToolsDirectory = Join-Path $work 'installed board/tools'
            [void][IO.Directory]::CreateDirectory($PlatformToolsDirectory)
            Copy-Item -Path (Join-Path $sourceTools '*.ps1') $PlatformToolsDirectory
        }
    }
    if ((-not $Fixture -or -not [string]::IsNullOrEmpty($Fqbn)) -and
        (-not $windowsHost -or [string]::IsNullOrEmpty($Fqbn) -or
        [string]::IsNullOrEmpty($ConfigFile) -or [string]::IsNullOrEmpty($PlatformToolsDirectory))) {
        throw 'Real-build mode requires Windows, the installed board tools, FQBN and IDE config'
    }
    $stages = @(Get-ChildItem -LiteralPath (Join-Path $BuildPath 'mk61-system-apps') -Directory)
    if ($stages.Count -ne 1) { throw 'Expected one actual Arduino build stage' }
    $stage = $stages[0].FullName; $bundle = $stages[0].Name
    $system = Join-Path $stage 'System'
    $manifestPath = Join-Path $stage 'build.system.json'
    $metadata = [IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
    $mcu = $metadata.mcu
    $label = $bundle.Substring(8, $bundle.Length - 8 - $mcu.Length - 1)
    $installer = Join-Path $stage 'mk61-system-installer.ps1'
    $uploader = Join-Path $PlatformToolsDirectory 'mk61-app-upload.ps1'
    $resident = Join-Path $BuildPath 'code.ino.bin'
    $null = Get-VerifiedMk61SystemManifest $stage $bundle $mcu $resident
    foreach ($pair in @(@($installer, (Join-Path $root 'tools/.mkc/mkc.ps1')),
            @($uploader, (Join-Path $sourceTools 'mk61-app-upload.ps1')))) {
        if ((Get-Mk61FileSha256 $pair[0]) -cne (Get-Mk61FileSha256 $pair[1])) {
            throw "Actual build is using a stale script: $($pair[0])"
        }
    }
    if (-not $Fixture) {
        if ([string]::IsNullOrEmpty($PublishedSystem)) { throw 'Missing published System directory' }
        foreach ($file in @(Get-ChildItem -LiteralPath $system -Recurse -File)) {
            $name = $file.FullName.Substring($system.Length + 1)
            if ((Get-Mk61FileSha256 $file.FullName) -cne (Get-Mk61FileSha256 (Join-Path $PublishedSystem $name))) {
                throw "Published System differs from the staged Arduino output: $name"
            }
        }
        if ($mcu -eq 'f411' -and -not [IO.File]::Exists((Join-Path $system 'VMCache/VMSTORE.APP'))) {
            throw 'Real language bundle did not exercise nested VMSTORE publication'
        }
    }
    foreach ($path in @($installer, $uploader, $manifestPath)) { $backups[$path] = [IO.File]::ReadAllBytes($path) }
    Set-Mk61E2eSerialAdapter $installer Installer -NonWindowsHost:(-not $windowsHost)
    Set-Mk61E2eSerialAdapter $uploader Uploader
    # The fixture uses an instrumented installer, pinned exactly as a normal
    # staged installer is. All firmware and System hashes remain unchanged.
    $metadata.installer_sha256 = Get-Mk61FileSha256 $installer
    [IO.File]::WriteAllText($manifestPath, ($metadata | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
    $bin = Join-Path $work 'Programmer and blocked Python'
    [void][IO.Directory]::CreateDirectory($bin)
    if ($windowsHost) {
        if (-not [IO.File]::Exists((Join-Path $Stm32ToolsDirectory 'win/busybox.exe'))) { throw 'Missing real STM32Tools BusyBox' }
        Add-Type -Path $env:MK61_E2E_DEVICE_SOURCE -OutputType ConsoleApplication `
            -OutputAssembly (Join-Path $bin 'STM32_Programmer_CLI.exe')
        [void][Reflection.Assembly]::LoadFrom((Join-Path $bin 'STM32_Programmer_CLI.exe'))
        foreach ($name in @('python.exe', 'python3.exe', 'py.exe')) {
            Copy-Item "$env:WINDIR/System32/where.exe" (Join-Path $bin $name)
        }
        $busybox = Join-Path $Stm32ToolsDirectory 'win/busybox.exe'
        $wrapper = Join-Path $Stm32ToolsDirectory 'stm32CubeProg.sh'
    } else {
        # Local fixture only. CI runs the native BusyBox and STM32 wrapper.
        $busybox = Join-Path $bin 'busybox'
        $wrapper = Join-Path $bin 'stm32CubeProg.sh'
        $programmer = Join-Path $bin 'programmer.ps1'
        [IO.File]::WriteAllText($programmer, 'Add-Type -Path $env:MK61_E2E_DEVICE_SOURCE; exit [Mk61.ArduinoE2E.Device]::Main($args)')
        $shell = '#!/bin/bash' + "`n" + 'exec "$MK61_E2E_POWERSHELL" -NoLogo -NoProfile -File "' + $programmer + '" --download "${4:2}" 0x8000000 --start 0x8000000' + "`n"
        [IO.File]::WriteAllText($busybox, $shell, [Text.UTF8Encoding]::new($false))
        & chmod +x $busybox
        $env:MK61_E2E_POWERSHELL = $powerShell
        [IO.File]::WriteAllText($wrapper, "-b | --bin )`n")
        Add-Type -Path $env:MK61_E2E_DEVICE_SOURCE
    }
    $env:PATH = "$bin$([IO.Path]::PathSeparator)$($env:PATH)"
    if ($windowsHost) {
        $resolved = (& $busybox sh -c 'command -v STM32_Programmer_CLI.exe' | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $resolved.Replace('\', '/') -ine
            (Join-Path $bin 'STM32_Programmer_CLI.exe').Replace('\', '/')) {
            throw "Refusing to use a non-test programmer: $resolved"
        }
    }
    $env:MK61_HOST_CXX = Join-Path $work 'missing-host-cxx.exe'
    $unicodeTemp = Join-Path $work ('Temp ' + [char]0x420 + [char]0x43E + [char]0x43C + [char]0x430 + [char]0x43D)
    [void][IO.Directory]::CreateDirectory($unicodeTemp)
    $env:TEMP = $unicodeTemp; $env:TMP = $unicodeTemp
    $ideDirectory = Join-Path $work 'Program Files/Arduino IDE'
    [void][IO.Directory]::CreateDirectory($ideDirectory)
    Set-Location $ideDirectory
    $cases = @('normal', 'normal-auto-port', 'legacy-first', 'busy-once', 'delayed-port',
        'wrong-profile', 'wrong-build', 'identity-switch', 'multiple',
        'dfu-failure', 'wrong-ack', 'disconnect', 'corrupt-readback',
        'changed-resident', 'changed-system', 'missing-system', 'missing-manifest', 'invalid-port')
    foreach ($case in $cases) {
        $env:MK61_E2E_ROOT = Join-Path $work $case
        $fs = Join-Path $env:MK61_E2E_ROOT 'fs/System'
        [void][IO.Directory]::CreateDirectory((Join-Path $fs 'VMCache'))
        [IO.File]::WriteAllText((Join-Path $env:MK61_E2E_ROOT 'mode'), $case)
        foreach ($name in @('USER.TXT', 'VMCache/VMC-0042.APP')) { [IO.File]::WriteAllText((Join-Path $fs $name), 'keep') }
        foreach ($name in $script:Mk61SystemFiles) {
            if (-not [IO.File]::Exists((Join-Path $system $name))) { [IO.File]::WriteAllText((Join-Path $fs $name), 'stale') }
        }
        $changed = $null; $original = $null
        if ($case -eq 'changed-resident') { $changed = $resident }
        if ($case -in @('changed-system', 'missing-system')) { $changed = Join-Path $system 'HELP0.TXT' }
        if ($case -eq 'missing-manifest') { $changed = $manifestPath }
        if ($null -ne $changed) {
            $original = [IO.File]::ReadAllBytes($changed)
            if ($case.StartsWith('missing-')) { Remove-Item -LiteralPath $changed }
            else { $bad = [byte[]]$original.Clone(); $bad[0] = $bad[0] -bxor 1; [IO.File]::WriteAllBytes($changed, $bad) }
        }
        try {
            $port = if ($case -in @('multiple', 'normal-auto-port')) { '' } elseif ($case -eq 'invalid-port') { '/dev/wrong' } else { 'COM71' }
            $log = Join-Path $env:MK61_E2E_ROOT 'upload.log'
            if ([string]::IsNullOrEmpty($Fqbn)) {
                $argv = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $uploader,
                    '-BuildPath', $BuildPath, '-Project', 'code.ino', '-Bundle', $bundle, '-Profile', $label,
                    '-Mcu', $mcu, '-RequireUsbDisk', $(if ($mcu -eq 'f401') { '1' } else { '0' }),
                    '-Busybox', $busybox, '-Stm32Script', $wrapper)
                if ($port) { $argv += @('-Port', $port) }
                $code = Invoke-TestCommand $powerShell $argv $log
            } else {
                $argv = @('--config-file', $ConfigFile, 'upload', '--fqbn', $Fqbn, '--build-path', $BuildPath,
                    '--upload-property', "busybox=$busybox", '--upload-property', "runtime.tools.STM32Tools.path=$Stm32ToolsDirectory")
                if ($port) { $argv += @('--port', $port) }
                $argv += (Join-Path $root 'code')
                $code = Invoke-TestCommand 'arduino-cli' $argv $log
            }
            $output = [IO.File]::ReadAllText($log)
            if ($case -in @('normal', 'normal-auto-port', 'legacy-first', 'busy-once', 'delayed-port')) {
                if ($code -ne 0 -or $output -notmatch 'Resident and System APP upload complete') { throw "$case failed ($code): $output" }
                Assert-DeviceContents
                $actualIdentity = [Mk61.ArduinoE2E.Device]::FirmwareIdentity((Join-Path $env:MK61_E2E_ROOT 'firmware.bin'))
                if ($actualIdentity[0] -cne $metadata.profile -or $actualIdentity[1] -cne $metadata.build_id) { throw 'Firmware identity differs from actual build' }
            } else {
                if ($code -eq 0 -or $output -match 'Resident and System APP upload complete') { throw "Fault $case was silently accepted: $output" }
                if ($case -in @('changed-resident', 'changed-system', 'missing-system', 'missing-manifest', 'invalid-port')) {
                    if ([IO.File]::Exists((Join-Path $env:MK61_E2E_ROOT 'programmer.args'))) { throw "DFU started before $case was rejected" }
                } elseif ($case -eq 'dfu-failure') {
                    if ($output -notmatch 'STM32 DFU failed with exit code 7' -or $output -match 'Recovery without reflashing' -or
                        [IO.File]::Exists((Join-Path $env:MK61_E2E_ROOT 'commands.log'))) { throw "CDC continued after failed DFU: $output" }
                } else {
                    if ($output -notmatch 'Recovery without reflashing:.*--expect-build' -or
                        -not [IO.File]::Exists((Join-Path $env:MK61_E2E_ROOT 'firmware.bin'))) { throw "Fault $case did not reach the intended CDC failure: $output" }
                    $commands = Join-Path $env:MK61_E2E_ROOT 'commands.log'
                    if ($case -in @('wrong-profile', 'wrong-build', 'identity-switch', 'multiple') -and
                        [IO.File]::Exists($commands) -and [IO.File]::ReadAllText($commands) -match '(?m)^(mkdir|rm|fsput) ') {
                        throw "System modified before $case was rejected"
                    }
                    if ($case -eq 'wrong-build' -and $output -notmatch 'firmware build .* does not match bundle') { throw "Build guard did not run: $output" }
                }
            }
            Write-Host "arduino_windows_e2e: $mcu $case OK"
            if ($case -eq 'corrupt-readback') {
                # Retry the actual emitted recovery operation, without DFU.
                $before = Get-Mk61FileSha256 (Join-Path $env:MK61_E2E_ROOT 'programmer.args')
                [IO.File]::WriteAllText((Join-Path $env:MK61_E2E_ROOT 'mode'), 'normal')
                $recovery = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $installer,
                    '--install-system', $system, '--expect-profile', $metadata.profile, '--expect-build', $metadata.build_id,
                    '--wait-ready', '45', '--port', 'COM71')
                if ($mcu -eq 'f411') { $recovery += '--resident-usbdisk' }
                $code = Invoke-TestCommand $powerShell $recovery (Join-Path $env:MK61_E2E_ROOT 'recovery.log')
                if ($code -ne 0 -or $before -cne (Get-Mk61FileSha256 (Join-Path $env:MK61_E2E_ROOT 'programmer.args'))) {
                    throw "Recovery without DFU failed: $([IO.File]::ReadAllText((Join-Path $env:MK61_E2E_ROOT 'recovery.log')))"
                }
                Assert-DeviceContents
                Write-Host "arduino_windows_e2e: $mcu recovery without reflashing OK"
            }
        } finally {
            if ($null -ne $changed) { [IO.File]::WriteAllBytes($changed, $original) }
        }
    }
    Write-Host "arduino_windows_e2e: $mcu OK (18 scenarios and recovery; physical USB boundary simulated)"
} finally {
    Set-Location $currentLocation
    foreach ($path in $backups.Keys) { [IO.File]::WriteAllBytes($path, $backups[$path]) }
    foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name]) }
    if ([IO.Directory]::Exists($work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
