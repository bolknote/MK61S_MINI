#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('setup', 'focal', 'tinybasic', 'wbmp-viewer',
                 'markdown-viewer', 'chip8', 'usbdisk', 'explorer')]
    [string]$System,
    [Parameter(Mandatory = $true)]
    [string]$ArmToolchainBin,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [switch]$NoUiFonts,
    [switch]$TextOnly,
    [switch]$LocalFloatMath,
    [int]$LocalFloatMathMask = -1
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
$DefaultLocalFloatMask = 0x3C0

$Systems = @{
    'setup' = @{
        Name = 'SETUP'; Macro = 'SETUP'; Magic = $null
        Sources = @('setup_ui.cpp', 'setup_module_entry.cpp',
            'setup_font_compiler.cpp', 'fmk_font.cpp', 'fmk_prepare.cpp',
            'prepared_font.cpp')
    }
    'focal' = @{
        Name = 'FOCAL'; Macro = 'FOCAL'; Magic = $null
        Sources = @('focal.cpp', 'focal_module_entry.cpp')
    }
    'tinybasic' = @{
        Name = 'BASIC'; Macro = 'TINYBASIC'; Magic = $null
        Sources = @('tinybasic.cpp', 'tinybasic_module_entry.cpp')
    }
    'wbmp-viewer' = @{
        Name = 'WBMP'; Macro = 'WBMP'; Magic = 'I1'
        Sources = @('image1_viewer.cpp', 'image1_viewer_module_entry.cpp',
            'wbmp.cpp')
    }
    'markdown-viewer' = @{
        Name = 'MARKDOWN'; Macro = 'MARKDOWN'; Magic = 'T2'
        Sources = @('markdown_document.cpp', 'markdown_viewer.cpp',
            'markdown_viewer_module_entry.cpp', 'image1_viewer.cpp',
            'wbmp.cpp')
    }
    'chip8' = @{
        Name = 'CHIP8'; Macro = 'CHIP8'; Magic = 'C1'
        Sources = @('chip8.cpp', 'chip8_runner.cpp',
            'chip8_module_entry.cpp')
    }
    'usbdisk' = @{
        Name = 'USBDISK'; Macro = 'USBDISK'; Magic = $null
        Sources = @('virtual_fat.cpp', 'virtual_fat_diagnostic.cpp',
            'usbdisk_module_entry.cpp')
    }
    'explorer' = @{
        Name = 'EXPLORER'; Macro = 'EXPLORER'; Magic = $null
        Sources = @('explorer_ui.cpp', 'explorer_autoexec.cpp', 'explorer_module_entry.cpp')
    }
}

function Invoke-ArmTool {
    param([string]$Path, [string[]]$Arguments, [switch]$Capture)
    if ($Capture) {
        $lines = @(& $Path @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        $text = ($lines | Out-String).TrimEnd()
        if ($exitCode -ne 0) {
            throw "$([IO.Path]::GetFileName($Path)) failed with exit code " +
                "${exitCode}:`n$text"
        }
        return $text
    }
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$([IO.Path]::GetFileName($Path)) failed with exit code $LASTEXITCODE"
    }
}

function Get-ArmTool {
    param([string]$Name)
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    $path = Join-Path $script:Toolchain "arm-none-eabi-$Name$suffix"
    if (-not [IO.File]::Exists($path)) { throw "ARM tool is missing: $path" }
    return $path
}

