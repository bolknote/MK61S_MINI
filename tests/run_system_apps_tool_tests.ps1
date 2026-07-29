#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appsRoot = Join-Path $root 'system_apps'
$launcher = Join-Path $appsRoot 'build.cmd'
$builder = Join-Path (Join-Path $appsRoot '.tool') 'build.ps1'
$gccBuilder = Join-Path (
    Join-Path (Join-Path $root 'tools') '.mk61-gcc'
) 'build.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Read-Le32 {
    param([byte[]]$Data, [int]$Offset)
    return [uint32](
        [uint32]$Data[$Offset] -bor
        ([uint32]$Data[$Offset + 1] -shl 8) -bor
        ([uint32]$Data[$Offset + 2] -shl 16) -bor
        ([uint32]$Data[$Offset + 3] -shl 24))
}

function Read-Le16 {
    param([byte[]]$Data, [int]$Offset)
    return [uint16](
        [uint16]$Data[$Offset] -bor
        ([uint16]$Data[$Offset + 1] -shl 8))
}

function Get-Crc32 {
    param([byte[]]$Data)
    [uint32]$state = [uint32]::MaxValue
    foreach ($value in $Data) {
        $state = [uint32]($state -bxor [uint32]$value)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($state -band [uint32]1) -ne 0) {
                $state = [uint32](($state -shr 1) -bxor
                    [uint32]3988292384)
            } else {
                $state = [uint32]($state -shr 1)
            }
        }
    }
    return [uint32]($state -bxor [uint32]::MaxValue)
}

Assert-True (Test-Path -LiteralPath $launcher -PathType Leaf) `
    'System APP launcher is missing'
Assert-True (Test-Path -LiteralPath $builder -PathType Leaf) `
    'System APP PowerShell builder is missing'
Assert-True (Test-Path -LiteralPath $gccBuilder -PathType Leaf) `
    'direct GCC F401 builder is missing'
Assert-True (-not (Test-Path -LiteralPath (
    Join-Path $root 'tools/.mk61-firmware/build-f401-native.ps1'))) `
    'obsolete Arduino-CLI F401 worker is still present'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $root 'focal_app'))) `
    'obsolete focal-only directory is still present'

$launcherText = [IO.File]::ReadAllText($launcher)
Assert-True ($launcherText -match
    '\A:; exec pwsh -NoLogo -NoProfile -File "\$\(dirname "\$0"\)/\.tool/build\.ps1" "\$@"') `
    'System APP launcher is not a shell/batch polyglot'
Assert-True ($launcherText -match
    '(?i)powershell\.exe -NoLogo -NoProfile -ExecutionPolicy Bypass') `
    'Windows PowerShell fallback is missing'

foreach ($file in @($builder, $gccBuilder)) {
    $tokens = $null
    $parseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile(
        $file, [ref]$tokens, [ref]$parseErrors)
    Assert-True ($parseErrors.Count -eq 0) (
        "$file has parser errors: " +
        (@($parseErrors | ForEach-Object { $_.Message }) -join '; '))
}

$sources = @(
    @{
        Path = Join-Path (Join-Path $appsRoot 'focal') 'main.cpp'
        Macro = 'MK61_BUILD_FOCAL_MODULE'
        Includes = @('focal.cpp', 'focal_module_entry.cpp')
    }
    @{
        Path = Join-Path (Join-Path $appsRoot 'basic') 'main.cpp'
        Macro = 'MK61_BUILD_TINYBASIC_MODULE'
        Includes = @('tinybasic.cpp', 'tinybasic_module_entry.cpp')
    }
    @{
        Path = Join-Path (Join-Path $appsRoot 'wbmp') 'main.cpp'
        Macro = 'MK61_BUILD_WBMP_MODULE'
        Includes = @(
            'wbmp.cpp',
            'image1_viewer.cpp',
            'image1_viewer_module_entry.cpp')
    }
    @{
        Path = Join-Path (Join-Path $appsRoot 'markdown') 'main.cpp'
        Macro = 'MK61_BUILD_MARKDOWN_MODULE'
        Includes = @(
            'markdown_document.cpp',
            'wbmp.cpp',
            'markdown_viewer.cpp',
            'markdown_viewer_module_entry.cpp')
    }
    @{
        Path = Join-Path (Join-Path $appsRoot 'chip8') 'main.cpp'
        Macro = 'MK61_BUILD_CHIP8_MODULE'
        Includes = @(
            'chip8.cpp',
            'chip8_runner.cpp',
            'chip8_module_entry.cpp')
    }
)
foreach ($source in $sources) {
    Assert-True (Test-Path -LiteralPath $source.Path -PathType Leaf) `
        "module source is missing: $($source.Path)"
    $text = [IO.File]::ReadAllText($source.Path)
    Assert-True ($text -match [regex]::Escape($source.Macro)) `
        "$($source.Path) does not enable its module"
    foreach ($include in $source.Includes) {
        Assert-True ($text -match [regex]::Escape($include)) `
            "$($source.Path) does not include $include"
    }
}

