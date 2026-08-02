#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$Compiler,
    [switch]$Check
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:ToolRoot = $PSScriptRoot
$script:ProjectRoot = [IO.Path]::GetFullPath(
    (Join-Path $script:ToolRoot '../..'))

function Stop-ModulePackerBuild {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61 APP host packer: $Message"
}

function Resolve-HostCompiler {
    param([string]$Requested)

    $names = New-Object 'System.Collections.Generic.List[string]'
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        $names.Add($Requested)
    } elseif (-not [string]::IsNullOrWhiteSpace($env:MK61_HOST_CXX)) {
        $names.Add($env:MK61_HOST_CXX)
    } else {
        foreach ($name in @('c++', 'clang++', 'g++', 'cl', 'clang-cl')) {
            $names.Add($name)
        }
    }

    foreach ($name in $names) {
        if ([IO.Path]::IsPathRooted($name)) {
            if ([IO.File]::Exists($name)) {
                return [IO.Path]::GetFullPath($name)
            }
            continue
        }
        $command = Get-Command $name -CommandType Application `
            -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) {
            return $command.Source
        }
    }
    Stop-ModulePackerBuild (
        'C++17 compiler not found; install c++, clang++, g++, or MSVC, ' +
        'or set MK61_HOST_CXX')
}

$script:Compiler = Resolve-HostCompiler $Compiler
$compilerName = [IO.Path]::GetFileName(
    $script:Compiler).ToLowerInvariant()
$msvcStyle = $compilerName -eq 'cl' -or $compilerName -eq 'cl.exe' -or
    $compilerName -eq 'clang-cl' -or $compilerName -eq 'clang-cl.exe'

if ($Check) {
    [Console]::WriteLine(
        "MK61 APP host packer compiler: $($script:Compiler)")
    return
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    $OutputPath = Join-Path $script:ProjectRoot `
        ".build/tools/mk61_module_pack$suffix"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

$sources = @(
    (Join-Path $script:ToolRoot 'mk61_module_pack.cpp'),
    (Join-Path $script:ProjectRoot 'code/loadable_module_format.cpp'),
    (Join-Path $script:ProjectRoot 'code/loadable_module_format.hpp'),
    (Join-Path $script:ProjectRoot 'code/zx0.cpp'),
    (Join-Path $script:ProjectRoot 'code/zx0.hpp'),
    (Join-Path $script:ProjectRoot 'code/storage_geometry.hpp'),
    (Join-Path $script:ToolRoot 'third_party/zx0/zx0.h'),
    (Join-Path $script:ToolRoot 'third_party/zx0/optimize.c'),
    (Join-Path $script:ToolRoot 'third_party/zx0/compress.c'),
    (Join-Path $script:ToolRoot 'third_party/zx0/memory.c')
)
foreach ($source in $sources) {
    if (-not [IO.File]::Exists($source)) {
        Stop-ModulePackerBuild "source not found: $source"
    }
}

$rebuild = -not [IO.File]::Exists($OutputPath)
if (-not $rebuild) {
    $outputTime = (Get-Item -LiteralPath $OutputPath).LastWriteTimeUtc
    foreach ($source in $sources) {
        if ((Get-Item -LiteralPath $source).LastWriteTimeUtc -gt $outputTime) {
            $rebuild = $true
            break
        }
    }
}

if ($rebuild) {
    $outputDirectory = [IO.Path]::GetDirectoryName($OutputPath)
    [IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
    $objectDirectory = Join-Path $outputDirectory 'mk61_module_pack-obj'
    [IO.Directory]::CreateDirectory($objectDirectory) | Out-Null
    $temporarySuffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    $temporary = Join-Path $outputDirectory (
        'mk61_module_pack.tmp-' + [string]$PID + $temporarySuffix)

    $compileSources = @(
        (Join-Path $script:ToolRoot 'mk61_module_pack.cpp'),
        (Join-Path $script:ProjectRoot 'code/loadable_module_format.cpp'),
        (Join-Path $script:ProjectRoot 'code/zx0.cpp'),
        (Join-Path $script:ToolRoot 'third_party/zx0/optimize.c'),
        (Join-Path $script:ToolRoot 'third_party/zx0/compress.c'),
        (Join-Path $script:ToolRoot 'third_party/zx0/memory.c')
    )
    try {
        Push-Location $objectDirectory
        try {
            if ($msvcStyle) {
                $arguments = @(
                    '/nologo', '/std:c++17', '/O2', '/W3', '/EHsc', '/TP',
                    "/I$(Join-Path $script:ProjectRoot 'code')"
                ) + $compileSources + @("/Fe$temporary")
            } else {
                $arguments = @(
                    '-x', 'c++', '-std=c++17', '-O2',
                    '-Wall', '-Wextra', '-Werror',
                    "-I$(Join-Path $script:ProjectRoot 'code')"
                ) + $compileSources + @('-o', $temporary)
            }
            & $script:Compiler @arguments
            if ($LASTEXITCODE -ne 0) {
                Stop-ModulePackerBuild (
                    "$compilerName failed with exit code $LASTEXITCODE")
            }
        } finally {
            Pop-Location
        }
        if (-not [IO.File]::Exists($temporary) -or
            (Get-Item -LiteralPath $temporary).Length -eq 0) {
            Stop-ModulePackerBuild 'compiler did not produce the executable'
        }
        Move-Item -LiteralPath $temporary -Destination $OutputPath -Force
    } finally {
        if ([IO.File]::Exists($temporary)) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

[Console]::WriteLine($OutputPath)