function Get-StackSummary {
    param([object[]]$Commands, [string]$Directory)
    $stackDirectory = Join-Path $Directory '.mk61-stack-analysis'
    [IO.Directory]::CreateDirectory($stackDirectory) | Out-Null
    $compiled = 0
    foreach ($command in $Commands) {
        if ($command.Assembly) { continue }
        $analysis = New-Object 'System.Collections.Generic.List[string]'
        foreach ($argument in $command.Arguments) {
            if ($argument -eq '-flto' -or $argument -like '-flto=*') { continue }
            $analysis.Add([string]$argument)
        }
        $analysis.Add('-fno-lto')
        $analysis.Add('-fstack-usage')
        $analysis.Add('-c')
        $analysis.Add($command.Source)
        $analysis.Add('-o')
        $analysis.Add((Join-Path $stackDirectory "unit-$compiled.o"))
        Invoke-ArmTool $command.Compiler $analysis.ToArray()
        $compiled++
    }
    $reports = @(Get-ChildItem -LiteralPath $stackDirectory -Recurse `
        -Filter '*.su' -File)
    if ($reports.Count -eq 0) { throw 'stack analysis produced no .su reports' }
    $records = New-Object 'System.Collections.Generic.List[object]'
    foreach ($report in $reports) {
        $lineNumber = 0
        foreach ($line in [IO.File]::ReadAllLines($report.FullName)) {
            $lineNumber++
            if ([string]::IsNullOrEmpty($line)) { continue }
            if ($line -notmatch '^(.*)\t([0-9]+)\t([^\t]+)$') {
                throw "$($report.FullName):${lineNumber}: malformed stack-usage record"
            }
            $qualifier = $Matches[3]
            $tokens = @($qualifier -split ',')
            foreach ($token in $tokens) {
                if ($token -notin @('static', 'dynamic', 'bounded')) {
                    throw "$($report.FullName):${lineNumber}: unknown qualifier $qualifier"
                }
            }
            $dynamic = $tokens -contains 'dynamic'
            $static = $tokens -contains 'static'
            if ($dynamic -eq $static -or
                (($tokens -contains 'bounded') -and -not $dynamic)) {
                throw "$($report.FullName):${lineNumber}: invalid qualifier $qualifier"
            }
            $records.Add([pscustomobject]@{
                Description = $Matches[1]
                Bytes = [int]$Matches[2]
                Qualifier = $qualifier
                Unbounded = $dynamic -and -not ($tokens -contains 'bounded')
                Report = $report.FullName
            })
        }
    }
    if ($records.Count -eq 0) { throw 'all stack-usage reports are empty' }
    $ranked = @($records | Sort-Object `
        @{Expression = 'Bytes'; Descending = $true}, `
        @{Expression = 'Description'; Descending = $true})
    $failures = New-Object 'System.Collections.Generic.List[string]'
    foreach ($record in $records) {
        if ($record.Unbounded) {
            $failures.Add("unbounded dynamic frame: $($record.Description) " +
                "($($record.Bytes) bytes, $($record.Report))")
        }
        if ($record.Bytes -gt 5120) {
            $failures.Add("frame exceeds 5120 bytes: $($record.Description) " +
                "($($record.Bytes) bytes, $($record.Report))")
        }
    }
    Write-Host "stack analysis: compiled=$compiled shipping_artifact=untouched"
    Write-Host ("STACK frame=$($ranked[0].Bytes) " +
        "qualifier=$($ranked[0].Qualifier) " +
        "function=$($ranked[0].Description)")
    if ($failures.Count -gt 0) {
        foreach ($failure in $failures) {
            [Console]::Error.WriteLine("stack usage: FAIL: $failure")
        }
        throw 'stack usage policy failed'
    }
    $bounded = @($records | Where-Object {
        $_.Qualifier -split ',' -contains 'dynamic'
    }).Count
    Write-Host ("stack usage: OK files=$($reports.Count) " +
        "records=$($records.Count) max=$($ranked[0].Bytes) " +
        "limit=5120 dynamic_bounded=$bounded")
    $description = $ranked[0].Description -replace
        '^.*[/\\](?=[^/\\]+:\d+:\d+:)', ''
    $summary = [ordered]@{
        schema = 1
        records = $records.Count
        max_frame = $ranked[0].Bytes
        max_function = $description
        limit = 5120
        dynamic_bounded = $bounded
        unbounded = 0
        status = 'ok'
        compiled_units = $compiled
    }
    [IO.File]::WriteAllText(
        (Join-Path $Directory 'stack-usage.json'),
        ($summary | ConvertTo-Json) + [Environment]::NewLine,
        $script:Utf8NoBom)
}

function Get-Symbols {
    param([string]$Nm, [string]$Elf)
    $output = Invoke-ArmTool $Nm @('--defined-only', $Elf) -Capture
    $symbols = @{}
    foreach ($line in $output -split "`r?`n") {
        if ($line -match '^([0-9a-fA-F]+)\s+\S\s+(.+)$') {
            $symbols[$Matches[2]] = [Convert]::ToUInt32($Matches[1], 16)
        }
    }
    return $symbols
}

function Assert-SizeBudget {
    param([hashtable]$Report)
    $appLimit = $null
    $memoryLimit = $null
    if ($LocalFloatMath) {
        if ($System -eq 'focal') { $appLimit = 15100; $memoryLimit = 20000 }
        elseif ($System -eq 'tinybasic') { $appLimit = 13000; $memoryLimit = 17500 }
    } else {
        if ($System -eq 'setup') { $appLimit = 10000; $memoryLimit = 20480 }
        elseif ($System -eq 'focal') { $appLimit = 13500; $memoryLimit = 17000 }
        elseif ($System -eq 'explorer') { $appLimit = 8000; $memoryLimit = 10000 }
    }
    $failures = @()
    if ($null -ne $appLimit -and $Report.app_bytes -gt $appLimit) {
        $failures += "app_bytes=$($Report.app_bytes) > $appLimit"
    }
    if ($null -ne $memoryLimit -and $Report.memory_bytes -gt $memoryLimit) {
        $failures += "memory_bytes=$($Report.memory_bytes) > $memoryLimit"
    }
    if ($failures.Count -gt 0) {
        throw "$System size budget exceeded: $($failures -join ', ')"
    }
}

try {
    if ($TextOnly -and $System -ne 'markdown-viewer') {
        throw '-TextOnly applies to markdown-viewer'
    }
    if ($LocalFloatMath -and $System -notin @('focal', 'tinybasic')) {
        throw '-LocalFloatMath applies only to FOCAL or TinyBASIC'
    }
    if ($LocalFloatMathMask -ge 0 -and -not $LocalFloatMath) {
        throw '-LocalFloatMathMask requires -LocalFloatMath'
    }
    if ($LocalFloatMathMask -gt 0x7FF) {
        throw '-LocalFloatMathMask must fit 11 operation bits'
    }
    $script:Toolchain = [IO.Path]::GetFullPath($ArmToolchainBin)
    $gcc = Get-ArmTool 'gcc'
    $gxx = Get-ArmTool 'g++'
    $nm = Get-ArmTool 'nm'
    $objcopy = Get-ArmTool 'objcopy'
    $output = [IO.Path]::GetFullPath($OutputDirectory)
    [IO.Directory]::CreateDirectory($output) | Out-Null
    $definition = $Systems[$System]
    $name = [string]$definition.Name

    $sources = New-Object 'System.Collections.Generic.List[string]'
    $sources.Add((Join-Path $ProjectRoot 'sdk/portable/start.c'))
    $sources.Add((Join-Path $ProjectRoot `
        'sdk/portable/system/system_compat.cpp'))
    foreach ($source in $definition.Sources) {
        $sources.Add((Join-Path (Join-Path $ProjectRoot 'code') $source))
    }
    if ($System -eq 'setup') {
        $sources.Add((Join-Path $ProjectRoot `
            'sdk/portable/system/setup_compat.cpp'))
    }
    if ($System -eq 'usbdisk') {
        $sources.Add((Join-Path $ProjectRoot `
            'sdk/portable/system/usbdisk_compat.cpp'))
    }
    if ($System -notin @('focal', 'tinybasic')) {
        $sources.Add((Join-Path $ProjectRoot 'sdk/portable/memory.c'))
    } else {
        $sources.Add((Join-Path $ProjectRoot `
            'sdk/portable/system/runtime.S'))
        $sources.Add((Join-Path $ProjectRoot `
            'sdk/portable/system/editor.cpp'))
    }
    $unique = @($sources | Select-Object -Unique)
    if ($unique.Count -ne $sources.Count) { throw 'duplicate source' }

    $flags = @('-mcpu=cortex-m4', '-mthumb', '-mfpu=fpv4-sp-d16',
        '-mfloat-abi=hard', '-Oz', '-flto', '-fipa-pta',
        '-mword-relocations', '-fno-builtin', '-ffunction-sections',
        '-fdata-sections', '-Wall', '-Wextra', '-Werror')
    $includes = @(
        ('-I' + (Join-Path $ProjectRoot 'sdk/portable/system')),
        ('-I' + (Join-Path $ProjectRoot 'sdk/portable/include')),
        ('-I' + (Join-Path $ProjectRoot 'code')))
    $objects = New-Object 'System.Collections.Generic.List[string]'
    $compileCommands = New-Object 'System.Collections.Generic.List[object]'
    $index = 0
    foreach ($source in $sources) {
        if (-not [IO.File]::Exists($source)) { throw "source not found: $source" }
        $extension = [IO.Path]::GetExtension($source)
        if ($extension -notin @('.c', '.cpp', '.S')) {
            throw "expected an existing .c, .cpp or .S source: $source"
        }
        $object = Join-Path $output "$index-$([IO.Path]::GetFileName($source)).o"
        $cpp = $extension -eq '.cpp'
        $compiler = if ($cpp) { $gxx } else { $gcc }
        $arguments = New-Object 'System.Collections.Generic.List[string]'
        foreach ($flag in $flags) { $arguments.Add($flag) }
        if ((Join-Path $ProjectRoot 'sdk/portable/memory.c') -eq $source) {
            $arguments.Add('-fno-lto')
        }
        if ($cpp) {
            foreach ($flag in @('-DMK61_BUILD_PORTABLE_SYSTEM',
                "-DMK61_BUILD_$($definition.Macro)_MODULE",
                '-include', (Join-Path $ProjectRoot `
                    'sdk/portable/system/system_compat.hpp'))) {
                $arguments.Add($flag)
            }
            if ($LocalFloatMath) {
                $mask = if ($LocalFloatMathMask -ge 0) {
                    $LocalFloatMathMask
                } else { $DefaultLocalFloatMask }
                $arguments.Add('-DMK61_APP_LOCAL_FLOAT_MATH=1')
                $arguments.Add(('-DMK61_APP_LOCAL_FLOAT_MATH_MASK=0x{0:x}' -f $mask))
            }
            if ($NoUiFonts) { $arguments.Add('-DMK61_PORTABLE_UI_FONTS=0') }
            if ($TextOnly) { $arguments.Add('-DMK61_PORTABLE_TEXT_ONLY=1') }
            foreach ($flag in @('-std=c++17', '-fno-exceptions', '-fno-rtti',
                '-fno-threadsafe-statics', '-fno-use-cxa-atexit')) {
                $arguments.Add($flag)
            }
        } elseif ($extension -eq '.c') {
            $arguments.Add('-std=c11')
        }
        foreach ($include in $includes) { $arguments.Add($include) }
        Invoke-ArmTool $compiler ($arguments.ToArray() +
            @('-c', $source, '-o', $object))
        $compileCommands.Add([pscustomobject]@{
            Compiler = $compiler
            Arguments = $arguments.ToArray()
            Source = $source
            Assembly = $extension -eq '.S'
        })
        $objects.Add($object)
        $index++
    }
    Get-StackSummary $compileCommands.ToArray() $output

    $elf = Join-Path $output "$name.elf"
    $map = Join-Path $output "$name.map"
    $link = New-Object 'System.Collections.Generic.List[string]'
    foreach ($flag in $flags) { $link.Add($flag) }
    foreach ($flag in @('-nostdlib', '-nostartfiles', '-Wl,--gc-sections,--emit-relocs',
        '-Wl,--defsym=MK61_MODULE_ORIGIN=0x20000000',
        ('-Wl,-T,' + (Join-Path $ProjectRoot `
            'tools/.mk61-app/mk61_module.ld')),
        ('-Wl,-Map,' + $map))) { $link.Add($flag) }
    foreach ($object in $objects) { $link.Add($object) }
    if ($LocalFloatMath) { $link.Add('-lm') }
    $link.Add('-lc')
    $link.Add('-lgcc')
    $link.Add('-o')
    $link.Add($elf)
    Invoke-ArmTool $gxx $link.ToArray()
    $undefined = Invoke-ArmTool $nm @('--undefined-only', $elf) -Capture
    if (-not [string]::IsNullOrWhiteSpace($undefined)) {
        throw "APP has unresolved imports:`n$undefined"
    }
    $symbols = Get-Symbols $nm $elf
    foreach ($symbol in @('__module_image_start', '__module_memory_end',
                           'mk61_module_entry')) {
        if (-not $symbols.ContainsKey($symbol)) {
            throw "APP symbol is missing: $symbol"
        }
    }
    [uint32]$base = $symbols['__module_image_start']
    $memorySize = [int]($symbols['__module_memory_end'] - $base)
    [uint32]$entryAddress = $symbols['mk61_module_entry'] -band
        [uint32]4294967294
    $entryOffset = [int]($entryAddress - $base)
    if ($base -ne [uint32]0x20000000) { throw 'portable SRAM base changed' }
    $image = Join-Path $output "$name.bin"
    $app = Join-Path $output "$name.APP"
    Invoke-ArmTool $objcopy @('-O', 'binary', '-j', '.module_image',
        $elf, $image)
    if (-not ('Mk61.Build.AppPacker' -as [type])) {
        Add-Type -Path (Join-Path $ProjectRoot `
            'tools/.mk61-app/Mk61AppPacker.cs')
    }
    $relocations = Join-Path $output "$name.rel"
    $imageSize = [int](Get-Item -LiteralPath $image).Length
    $relocationCount = [Mk61.Build.AppPacker]::ExtractRelocations(
        $elf, $base, $imageSize, $memorySize, $relocations)
    $packed = [Mk61.Build.AppPacker]::PackFile(
        $System, $image, $relocations, $memorySize, $entryOffset,
        $base, $definition.Magic, $app)
    $selected = if ($packed.UsesBcj) { 'BCJ' } else { 'plain' }
    Write-Host ("ZX0 candidates: plain=$($packed.PlainBytes) " +
        "BCJ=$($packed.BcjBytes); selected=$selected")
    $ratio = ($packed.AppBytes - 64) * 100.0 / $imageSize
    Write-Host ('{0}: {1} bytes, payload ratio {2:F1}%' -f
        $app, $packed.AppBytes, $ratio)
    $compilerVersion = (Invoke-ArmTool $gcc @('--version') -Capture `
        -ErrorAction Stop) -split "`r?`n" | Select-Object -First 1
    $report = [ordered]@{
        name = $name
        abi = 6
        load_address = [uint64]$base
        relocations = $relocationCount
        relocation_bytes = [int](Get-Item -LiteralPath $relocations).Length
        entry_offset = $entryOffset
        image_bytes = $imageSize
        bss_bytes = $memorySize - $imageSize
        memory_bytes = $memorySize
        app_bytes = $packed.AppBytes
        compression = if ($packed.UsesBcj) { 'ZX0+BCJ' } else { 'ZX0' }
        zx0_parser = 'greedy-dotnet'
        resident_imports = 0
        compiler = $compilerVersion
    }
    if ($LocalFloatMath) {
        $report.local_float_math_mask = if ($LocalFloatMathMask -ge 0) {
            $LocalFloatMathMask
        } else { $DefaultLocalFloatMask }
    }
    Assert-SizeBudget $report
    $json = $report | ConvertTo-Json
    [IO.File]::WriteAllText(
        (Join-Path $output "$name.json"),
        $json + [Environment]::NewLine, $Utf8NoBom)
    Write-Host $json
} catch {
    [Console]::Error.WriteLine(
        "portable APP build: $($_.Exception.Message)")
    exit 1
}
