#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appsRoot = Join-Path $root 'system_apps'
$launcher = Join-Path $appsRoot 'build.cmd'
$wrapper = Join-Path $appsRoot '.tool/build.ps1'
$commonBuilder = Join-Path $root 'tools/build_system_app_bundle.py'
$appBuilder = Join-Path $root 'tools/build_portable_app.py'
$gccBuilder = Join-Path $root 'tools/.mk61-gcc/build.ps1'
$arduinoShell = Join-Path $root `
    'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-app-postbuild.sh'
$arduinoPowerShell = Join-Path $root `
    'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-app-postbuild.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Read-Le16 {
    param([byte[]]$Data, [int]$Offset)
    return [uint16]([uint16]$Data[$Offset] -bor
        ([uint16]$Data[$Offset + 1] -shl 8))
}

function Read-Le32 {
    param([byte[]]$Data, [int]$Offset)
    return [uint32]([uint32]$Data[$Offset] -bor
        ([uint32]$Data[$Offset + 1] -shl 8) -bor
        ([uint32]$Data[$Offset + 2] -shl 16) -bor
        ([uint32]$Data[$Offset + 3] -shl 24))
}

foreach ($file in @(
    $launcher, $wrapper, $commonBuilder, $appBuilder, $gccBuilder,
    $arduinoShell, $arduinoPowerShell
)) {
    Assert-True (Test-Path -LiteralPath $file -PathType Leaf) `
        "unified APP build file is missing: $file"
}

$launcherText = [IO.File]::ReadAllText($launcher)
Assert-True ($launcherText -match
    '\A:; exec pwsh -NoLogo -NoProfile -File "\$\(dirname "\$0"\)/\.tool/build\.ps1" "\$@"') `
    'System APP launcher is not a shell/batch polyglot'
Assert-True ($launcherText -match
    '(?i)powershell\.exe -NoLogo -NoProfile -ExecutionPolicy Bypass') `
    'Windows PowerShell fallback is missing'

$tokens = $null
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile(
    $wrapper, [ref]$tokens, [ref]$parseErrors)
Assert-True ($parseErrors.Count -eq 0) (
    "$wrapper has parser errors: " +
    (@($parseErrors | ForEach-Object { $_.Message }) -join '; '))

$wrapperText = [IO.File]::ReadAllText($wrapper)
$commonText = [IO.File]::ReadAllText($commonBuilder)
$appText = [IO.File]::ReadAllText($appBuilder)
$gccText = [IO.File]::ReadAllText($gccBuilder)
$arduinoShellText = [IO.File]::ReadAllText($arduinoShell)
$arduinoPowerShellText = [IO.File]::ReadAllText($arduinoPowerShell)

Assert-True ($wrapperText -match 'tools/build_system_app_bundle\.py') `
    'PowerShell wrapper does not delegate to the common builder'
Assert-True ($wrapperText -notmatch 'arm-none-eabi-(?:g\+\+|objcopy|nm)') `
    'PowerShell wrapper still contains a second APP compiler pipeline'
Assert-True ($commonText -match 'tools/build_portable_app\.py') `
    'System bundle does not use the ordinary APP builder'
Assert-True ($commonText -match '"setup", "SETUP\.APP"') `
    'mandatory SETUP.APP is missing from the common bundle'
Assert-True ($commonText -match 'HELP0\.TXT.+HELP1\.TXT') `
    'terminal help is missing from the common bundle'
Assert-True ($commonText -match '"abi": 5') `
    'common bundle does not report current ABI 5'
Assert-True ($appText -match '"abi": 5') `
    'ordinary and System APP builder is not current ABI 5'
Assert-True ($appText -match 'sdk/portable/start\.c') `
    'System APP does not share the ordinary SDK startup'
Assert-True ($appText -notmatch 'resident_imports[^\n]+[1-9]') `
    'APP builder still advertises resident symbol imports'
Assert-True ($gccText -match 'system_apps/\.tool/build\.ps1') `
    'direct GCC builder does not call the common System APP wrapper'
Assert-True ($arduinoShellText -match 'build_system_app_bundle\.py') `
    'Arduino shell hook does not use the common System APP builder'
Assert-True ($arduinoPowerShellText -match 'build_system_app_bundle\.py') `
    'Arduino PowerShell hook does not use the common System APP builder'

foreach ($obsolete in @(
    'system_apps/focal/main.cpp', 'system_apps/basic/main.cpp',
    'system_apps/wbmp/main.cpp', 'system_apps/markdown/main.cpp',
    'system_apps/chip8/main.cpp', 'code/loadable_module_imports.cpp',
    'tools/.mk61-gcc/system-app-exports.list'
)) {
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $root $obsolete))) `
        "obsolete private System APP path remains: $obsolete"
}

