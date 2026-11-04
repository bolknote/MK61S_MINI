#requires -Version 5.1
# First-install child process must print progress without returning it as a path.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tools/.mk61-arduino-board/payload.ps1')
# Reproduce the Arduino-launched 5.1 process without its optional hash function.
function Get-FileHash { throw 'Get-FileHash is deliberately unavailable' }
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61 native install ' + [Guid]::NewGuid().ToString('N'))
$oldBoard = $env:MK61_ARDUINO_TOOLCHAIN
$oldNative = $env:MK61_GCC_TOOLCHAIN
$oldPublic = $env:PUBLIC
$oldOs = $env:OS
try {
    $env:MK61_ARDUINO_TOOLCHAIN = ''
    $env:MK61_GCC_TOOLCHAIN = ''
    $project = Join-Path $work 'source'
    $native = Join-Path $project 'tools/.mk61-gcc'
    [void][IO.Directory]::CreateDirectory($native)
    foreach ($file in @('sdk.ps1', 'toolchain-lock.json')) {
        Copy-Item (Join-Path $root "tools/.mk61-gcc/$file") $native
    }
    # Only the compiler download is replaced. It runs in a real child process
    # and emits Write-Host just like install_gcc_dependencies.ps1, on both PSs.
    $installer = @'
param([string]$InstallRoot)
$ErrorActionPreference = 'Stop'
$bin = Join-Path $InstallRoot 'xpack-arm-none-eabi-gcc-14.2.1-1.1/bin'
[void][IO.Directory]::CreateDirectory($bin)
Write-Host 'Downloading pinned compiler fixture'
$suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
$gcc = Join-Path $bin "arm-none-eabi-gcc$suffix"
if ($suffix) {
    Add-Type -Language CSharp -OutputType ConsoleApplication -OutputAssembly $gcc -TypeDefinition @"
public static class GnuFixture {
    public static void Main() { System.Console.WriteLine("14.2.1"); }
}
"@
} else {
    [IO.File]::WriteAllText($gcc, "#!/bin/sh`necho 14.2.1`n", (New-Object Text.UTF8Encoding($false)))
    & chmod +x $gcc
}
foreach ($name in @('g++', 'ar', 'ranlib', 'objcopy', 'size', 'nm', 'objdump', 'c++filt', 'gcc-ar')) {
    Copy-Item -LiteralPath $gcc -Destination (Join-Path $bin "arm-none-eabi-$name$suffix")
}
Write-Host "GNU Arm installed: $bin"
Write-Host "Native SDK: $PSScriptRoot"
'@
    [IO.File]::WriteAllText((Join-Path $project 'tools/install_gcc_dependencies.ps1'),
        $installer, (New-Object Text.UTF8Encoding($false)))
    $target = Join-Path $work 'Arduino sketchbook/hardware/mk61/stm32'
    $result = @(Get-Mk61NativeCompiler $project $target '' -Install)
    $expected = [IO.Path]::GetFullPath((Join-Path $target 'tools/toolchains/xpack-arm-none-eabi-gcc-14.2.1-1.1/bin'))
    if ($result.Count -ne 1 -or $result[0] -cne $expected) {
        throw "Compiler installation returned status output as a path: $result"
    }
    $cached = @(Get-Mk61NativeCompiler $project $target '' -Install)
    if ($cached.Count -ne 1 -or $cached[0] -cne $expected) {
        throw 'Reinstall did not return the same compiler path'
    }
    Install-Mk61NativePayload $root $target $expected
    if (-not (Test-Mk61NativePayload $root $target)) {
        throw 'A fresh native board package requires Get-FileHash'
    }
    $header = Join-Path $target 'cores/mk61/Arduino.h'
    $original = [IO.File]::ReadAllBytes($header)
    [IO.File]::AppendAllText($header, '// changed installed header')
    if (Test-Mk61NativePayload $root $target) {
        throw 'A changed installed header passed the native package check'
    }
    [IO.File]::WriteAllBytes($header, $original)
    [IO.File]::Delete($header)
    if (Test-Mk61NativePayload $root $target) {
        throw 'A missing installed header passed the native package check'
    }
    [IO.File]::WriteAllBytes($header, $original)
    . (Join-Path $root 'tools/.mk61-gcc/sdk.ps1')
    $sdkCopy = Join-Path $work 'SDK checksum fixture'
    Copy-Item (Join-Path $root 'third_party/stm32f4') $sdkCopy -Recurse
    [IO.File]::AppendAllText((Join-Path $sdkCopy 'device/include/stm32f411xe.h'), '// changed SDK')
    $sdkRejected = $false
    try { $null = Get-NativeSdkPath $root $sdkCopy }
    catch { $sdkRejected = $_.Exception.Message -match 'checksum mismatch' }
    if (-not $sdkRejected) { throw 'SDK checksum verification requires Get-FileHash' }
    $env:PUBLIC = Join-Path $work 'Public'
    $unicodeTarget = Join-Path $work ('Arduino ' + [char]0x420 + [char]0x43e + [char]0x43c + [char]0x430 + [char]0x43d)
    $requestedRoot = Join-Path $unicodeTarget 'tools/toolchains'
    $env:OS = 'Windows_NT'
    $safeRoot = Get-NativeGnuArmInstallRoot $requestedRoot
    if ($safeRoot -match '[^\x20-\x7e]' -or $safeRoot -notlike "$($env:PUBLIC)*" -or
        $safeRoot -cne (Get-NativeGnuArmInstallRoot $requestedRoot)) {
        throw 'Unicode compiler installation did not select a stable real ASCII cache'
    }
    if ((Get-NativeGnuArmInstallRoot (Join-Path $work 'ASCII toolchain')) -cne (Join-Path $work 'ASCII toolchain')) {
        throw 'ASCII compiler path was unnecessarily relocated'
    }
    $rejected = $false
    try { $null = Get-NativeGnuArmBin $project '14.2.1-1.1' $unicodeTarget }
    catch { $rejected = $_.Exception.Message -match 'ASCII-only path' }
    if (-not $rejected) { throw 'Explicit unsafe Windows compiler path was accepted' }
    $env:OS = $oldOs
    if ($env:OS -eq 'Windows_NT') {
        # Reproduce an older package that registered GCC in a Cyrillic folder.
        $legacy = Join-Path $requestedRoot 'xpack-arm-none-eabi-gcc-14.2.1-1.1/bin'
        [void][IO.Directory]::CreateDirectory($legacy)
        [IO.File]::WriteAllText((Join-Path $unicodeTarget 'platform.local.txt'), 'compiler.path=' + $legacy)
        $migrated = @(Get-Mk61NativeCompiler $project $unicodeTarget '' -Install)
        $expectedMigration = Join-Path $safeRoot 'xpack-arm-none-eabi-gcc-14.2.1-1.1/bin'
        if ($migrated.Count -ne 1 -or $migrated[0] -cne $expectedMigration) {
            throw 'Reinstall did not migrate the registered Unicode compiler'
        }
    }
    Write-Host 'Native Arduino first install: status/path isolation, module-independent SHA256 checks and Windows ASCII migration PASS'
} finally {
    $env:MK61_ARDUINO_TOOLCHAIN = $oldBoard
    $env:MK61_GCC_TOOLCHAIN = $oldNative
    $env:PUBLIC = $oldPublic
    $env:OS = $oldOs
    if ([IO.Directory]::Exists($work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
