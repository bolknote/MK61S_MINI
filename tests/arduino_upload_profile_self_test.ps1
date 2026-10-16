#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$uploader = Join-Path $root 'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-app-upload.ps1'
$powerShell = (Get-Process -Id $PID).Path
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61 upload profiles ' + [guid]::NewGuid().ToString('N'))
$oldTool = $env:MK61_TEST_MKC_TOOL
$oldProfile = $env:MK61_TEST_DEVICE_PROFILE

# Supply a device identity, then use the real MKC profile guard and file
# installation. Enable the filesystem transport only after that guard runs;
# ordinary --mock installations intentionally skip the identity comparison.
$installer = @'
$uploadArguments = @($args)
$env:MKC_POWERSHELL_IMPORT_ONLY = '1'
. $env:MK61_TEST_MKC_TOOL
try {
    [void](Parse-Arguments $uploadArguments)
    $script:TestDeviceRoot = $script:MockRoot
    $script:MockRoot = ''
    $script:DetectedProfile = $env:MK61_TEST_DEVICE_PROFILE
    $script:SessionDir = Join-Path $PSScriptRoot 'session'
    [void][IO.Directory]::CreateDirectory($script:SessionDir)
    $script:CreateRemoteDirectory = (Get-Command New-RemoteDirectory).ScriptBlock
    function New-RemoteDirectory {
        param([string]$Remote)
        $script:MockRoot = $script:TestDeviceRoot
        & $script:CreateRemoteDirectory $Remote
    }
    Install-SystemBundle $script:InstallSystemDir
} catch {
    [Console]::Error.WriteLine('mkc: ' + $_.Exception.Message)
    exit 1
}
'@

try {
    [void][IO.Directory]::CreateDirectory($work)
    $env:MK61_TEST_MKC_TOOL = Join-Path $root 'tools/.mkc/mkc.ps1'
    $profiles = @(
        @('mini-v2-lcd1602-a00', 'mini-v2-a00'),
        @('mini-v2-lcd1602-a02', 'mini-v2-a02'),
        @('mini-v3-lcd1602-a00', 'mini-v3-a00'),
        @('mini-v3-lcd1602-a02', 'mini-v3-a02'),
        @('mini-v3-oled1602-ws0010', 'mini-v3-ws0010'),
        @('classic-v2-uc1609', 'classic-v2-uc1609'),
        @('classic-v3-uc1609', 'classic-v3-uc1609'),
        @('40th-uc1609', '40th-uc1609')
    )
    foreach ($mcu in @('f401', 'f411')) {
        foreach ($pair in $profiles) {
            $profile = $pair[0]
            $env:MK61_TEST_DEVICE_PROFILE = $pair[1]
            $build = Join-Path $work "$profile-$mcu"
            $bundle = "mk61s-M-$profile-$mcu"
            $stage = Join-Path (Join-Path $build 'mk61-system-apps') $bundle
            $system = Join-Path $stage 'System'
            $device = Join-Path $build 'device'
            [void][IO.Directory]::CreateDirectory($system)
            [void][IO.Directory]::CreateDirectory($device)
            [IO.File]::WriteAllText((Join-Path $system 'HELP0.TXT'), "Help`n")
            $requiresUsbDisk = if ($mcu -eq 'f401') { '1' } else { '0' }
            if ($requiresUsbDisk -eq '1') {
                [IO.File]::WriteAllBytes((Join-Path $system 'USBDISK.APP'), [byte[]]::new(64))
            }
            [IO.File]::WriteAllText((Join-Path $stage 'mk61-system-installer.ps1'), $installer)
            $arguments = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', $uploader, '-BuildPath', $build, '-Project', 'code.ino',
                '-Bundle', $bundle, '-Profile', $profile, '-Mcu', $mcu,
                '-RequireUsbDisk', $requiresUsbDisk, '-TestMockDevice', $device)
            $log = Join-Path $build 'upload.txt'
            & $powerShell @arguments *> $log
            if ($LASTEXITCODE -ne 0 -or
                -not [IO.File]::Exists((Join-Path $device 'System/HELP0.TXT'))) {
                throw "Upload rejected firmware identity $($pair[1]): $([IO.File]::ReadAllText($log))"
            }
        }
    }

    # A different display must still be rejected before any device write.
    # Also exercise the recovery command after a successful fake DFU.
    $profile = 'mini-v2-lcd1602-a00'
    $build = Join-Path $work "$profile-f411"
    $device = Join-Path $build 'wrong-device'
    [void][IO.Directory]::CreateDirectory($device)
    [IO.File]::WriteAllText((Join-Path $build 'code.ino.bin'), 'resident')
    $stm32Script = Join-Path $work 'stm32CubeProg.sh'
    [IO.File]::WriteAllText($stm32Script, '    -f | --file)')
    if ($env:OS -eq 'Windows_NT') {
        $busybox = Join-Path $work 'fake-busybox.cmd'
        [IO.File]::WriteAllText($busybox, "@exit /b 0`r`n")
    } else {
        $busybox = Join-Path $work 'fake-busybox'
        [IO.File]::WriteAllText($busybox, "#!/bin/sh`nexit 0`n")
        & chmod +x $busybox
        if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare fake DFU tool' }
    }
    $env:MK61_TEST_DEVICE_PROFILE = 'mini-v2-a02'
    $arguments[([Array]::IndexOf($arguments, '-Profile') + 1)] = $profile
    $arguments[([Array]::IndexOf($arguments, '-BuildPath') + 1)] = $build
    $arguments[([Array]::IndexOf($arguments, '-Bundle') + 1)] = "mk61s-M-$profile-f411"
    $arguments[([Array]::IndexOf($arguments, '-TestMockDevice') + 1)] = $device
    $arguments += @('-Busybox', $busybox, '-Stm32Script', $stm32Script, '-TestMockDfu')
    $log = Join-Path $work 'wrong-profile.txt'
    $ErrorActionPreference = 'Continue'
    try {
        & $powerShell @arguments *> $log
        $failedExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = 'Stop' }
    $failure = [IO.File]::ReadAllText($log)
    if ($failedExit -eq 0 -or $failure -notmatch 'mini-v2-a02' -or
        $failure -notmatch '(?s)Recovery without reflashing:.*--expect-profile\s+mini-v2-a00\s' -or
        [IO.Directory]::Exists((Join-Path $device 'System'))) {
        throw "Upload did not reject a different display safely: $failure"
    }
    $global:LASTEXITCODE = 0
    Write-Host 'arduino_upload_profile_self_test: ok (16 profiles, strict MKC identity, recovery)'
} finally {
    $env:MK61_TEST_MKC_TOOL = $oldTool
    $env:MK61_TEST_DEVICE_PROFILE = $oldProfile
    if ([IO.Directory]::Exists($work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