# A real ARM build is optional in the fast suite. Release/HIL jobs set this to
# a current resident build directory and exercise the exact same wrapper.
$integrationBuild = [Environment]::GetEnvironmentVariable(
    'MK61_SYSTEM_APPS_BUILD_PATH')
if (-not [string]::IsNullOrWhiteSpace($integrationBuild)) {
    $integrationBuild = [IO.Path]::GetFullPath($integrationBuild)
    $output = Join-Path ([IO.Path]::GetTempPath()) (
        'mk61-system-apps-' + [guid]::NewGuid().ToString('N'))
    try {
        $powerShell = (Get-Process -Id $PID).Path
        & $powerShell -NoLogo -NoProfile -File $wrapper `
            -BuildPath $integrationBuild `
            -OutputDirectory $output `
            -Focal 1 -Basic 1 -Wbmp 1 -Markdown 1 -Chip8 1
        Assert-True ($LASTEXITCODE -eq 0) 'real unified System APP build failed'

        Assert-True (-not (Test-Path -LiteralPath (
            Join-Path $output 'WBMP.APP'))) `
            'WBMP.APP was built together with MARKDOWN.APP'
        $expected = [ordered]@{
            'FOCAL.APP' = 1
            'BASIC.APP' = 2
            'MARKDOWN.APP' = 6
            'CHIP8.APP' = 5
            'SETUP.APP' = 7
        }
        foreach ($name in $expected.Keys) {
            $path = Join-Path $output $name
            Assert-True (Test-Path -LiteralPath $path -PathType Leaf) `
                "$name was not built"
            [byte[]]$bytes = [IO.File]::ReadAllBytes($path)
            Assert-True ($bytes.Length -ge 64 -and $bytes.Length -le 20544) `
                "$name has an invalid container size"
            Assert-True (
                [Text.Encoding]::ASCII.GetString($bytes, 0, 8) -eq
                "MK61APP`0") "$name has invalid magic"
            Assert-True ((Read-Le16 $bytes 12) -eq 5) "$name is not ABI 5"
            Assert-True ($bytes[14] -eq $expected[$name]) `
                "$name has an invalid kind"
            Assert-True ($bytes[15] -eq 1) "$name is not ZX0-compressed"
            $flags = Read-Le32 $bytes 16
            Assert-True (($flags -band 5) -eq 5) `
                "$name is not a relocatable portable APP"
            Assert-True ((Read-Le32 $bytes 20) -eq 0x20000000) `
                "$name lost the relocation reference base"
            Assert-True ((Read-Le32 $bytes 44) -gt 0) `
                "$name has no relocation table"
        }
        foreach ($name in @('HELP0.TXT', 'HELP1.TXT')) {
            Assert-True (Test-Path -LiteralPath (Join-Path $output $name)) `
                "$name missing"
        }
    } finally {
        Remove-Item -LiteralPath $output -Recurse -Force `
            -ErrorAction SilentlyContinue
    }
}

[Console]::WriteLine('system_apps_tool_tests: ok')
