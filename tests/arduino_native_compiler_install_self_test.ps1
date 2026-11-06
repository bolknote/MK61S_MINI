#requires -Version 5.1
# First-install child process must print progress without returning it as a path.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tools/arduino/payload.ps1')
# Reproduce the Arduino-launched 5.1 process without its optional hash function.
function Get-FileHash { throw 'Get-FileHash is deliberately unavailable' }
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61 native install ' + [Guid]::NewGuid().ToString('N'))
$oldBoard = $env:MK61_ARDUINO_TOOLCHAIN
$oldNative = $env:MK61_GCC_TOOLCHAIN
$oldPublic = $env:PUBLIC
$oldOs = $env:OS
$oldData = $env:ARDUINO_DIRECTORIES_DATA
try {
    $env:MK61_ARDUINO_TOOLCHAIN = ''
    $env:MK61_GCC_TOOLCHAIN = ''
    $emptyData = Join-Path $work 'empty Arduino15'
    $env:ARDUINO_DIRECTORIES_DATA = $emptyData
    $project = Join-Path $work 'source'
    $native = Join-Path $project 'tools/firmware/stm32'
    [void][IO.Directory]::CreateDirectory($native)
    foreach ($file in @('sdk.ps1', 'toolchain-lock.json')) {
        Copy-Item (Join-Path $root "tools/firmware/stm32/$file") $native
    }
    # Only the compiler download is replaced. It runs in a real child process
    # and emits Write-Host just like install_gcc_dependencies.ps1, on both PSs.
    $installer = @'
param([string]$InstallRoot)
$ErrorActionPreference = 'Stop'
[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'compiler-installs.txt'), "install`n")
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
    [IO.File]::WriteAllText((Join-Path $project 'tools/firmware/stm32/install_gcc_dependencies.ps1'),
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
    . (Join-Path $root 'tools/firmware/stm32/sdk.ps1')
    # Exercise transient DNS/transfer failure with the same helper on PS 5.1
    # and PS 7. Each retry must discard the partial file; no real HTTP/sleep.
    & {
        $script:downloadAttempts = 0
        $script:downloadFailures = 2
        $script:downloadSleeps = @()
        function Invoke-WebRequest {
            [CmdletBinding()]
            param([switch]$UseBasicParsing, [string]$Uri, [string]$OutFile)
            if ([IO.File]::Exists($OutFile)) { throw 'Partial archive survived a retry' }
            $script:downloadAttempts++
            [IO.File]::WriteAllText($OutFile, 'partial')
            if ($script:downloadAttempts -le $script:downloadFailures) {
                throw 'DNS fixture: github.com unavailable'
            }
            [IO.File]::WriteAllText($OutFile, 'complete')
        }
        function Start-Sleep { param([int]$Seconds) $script:downloadSleeps += $Seconds }
        $archive = Join-Path $work 'compiler-download.fixture'
        Invoke-NativeCompilerDownload 'https://example.invalid/compiler' $archive
        if ($script:downloadAttempts -ne 3 -or ($script:downloadSleeps -join ',') -ne '2,4' -or
            [IO.File]::ReadAllText($archive) -cne 'complete') {
            throw 'Compiler transfer did not recover within three attempts'
        }
        $script:downloadAttempts = 0
        $script:downloadFailures = 3
        $script:downloadSleeps = @()
        $failed = $false
        try { Invoke-NativeCompilerDownload 'https://example.invalid/compiler' $archive }
        catch { $failed = $_.Exception.Message -match 'DNS fixture' }
        if (-not $failed -or $script:downloadAttempts -ne 3 -or
            ($script:downloadSleeps -join ',') -ne '2,4' -or [IO.File]::Exists($archive)) {
            throw 'Permanent compiler download failure was hidden or left a partial archive'
        }
        $script:downloadAttempts = 0
        $script:downloadFailures = 0
        $script:downloadSleeps = @()
        Invoke-NativeCompilerDownload 'https://example.invalid/compiler' $archive
        if ($script:downloadAttempts -ne 1 -or $script:downloadSleeps.Count) {
            throw 'A successful compiler download was repeated'
        }
        [IO.File]::Delete($archive)
        Write-Host 'Compiler download: bounded retries, partial cleanup, recovery and final failure PASS'
    }
    # A pre-existing Arduino compiler must win over another download. Check
    # actual executables/version, not a matching version directory name.
    $data = Join-Path $work 'custom Arduino15'
    $env:ARDUINO_DIRECTORIES_DATA = $data
    $good = Join-Path $data 'packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/0.0.0/bin'
    $wrong = Join-Path $data 'packages/Arduino/tools/arm-none-eabi-gcc/14.2.1-1.1/bin'
    $incomplete = Join-Path $data 'packages/Arduino/tools/arm-none-eabi-gcc/99-incomplete/bin'
    $brokenHeaders = Join-Path $data 'packages/Arduino/tools/arm-none-eabi-gcc/98-broken-headers/bin'
    foreach ($bin in @($good, $wrong, $incomplete, $brokenHeaders)) {
        [void][IO.Directory]::CreateDirectory((Split-Path -Parent $bin))
        Copy-Item -LiteralPath $expected -Destination $bin -Recurse
    }
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    $wrongGcc = Join-Path $wrong "arm-none-eabi-gcc$suffix"
    Remove-Item -LiteralPath $wrongGcc
    if ($suffix) {
        Add-Type -Language CSharp -OutputType ConsoleApplication -OutputAssembly $wrongGcc -TypeDefinition @'
public static class OldGnuFixture {
    public static void Main() { System.Console.WriteLine("13.3.1"); }
}
'@
    } else {
        [IO.File]::WriteAllText($wrongGcc, "#!/bin/sh`necho 13.3.1`n")
        & chmod +x $wrongGcc
    }
    Remove-Item -LiteralPath (Join-Path $incomplete "arm-none-eabi-gcc-ar$suffix")
    $brokenCxx = Join-Path $brokenHeaders "arm-none-eabi-g++$suffix"
    Remove-Item -LiteralPath $brokenCxx
    if ($suffix) {
        Add-Type -Language CSharp -OutputType ConsoleApplication -OutputAssembly $brokenCxx -TypeDefinition @'
public static class BrokenCxxFixture {
    public static int Main() { return 93; }
}
'@
    } else {
        [IO.File]::WriteAllText($brokenCxx, "#!/bin/sh`nexit 93`n")
        & chmod +x $brokenCxx
    }
    $counter = Join-Path $project 'tools/firmware/stm32/compiler-installs.txt'
    $reuseTarget = Join-Path $work 'reuse/hardware/mk61/stm32'
    $reused = @(Get-Mk61NativeCompiler $project $reuseTarget '' -Install)
    if ($reused.Count -ne 1 -or $reused[0] -cne $good -or
        [IO.File]::ReadAllLines($counter).Count -ne 1) {
        throw 'Compatible Arduino compiler was not reused without a download'
    }
    $env:ARDUINO_DIRECTORIES_DATA = $emptyData
    Install-Mk61NativePayload $root $reuseTarget '' $data
    $env:ARDUINO_DIRECTORIES_DATA = $data
    $registration = [IO.File]::ReadAllText((Join-Path $reuseTarget 'platform.local.txt'))
    if (-not $registration.Contains('compiler.path=' + $good.Replace('\', '/') + '/') -or
        -not (Test-Mk61NativePayload $root $reuseTarget)) {
        throw 'Discovered Arduino compiler was not registered or failed the package check'
    }
    [IO.File]::WriteAllText((Join-Path $reuseTarget 'platform.local.txt'), 'compiler.path=' + $incomplete)
    if (Test-Mk61NativePayload $root $reuseTarget) {
        throw 'Read-only package check replaced an invalid registered compiler'
    }
    $repaired = @(Get-Mk61NativeCompiler $project $reuseTarget '' -Install)
    if ($repaired.Count -ne 1 -or $repaired[0] -cne $good) {
        throw 'Reinstall did not replace the incomplete registered compiler'
    }
    [IO.File]::WriteAllText((Join-Path $reuseTarget 'platform.local.txt'), 'compiler.path=' + $brokenHeaders)
    if ((Get-Mk61NativeCompiler $project $reuseTarget '' -Install) -cne $good) {
        throw 'Reinstall retained a compiler with broken C++ headers'
    }
    $explicit = Get-Mk61NativeCompiler $project $reuseTarget $expected -Install
    if ($explicit -cne $expected) { throw 'Discovery overrode an explicit compiler' }
    $invalidExplicitRejected = $false
    try { $null = Get-Mk61NativeCompiler $project $reuseTarget $wrong -Install }
    catch { $invalidExplicitRejected = $true }
    if (-not $invalidExplicitRejected) { throw 'Invalid explicit compiler silently fell back to discovery' }
    Remove-Item -LiteralPath (Join-Path $good "arm-none-eabi-gcc-ar$suffix")
    $fallbackTarget = Join-Path $work 'fallback/hardware/mk61/stm32'
    $fallback = @(Get-Mk61NativeCompiler $project $fallbackTarget '' -Install)
    if ($fallback.Count -ne 1 -or -not $fallback[0].StartsWith($fallbackTarget) -or
        [IO.File]::ReadAllLines($counter).Count -ne 2) {
        throw 'Missing compatible Arduino compiler did not trigger exactly one standalone install'
    }
    $env:ARDUINO_DIRECTORIES_DATA = $emptyData
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
    Write-Host 'Native Arduino compiler: discovery/reuse, actual version/tool validation, explicit override, stale registration repair, fallback install, SHA256 and Windows ASCII migration PASS'
} finally {
    $env:MK61_ARDUINO_TOOLCHAIN = $oldBoard
    $env:MK61_GCC_TOOLCHAIN = $oldNative
    $env:PUBLIC = $oldPublic
    $env:OS = $oldOs
    $env:ARDUINO_DIRECTORIES_DATA = $oldData
    if ([IO.Directory]::Exists($work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