$builderText = [IO.File]::ReadAllText($builder)
foreach ($name in @(
    'FOCAL.APP', 'BASIC.APP', 'WBMP.APP', 'MARKDOWN.APP', 'CHIP8.APP'
)) {
    Assert-True ($builderText -match [regex]::Escape($name)) `
        "$name is missing from the standalone builder"
}
Assert-True ($builderText -match "Get-RelatedTool.+?'objcopy'") `
    'standalone builder does not derive objcopy'
Assert-True ($builderText -match "Get-RelatedTool.+?'nm'") `
    'standalone builder does not derive nm'
Assert-True ($builderText -match 'compile_commands\.json') `
    'standalone builder does not consume the resident compile database'
Assert-True ($builderText -match
    'tools/\.mk61-app/mk61_module\.ld') `
    'standalone builder does not use the canonical APP linker script'
Assert-True ($builderText -notmatch
    "ProjectRoot 'tools/mk61_module\.ld'") `
    'standalone builder still references the removed linker script path'
Assert-True ($builderText -notmatch 'mk61_ide_.*\.cpp\.o') `
    'standalone builder still consumes Arduino System APP objects'
Assert-True ($builderText -match
    "\^-flto\(\?:=\.\*\)\?\$[\s\S]+-fno-fat-lto-objects") `
    'standalone builder does not normalize resident LTO flags'

$gccText = [IO.File]::ReadAllText($gccBuilder)
Assert-True ($gccText -match 'system_apps/\.tool/build\.ps1') `
    'direct GCC builder does not call the standalone System APP builder'
Assert-True ($gccText -match '"-DMK61_ENABLE_CHIP8=\$Chip8"') `
    'direct GCC builder does not forward the CHIP-8 selection'
Assert-True ($gccText -match
    '"-DMK61_ENABLE_MARKDOWN_VIEWER=\$Markdown"') `
    'direct GCC builder does not forward the Markdown selection'
Assert-True ($gccText -notmatch 'mk61-app-postbuild') `
    'direct GCC builder still uses Arduino APP post-build objects'

$integrationBuild = [Environment]::GetEnvironmentVariable(
    'MK61_SYSTEM_APPS_BUILD_PATH')
if (-not [string]::IsNullOrWhiteSpace($integrationBuild)) {
    $integrationBuild = [IO.Path]::GetFullPath($integrationBuild)
    $output = Join-Path ([IO.Path]::GetTempPath()) (
        'mk61-system-apps-' + [guid]::NewGuid().ToString('N'))
    try {
        $powerShell = (Get-Process -Id $PID).Path
        & $powerShell -NoLogo -NoProfile -File $builder `
            -BuildPath $integrationBuild `
            -OutputDirectory $output `
            -Focal 1 -Basic 1 -Wbmp 1 -Markdown 1 -Chip8 1
        Assert-True ($LASTEXITCODE -eq 0) `
            'real standalone System APP build failed'

        $resident = @(Get-ChildItem -LiteralPath $integrationBuild -File |
            Where-Object { $_.Extension -ieq '.bin' })
        Assert-True ($resident.Count -eq 1) `
            'integration build must contain one resident BIN'
        $expectedResidentSize = [uint32]$resident[0].Length
        [byte[]]$residentBytes = [IO.File]::ReadAllBytes(
            $resident[0].FullName)
        [uint32]$expectedResidentCrc = Get-Crc32 $residentBytes
        $expected = [ordered]@{
            'FOCAL.APP' = 1
            'BASIC.APP' = 2
            'WBMP.APP' = 3
            'MARKDOWN.APP' = 6
            'CHIP8.APP' = 5
        }
        $expectedMagic = @{
            'FOCAL.APP' = [uint16]0
            'BASIC.APP' = [uint16]0
            'WBMP.APP' = [uint16]0x3149
            'MARKDOWN.APP' = [uint16]0x3254
            'CHIP8.APP' = [uint16]0x3143
        }
        foreach ($name in $expected.Keys) {
            $path = Join-Path $output $name
            Assert-True (Test-Path -LiteralPath $path -PathType Leaf) `
                "$name was not built"
            [byte[]]$bytes = [IO.File]::ReadAllBytes($path)
            Assert-True ($bytes.Length -le 20544) "$name exceeds APP limit"
            Assert-True (
                [Text.Encoding]::ASCII.GetString($bytes, 0, 8) -eq
                "MK61APP`0") "$name has invalid magic"
            Assert-True ($bytes[14] -eq $expected[$name]) `
                "$name has an invalid kind"
            Assert-True ($bytes[15] -eq 0) `
                "$name is not an uncompressed ARM-built APP"
            Assert-True (
                (Read-Le16 $bytes 56) -eq $expectedMagic[$name]) `
                "$name has an invalid handled type magic"
            Assert-True ((Read-Le16 $bytes 58) -eq 0) `
                "$name has non-zero reserved header bytes"
            Assert-True ((Read-Le32 $bytes 40) -eq $expectedResidentSize) `
                "$name is bound to a different resident size"
            Assert-True ((Read-Le32 $bytes 44) -eq $expectedResidentCrc) `
                "$name is bound to a different resident CRC"
            Assert-True (
                (Read-Le32 $bytes 24) + 64 -eq $bytes.Length) `
                "$name stored size differs from its container"
            [byte[]]$payload = $bytes[64..($bytes.Length - 1)]
            [uint32]$payloadCrc = Get-Crc32 $payload
            Assert-True (
                (Read-Le32 $bytes 48) -eq $payloadCrc -and
                (Read-Le32 $bytes 52) -eq $payloadCrc) `
                "$name payload CRC differs"
            [byte[]]$headerPrefix = $bytes[0..59]
            Assert-True (
                (Read-Le32 $bytes 60) -eq (Get-Crc32 $headerPrefix)) `
                "$name header CRC differs"
        }
    } finally {
        Remove-Item -LiteralPath $output -Recurse -Force `
            -ErrorAction SilentlyContinue
    }
}

[Console]::WriteLine('system_apps_tool_tests: ok')
