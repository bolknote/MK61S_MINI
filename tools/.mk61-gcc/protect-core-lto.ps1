# Parameter-free: native compiler flags must not bind as PowerShell options.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try {
    if ($args.Count -lt 3) { throw 'Expected BUILD SKETCH CXX [FLAGS...]' }
    $build = [IO.Path]::GetFullPath([string]$args[0])
    $sketch = [IO.Path]::GetFullPath([string]$args[1])
    $compiler = [string]$args[2]
    if (-not [IO.File]::Exists($compiler) -and [IO.File]::Exists("$compiler.exe")) {
        $compiler += '.exe'
    }
    $flags = @()
    $lto = $false
    for ($index = 3; $index -lt $args.Count; ++$index) {
        $argument = [string]$args[$index]
        if ($argument -cmatch '^-I[A-Za-z]$' -and $index + 1 -lt $args.Count -and
            [string]$args[$index + 1] -match '^[\\/]') {
            $argument += ':' + [string]$args[++$index]
        }
        if ($argument -eq '-flto' -or $argument.StartsWith('-flto=')) { $lto = $true }
        elseif ($argument -eq '-fno-lto') { $lto = $false }
        $flags += $argument
    }
    if (-not $lto -or '-DSTM32F411xE' -cnotin $flags) { exit 0 }
    $source = Join-Path $sketch 'mk61emu_core.cpp'
    $objects = @([IO.Directory]::GetFiles((Join-Path $build 'sketch'),
        'mk61emu_core.cpp.o', [IO.SearchOption]::AllDirectories))
    if (-not [IO.File]::Exists($source) -or $objects.Count -ne 1) {
        throw "Expected F411 core source and one object, found $($objects.Count)"
    }
    $safeTemp = Join-Path $build 'mk61-core-lto'
    [IO.Directory]::CreateDirectory($safeTemp) | Out-Null
    $env:TEMP = $safeTemp
    $env:TMP = $safeTemp
    $env:TMPDIR = $safeTemp
    $command = @($flags) + @('-fno-lto', ('-I' + $sketch), $source, '-o', $objects[0])
    $lines = foreach ($argument in $command) {
        '"' + ([string]$argument).Replace('\', '/').Replace('"', '\"') + '"'
    }
    $response = Join-Path $safeTemp 'mk61emu_core.rsp'
    [IO.File]::WriteAllLines($response, [string[]]$lines, [Text.Encoding]::Default)
    & $compiler ('@' + $response.Replace('\', '/'))
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host 'Core LTO barrier: mk61emu_core.cpp (F411)'
} catch {
    [Console]::Error.WriteLine("Core LTO barrier: $($_.Exception.Message)")
    exit 1
}
