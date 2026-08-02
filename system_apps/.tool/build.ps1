#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BuildPath,

    [string]$ResidentElf,
    [string]$ResidentBin,
    [string]$CompileCommands,
    [string]$OutputDirectory,
    [string]$ModulePacker,

    [ValidateSet('0', '1')]
    [string]$Focal = '1',

    [ValidateSet('0', '1')]
    [string]$Basic = '1',

    [ValidateSet('0', '1')]
    [string]$Wbmp = '1',

    [ValidateSet('0', '1')]
    [string]$Markdown = '1',

    [ValidateSet('0', '1')]
    [string]$Chip8 = '1',

    [switch]$KeepBuild
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

if ($Markdown -eq '1') {
    $Wbmp = '0'
}

$script:ToolDir = $PSScriptRoot
$script:AppsRoot = [IO.Path]::GetFullPath((Join-Path $script:ToolDir '..'))
$script:ProjectRoot = [IO.Path]::GetFullPath(
    (Join-Path $script:AppsRoot '..'))
$script:LinkerScript = Join-Path $script:ProjectRoot `
    'tools/.mk61-app/mk61_module.ld'
$script:WorkPath = Join-Path $script:AppsRoot '.build'

function Stop-SystemAppsBuild {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s System APP: $Message"
}

function Test-RequiredFile {
    param([string]$Path, [string]$Description)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [IO.File]::Exists($Path)) {
        Stop-SystemAppsBuild "$Description not found: $Path"
    }
}

function Invoke-ArmTool {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-SystemAppsBuild (
            "$([IO.Path]::GetFileName($Path)) failed with exit code " +
            "$LASTEXITCODE")
    }
}

function Get-ArmToolOutput {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $result = @(& $Path @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        Stop-SystemAppsBuild (
            "$([IO.Path]::GetFileName($Path)) failed with exit code " +
            "$LASTEXITCODE")
    }
    return $result
}

function Get-ElfSymbol {
    param([string]$Elf, [string]$Name)
    foreach ($line in (Get-ArmToolOutput $script:Nm @(
        '-g', '--defined-only', $Elf
    ))) {
        $text = [string]$line
        if ($text -match '^\s*([0-9A-Fa-f]+)\s+\S+\s+(.+?)\s*$' -and
            $Matches[2] -eq $Name) {
            return $Matches[1]
        }
    }
    Stop-SystemAppsBuild "ELF symbol not found: $Name"
}

function Get-HexUInt32 {
    param([string]$Text)
    return [Convert]::ToUInt32($Text, 16)
}

function Write-Zx0AppContainer {
    param(
        [pscustomobject]$App,
        [string]$Resident,
        [string]$Image,
        [uint32]$MemorySize,
        [uint32]$EntryOffset,
        [uint32]$LoadAddress,
        [string]$Target
    )
    $arguments = New-Object 'System.Collections.Generic.List[string]'
    foreach ($argument in @(
        '--kind', [string]$App.PackerKind,
        '--resident', $Resident,
        '--image', $Image,
        '--memory-size', [string]$MemorySize,
        '--entry-offset', [string]$EntryOffset,
        '--load-address', ('0x{0:X8}' -f $LoadAddress),
        '--require-zx0',
        '--output', $Target
    )) {
        $arguments.Add($argument)
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$App.HandledMagic)) {
        $arguments.Add('--handled-magic')
        $arguments.Add([string]$App.HandledMagic)
    }
    Invoke-ArmTool $script:ModulePacker $arguments.ToArray()

    [byte[]]$container = [IO.File]::ReadAllBytes($Target)
    if ($container.Length -le 64 -or $container[15] -ne 1) {
        Stop-SystemAppsBuild (
            "$($App.FileName) was not packed with ZX0")
    }
}

function Find-SingleArtifact {
    param([string]$Directory, [string]$Extension, [string]$Description)
    $items = @(Get-ChildItem -LiteralPath $Directory -File |
        Where-Object { $_.Extension -ieq $Extension })
    if ($items.Count -ne 1) {
        Stop-SystemAppsBuild (
            "expected one $Description in $Directory, found $($items.Count)")
    }
    return $items[0].FullName
}

function Get-CompileEntry {
    param([object[]]$Entries, [string]$SourceName)
    foreach ($entry in $Entries) {
        if ([IO.Path]::GetFileName([string]$entry.file) -eq $SourceName) {
            $argumentsProperty = $entry.PSObject.Properties['arguments']
            $commandProperty = $entry.PSObject.Properties['command']
            $hasArguments = $null -ne $argumentsProperty -and
                $null -ne $argumentsProperty.Value -and
                $argumentsProperty.Value.Count -gt 0
            $hasCommand = $null -ne $commandProperty -and
                -not [string]::IsNullOrWhiteSpace(
                    [string]$commandProperty.Value)
            if (-not $hasArguments -and -not $hasCommand) {
                Stop-SystemAppsBuild (
                    "compile database entry for $SourceName has neither " +
                    'arguments nor command')
            }
            return $entry
        }
    }
    Stop-SystemAppsBuild (
        "compile database has no $SourceName entry")
}

function ConvertFrom-PosixCommandLine {
    param([Parameter(Mandatory = $true)][string]$Command)

    $arguments = New-Object 'System.Collections.Generic.List[string]'
    $current = New-Object Text.StringBuilder
    $state = 'plain'
    $started = $false
    for ($index = 0; $index -lt $Command.Length; $index++) {
        $character = $Command[$index]
        if ($state -eq 'single') {
            if ($character -eq "'") {
                $state = 'plain'
            } else {
                [void]$current.Append($character)
            }
            continue
        }
        if ($state -eq 'double') {
            if ($character -eq '"') {
                $state = 'plain'
            } elseif ($character -eq '\') {
                $index++
                if ($index -ge $Command.Length) {
                    Stop-SystemAppsBuild (
                        'compile command ends with an escape character')
                }
                [void]$current.Append($Command[$index])
            } else {
                [void]$current.Append($character)
            }
            continue
        }
        if ([char]::IsWhiteSpace($character)) {
            if ($started) {
                $arguments.Add($current.ToString())
                [void]$current.Clear()
                $started = $false
            }
        } elseif ($character -eq "'") {
            $state = 'single'
            $started = $true
        } elseif ($character -eq '"') {
            $state = 'double'
            $started = $true
        } elseif ($character -eq '\') {
            $index++
            if ($index -ge $Command.Length) {
                Stop-SystemAppsBuild (
                    'compile command ends with an escape character')
            }
            [void]$current.Append($Command[$index])
            $started = $true
        } else {
            [void]$current.Append($character)
            $started = $true
        }
    }
    if ($state -ne 'plain') {
        Stop-SystemAppsBuild 'compile command contains an unterminated quote'
    }
    if ($started) {
        $arguments.Add($current.ToString())
    }
    return $arguments.ToArray()
}

function ConvertFrom-WindowsCommandLine {
    param([Parameter(Mandatory = $true)][string]$Command)

    if ($null -eq ('Mk61.NativeCommandLine' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace Mk61 {
    public static class NativeCommandLine {
        [DllImport("shell32.dll", SetLastError = true)]
        public static extern IntPtr CommandLineToArgvW(
            [MarshalAs(UnmanagedType.LPWStr)] string commandLine,
            out int argumentCount);

        [DllImport("kernel32.dll")]
        public static extern IntPtr LocalFree(IntPtr memory);
    }
}
'@
    }

    $argumentCount = 0
    $memory = [Mk61.NativeCommandLine]::CommandLineToArgvW(
        $Command, [ref]$argumentCount)
    if ($memory -eq [IntPtr]::Zero) {
        Stop-SystemAppsBuild 'cannot parse the Windows compile command'
    }
    try {
        $arguments = New-Object 'System.Collections.Generic.List[string]'
        for ($index = 0; $index -lt $argumentCount; $index++) {
            $pointer = [Runtime.InteropServices.Marshal]::ReadIntPtr(
                $memory, $index * [IntPtr]::Size)
            $arguments.Add(
                [Runtime.InteropServices.Marshal]::PtrToStringUni($pointer))
        }
        return $arguments.ToArray()
    } finally {
        [void][Mk61.NativeCommandLine]::LocalFree($memory)
    }
}

function Get-CompileArguments {
    param([pscustomobject]$Entry, [string]$SourceName)

    $argumentsProperty = $Entry.PSObject.Properties['arguments']
    $commandProperty = $Entry.PSObject.Properties['command']
    if ($null -ne $argumentsProperty -and
        $null -ne $argumentsProperty.Value -and
        $argumentsProperty.Value.Count -gt 0) {
        return [string[]]@($argumentsProperty.Value |
            ForEach-Object { [string]$_ })
    }
    if ($null -eq $commandProperty -or
        [string]::IsNullOrWhiteSpace([string]$commandProperty.Value)) {
        Stop-SystemAppsBuild (
            "compile database entry for $SourceName has no command")
    }
    if ($env:OS -eq 'Windows_NT') {
        return [string[]]@(ConvertFrom-WindowsCommandLine (
            [string]$commandProperty.Value))
    }
    return [string[]]@(ConvertFrom-PosixCommandLine (
        [string]$commandProperty.Value))
}

function Test-SamePath {
    param([string]$Left, [string]$Right)
    if ($Left -eq $Right) { return $true }
    try {
        if (-not [IO.Path]::IsPathRooted($Left) -or
            -not [IO.Path]::IsPathRooted($Right)) {
            return $false
        }
        return [IO.Path]::GetFullPath($Left).Equals(
            [IO.Path]::GetFullPath($Right),
            [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Get-RelatedTool {
    param([string]$Compiler, [string]$Name)
    $directory = [IO.Path]::GetDirectoryName($Compiler)
    $extension = [IO.Path]::GetExtension($Compiler)
    $candidate = Join-Path $directory ("arm-none-eabi-$Name$extension")
    Test-RequiredFile $candidate "ARM $Name"
    return $candidate
}

function Get-SelectedApps {
    $apps = New-Object 'System.Collections.Generic.List[object]'
    if ($Focal -eq '1') {
        $apps.Add([pscustomobject]@{
            Id = 'focal'
            FileName = 'FOCAL.APP'
            PackerKind = 'focal'
            HandledMagic = ''
            Template = 'focal.cpp'
        })
    }
    if ($Basic -eq '1') {
        $apps.Add([pscustomobject]@{
            Id = 'basic'
            FileName = 'BASIC.APP'
            PackerKind = 'tinybasic'
            HandledMagic = ''
            Template = 'tinybasic.cpp'
        })
    }
    if ($Wbmp -eq '1') {
        $apps.Add([pscustomobject]@{
            Id = 'wbmp'
            FileName = 'WBMP.APP'
            PackerKind = 'wbmp-viewer'
            HandledMagic = 'I1'
            Template = 'wbmp.cpp'
        })
    }
    if ($Markdown -eq '1') {
        $apps.Add([pscustomobject]@{
            Id = 'markdown'
            FileName = 'MARKDOWN.APP'
            PackerKind = 'markdown-viewer'
            HandledMagic = 'T2'
            Template = 'markdown_document.cpp'
        })
    }
    if ($Chip8 -eq '1') {
        $apps.Add([pscustomobject]@{
            Id = 'chip8'
            FileName = 'CHIP8.APP'
            PackerKind = 'chip8'
            HandledMagic = 'C1'
            Template = 'chip8.cpp'
        })
    }
    return $apps.ToArray()
}

function Build-SystemApp {
    param([pscustomobject]$App, [object[]]$CompileEntries)

    $compileEntry = Get-CompileEntry $CompileEntries $App.Template
    [string[]]$template = Get-CompileArguments `
        $compileEntry $App.Template
    $entryCompiler = [IO.Path]::GetFullPath($template[0])
    if (-not $entryCompiler.Equals(
        $script:Compiler, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-SystemAppsBuild (
            "$($App.FileName) uses a different ARM compiler")
    }

    $mainSource = Join-Path (
        Join-Path $script:AppsRoot $App.Id) 'main.cpp'
    Test-RequiredFile $mainSource "$($App.FileName) main translation unit"
    $moduleDir = Join-Path $script:WorkPath $App.Id
    [IO.Directory]::CreateDirectory($moduleDir) | Out-Null
    $object = Join-Path $moduleDir "$($App.Id).o"
    $moduleElf = Join-Path $moduleDir "$($App.Id).elf"
    $moduleMap = Join-Path $moduleDir "$($App.Id).map"
    $moduleImage = Join-Path $moduleDir "$($App.Id).bin"

    $compileArguments = New-Object 'System.Collections.Generic.List[string]'
    for ($index = 1; $index -lt $template.Count; $index++) {
        $argument = $template[$index]
        if ($argument -eq '-o' -or $argument -eq '-MF' -or
            $argument -eq '-MT' -or $argument -eq '-MQ' -or
            $argument -eq '-MJ') {
            $index++
            continue
        }
        if ((Test-SamePath $argument ([string]$compileEntry.file)) -or
            $argument -eq '-MMD' -or $argument -eq '-MD' -or
            $argument -eq '-MP' -or $argument -eq '-MG' -or
            $argument -match '^-flto(?:=.*)?$' -or
            $argument -eq '-ffat-lto-objects' -or
            $argument -eq '-fno-fat-lto-objects') {
            continue
        }
        $compileArguments.Add($argument)
    }
    $compileArguments.Add('-flto')
    $compileArguments.Add("-I$(Join-Path $script:ProjectRoot 'code')")
    $compileArguments.Add($mainSource)
    $compileArguments.Add('-o')
    $compileArguments.Add($object)
    Invoke-ArmTool $script:Compiler $compileArguments.ToArray()

    Invoke-ArmTool $script:Compiler @(
        '-mcpu=cortex-m4',
        '-mfpu=fpv4-sp-d16',
        '-mfloat-abi=hard',
        '-mthumb',
        '-Os',
        '-flto',
        '-nostartfiles',
        '-nostdlib',
        '-Wl,--gc-sections',
        "-Wl,--just-symbols=$script:ResidentElf",
        "-Wl,--defsym=MK61_MODULE_ORIGIN=0x$script:OverlayHex",
        "-Wl,-T,$script:LinkerScript",
        "-Wl,-Map,$moduleMap",
        $object,
        '-o',
        $moduleElf
    )

    $unexpected = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in (Get-ArmToolOutput $script:Size @(
        '-A', $moduleElf
    ))) {
        if ([string]$line -match '^\s*(\.\S+)\s+([0-9]+)\s+' -and
            [uint64]$Matches[2] -ne 0 -and
            $Matches[1] -ne '.module_image' -and
            $Matches[1] -ne '.module_bss') {
            $unexpected.Add($Matches[1])
        }
    }
    if ($unexpected.Count -ne 0) {
        Stop-SystemAppsBuild (
            "$($App.FileName) has unexpected ELF sections: " +
            "$($unexpected -join ', ')")
    }

    [uint32]$imageStart = Get-HexUInt32 (
        Get-ElfSymbol $moduleElf '__module_image_start')
    [uint32]$memoryEnd = Get-HexUInt32 (
        Get-ElfSymbol $moduleElf '__module_memory_end')
    [uint32]$entryAddress = Get-HexUInt32 (
        Get-ElfSymbol $moduleElf 'mk61_module_entry')
    [uint32]$memorySize = $memoryEnd - $imageStart
    [uint32]$entryOffset = $entryAddress - $imageStart
    if ($memorySize -eq 0 -or $memorySize -gt 20KB -or
        $entryOffset -ge 20KB -or ($entryOffset -band 1) -ne 0) {
        Stop-SystemAppsBuild (
            "$($App.FileName) does not fit the 20 KiB SRAM overlay")
    }

    Invoke-ArmTool $script:Objcopy @(
        '-O', 'binary', '-j', '.module_image', $moduleElf, $moduleImage
    )
    if ($entryOffset -ge (Get-Item -LiteralPath $moduleImage).Length) {
        Stop-SystemAppsBuild (
            "$($App.FileName) entry point is outside its stored image")
    }
    $target = Join-Path $script:OutputDirectory $App.FileName
    Write-Zx0AppContainer $App `
        $script:ResidentBin $moduleImage $memorySize $entryOffset `
        (Get-HexUInt32 $script:OverlayHex) $target
    [Console]::WriteLine(
        ('MK61s APP: {0,-10} {1,5} bytes, SRAM {2,5} / 20480' -f
            $App.FileName, (Get-Item -LiteralPath $target).Length,
            $memorySize))
}

