#requires -Version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This test requires Windows PowerShell' }

$root = Split-Path -Parent $PSScriptRoot
$work = Join-Path ([IO.Path]::GetTempPath()) (
    'mk61-dfu-test-' + [Guid]::NewGuid().ToString('N'))
$fakeBin = Join-Path $work 'Programmer with spaces'
$oldPath = $env:PATH
$oldLog = $env:MK61_TEST_CUBE_LOG
$oldExit = $env:MK61_TEST_CUBE_EXIT
. (Join-Path $PSScriptRoot 'fixtures/arduino_bundle.ps1')

try {
    [IO.Directory]::CreateDirectory($fakeBin) | Out-Null
    $installed = Join-Path $work 'native board/tools'
    [IO.Directory]::CreateDirectory($installed) | Out-Null
    Copy-Item (Join-Path $root 'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/*.ps1') $installed
    Copy-Item (Join-Path $root 'tools/.mk61-dfu/dfu.ps1') (Join-Path $installed 'mk61-dfu.ps1')
    # Only the hardware programmer is fake; direct PowerShell invocation,
    # sealed bundle validation, System installation and recovery are real.
    Add-Type -Language CSharp -OutputType ConsoleApplication `
        -OutputAssembly (Join-Path $fakeBin 'STM32_Programmer_CLI.exe') `
        -TypeDefinition @'
using System;
using System.IO;
using System.Text;
public static class FakeProgrammer {
    public static int Main(string[] args) {
        File.WriteAllLines(Environment.GetEnvironmentVariable("MK61_TEST_CUBE_LOG"),
                           args, new UTF8Encoding(false));
        return Int32.Parse(Environment.GetEnvironmentVariable("MK61_TEST_CUBE_EXIT"));
    }
}
'@
    $env:PATH = "$fakeBin;$oldPath"
    $env:MK61_TEST_CUBE_LOG = Join-Path $work 'programmer-args.txt'
    $env:MK61_TEST_CUBE_EXIT = '0'
    $programmer = Join-Path $fakeBin 'STM32_Programmer_CLI.exe'
    $powerShell = (Get-Process -Id $PID).Path
    $uploader = Join-Path $installed 'mk61-app-upload.ps1'

    foreach ($directory in @('build', 'build with spaces')) {
        $build = Join-Path $work $directory
        $bundle = 'mk61s-M-classic-v2-uc1609-f401'
        $stage = Join-Path (Join-Path $build 'mk61-system-apps') $bundle
        $system = Join-Path $stage 'System'
        $device = Join-Path $build 'mock-device'
        [IO.Directory]::CreateDirectory($system) | Out-Null
        [IO.Directory]::CreateDirectory($device) | Out-Null
        [IO.File]::WriteAllText((Join-Path $system 'USBDISK.APP'), 'APP')
        $resident = Join-Path $build 'code.ino.bin'
        [IO.File]::WriteAllText($resident, 'resident')
        Copy-Item -LiteralPath (Join-Path $root 'tools/.mkc/mkc.ps1') `
            -Destination (Join-Path $stage 'mk61-system-installer.ps1')
        [void](New-Mk61TestArduinoBundle $build $bundle)
        $arguments = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', $uploader, '-BuildPath', $build, '-Project', 'code.ino',
            '-Bundle', $bundle, '-Profile', 'classic-v2-uc1609',
            '-Programmer', $programmer,
            '-TestMockDevice', $device, '-TestMockDfu')
        & $powerShell @arguments
        if ($LASTEXITCODE -ne 0) { throw "DFU/System upload failed: $directory" }
        $received = [IO.File]::ReadAllLines($env:MK61_TEST_CUBE_LOG)
        $download = [Array]::IndexOf($received, '--download')
        $start = [Array]::IndexOf($received, '--start')
        if ($download -lt 0 -or $start -lt 0 -or
            $received[$download + 1] -ne $resident.Replace('\', '/') -or
            $received[$download + 2] -ne '0x8000000' -or
            $received[$start + 1] -ne '0x8000000' -or
            $received -notcontains '--verify' -or
            $received -notcontains 'port=usb1' -or
            $received -notcontains 'VID=0x0483' -or
            $received -notcontains 'PID=0xdf11') {
            throw "Direct DFU passed incorrect programmer arguments: $received"
        }
        if (-not [IO.File]::Exists((Join-Path $device 'System/USBDISK.APP'))) {
            throw 'DFU completed without the following System installation'
        }
    }

    # A failed programmer must never be followed by the CDC copy/recovery path.
    $env:MK61_TEST_CUBE_EXIT = '7'
    $failedDevice = Join-Path $work 'failed-device'
    [IO.Directory]::CreateDirectory($failedDevice) | Out-Null
    $deviceIndex = [Array]::IndexOf($arguments, '-TestMockDevice') + 1
    $arguments[$deviceIndex] = $failedDevice
    $failedLog = Join-Path $work 'failed-upload.txt'
    $ErrorActionPreference = 'Continue'
    try {
        & $powerShell @arguments *> $failedLog
        $failedExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = 'Stop'
    }
    if ($failedExit -eq 0) { throw 'Uploader accepted a failed DFU' }
    $failure = [IO.File]::ReadAllText($failedLog)
    if ($failure -notmatch 'STM32 DFU failed with exit code 7' -or
        $failure -match 'Recovery without reflashing' -or
        [IO.Directory]::Exists((Join-Path $failedDevice 'System'))) {
        throw "Uploader continued after failed DFU: $failure"
    }
    $global:LASTEXITCODE = 0
    Write-Host 'arduino_dfu_windows_self_test: ok (standalone DFU, fake hardware)'
} finally {
    $env:PATH = $oldPath
    $env:MK61_TEST_CUBE_LOG = $oldLog
    $env:MK61_TEST_CUBE_EXIT = $oldExit
    if ([IO.Directory]::Exists($work)) {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
}
