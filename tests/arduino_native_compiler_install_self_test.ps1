#requires -Version 5.1
# First-install child process must print progress without returning it as a path.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tools/.mk61-arduino-board/payload.ps1')
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61 native install ' + [Guid]::NewGuid().ToString('N'))
$oldBoard = $env:MK61_ARDUINO_TOOLCHAIN
$oldNative = $env:MK61_GCC_TOOLCHAIN
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
    Write-Host 'Native Arduino first install: progress is not compiler.path PASS'
} finally {
    $env:MK61_ARDUINO_TOOLCHAIN = $oldBoard
    $env:MK61_GCC_TOOLCHAIN = $oldNative
    if ([IO.Directory]::Exists($work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