try {
    $BuildPath = [IO.Path]::GetFullPath($BuildPath)
    if (-not [IO.Directory]::Exists($BuildPath)) {
        Stop-SystemAppsBuild (
            "resident build directory not found: $BuildPath")
    }
    if ([string]::IsNullOrWhiteSpace($CompileCommands)) {
        $CompileCommands = Join-Path $BuildPath 'compile_commands.json'
    }
    if ([string]::IsNullOrWhiteSpace($ResidentElf)) {
        $ResidentElf = Find-SingleArtifact $BuildPath '.elf' 'resident ELF'
    }
    if ([string]::IsNullOrWhiteSpace($ResidentBin)) {
        $ResidentBin = Find-SingleArtifact $BuildPath '.bin' 'resident BIN'
    }
    if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
        $OutputDirectory = Join-Path $script:AppsRoot 'System'
    }
    $script:ResidentElf = [IO.Path]::GetFullPath($ResidentElf)
    $script:ResidentBin = [IO.Path]::GetFullPath($ResidentBin)
    $CompileCommands = [IO.Path]::GetFullPath($CompileCommands)
    $finalOutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

    Test-RequiredFile $script:LinkerScript 'MK61 module linker script'
    Test-RequiredFile $script:ResidentElf 'resident ELF'
    Test-RequiredFile $script:ResidentBin 'resident BIN'
    Test-RequiredFile $CompileCommands 'resident compile database'

    [object[]]$compileEntries = @(
        Get-Content -LiteralPath $CompileCommands -Raw | ConvertFrom-Json)
    [object[]]$selectedApps = @(Get-SelectedApps)

    if ($selectedApps.Count -gt 0) {
        if ([string]::IsNullOrWhiteSpace($ModulePacker)) {
            $packerBuilder = Join-Path $script:ProjectRoot `
                'tools/.mk61-app/build.ps1'
            Test-RequiredFile $packerBuilder 'MK61 APP host packer builder'
            $packerSuffix = if ($env:OS -eq 'Windows_NT') {
                '.exe'
            } else {
                ''
            }
            $ModulePacker = Join-Path $script:ProjectRoot `
                ".build/tools/mk61_module_pack$packerSuffix"
            & $packerBuilder -OutputPath $ModulePacker | Out-Host
        }
        $script:ModulePacker = [IO.Path]::GetFullPath($ModulePacker)
        Test-RequiredFile $script:ModulePacker 'MK61 APP host packer'

        $firstEntry = Get-CompileEntry $compileEntries `
            $selectedApps[0].Template
        $firstArguments = Get-CompileArguments `
            $firstEntry $selectedApps[0].Template
        $script:Compiler = [IO.Path]::GetFullPath($firstArguments[0])
        Test-RequiredFile $script:Compiler 'ARM C++ compiler'
        $script:Objcopy = Get-RelatedTool $script:Compiler 'objcopy'
        $script:Nm = Get-RelatedTool $script:Compiler 'nm'
        $script:Size = Get-RelatedTool $script:Compiler 'size'
        $script:OverlayHex = Get-ElfSymbol $script:ResidentElf `
            'mk61_module_overlay'

        if ([IO.Directory]::Exists($script:WorkPath)) {
            Remove-Item -LiteralPath $script:WorkPath -Recurse -Force
        }
        [IO.Directory]::CreateDirectory($script:WorkPath) | Out-Null
        $script:OutputDirectory = Join-Path $script:WorkPath 'System'
        [IO.Directory]::CreateDirectory(
            $script:OutputDirectory) | Out-Null
        foreach ($app in $selectedApps) {
            Build-SystemApp $app $compileEntries
        }
    }

    [IO.Directory]::CreateDirectory($finalOutputDirectory) | Out-Null
    foreach ($name in @(
        'FOCAL.APP', 'BASIC.APP', 'WBMP.APP', 'MARKDOWN.APP', 'CHIP8.APP'
    )) {
        $target = Join-Path $finalOutputDirectory $name
        if ([IO.File]::Exists($target)) {
            Remove-Item -LiteralPath $target -Force
        }
        if ($selectedApps.Count -gt 0) {
            $source = Join-Path $script:OutputDirectory $name
            if ([IO.File]::Exists($source)) {
                Copy-Item -LiteralPath $source -Destination $target
            }
        }
    }

    [Console]::WriteLine('')
    [Console]::WriteLine('MK61s System APP built:')
    [Console]::WriteLine("  $finalOutputDirectory")
    [Console]::WriteLine("  resident $($script:ResidentBin)")

    if (-not $KeepBuild -and
        [IO.Directory]::Exists($script:WorkPath)) {
        Remove-Item -LiteralPath $script:WorkPath -Recurse -Force
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
