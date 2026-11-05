# Keep native GCC options in $args, including -o and drive-letter paths.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try {
    if ($args.Count -lt 4) { throw 'expected BUILD SKETCH CXX FLAGS...' }
    $build = [IO.Path]::GetFullPath([string]$args[0])
    $sketch = [IO.Path]::GetFullPath([string]$args[1])
    $cpp = [string]$args[2]
    $flags = @()
    for ($i = 3; $i -lt $args.Count; ++$i) {
        $flag = [string]$args[$i]
        if ($flag -cmatch '^-(?:[IL]|Wl,.*[,=])[A-Za-z]$' -and
            $i + 1 -lt $args.Count -and [string]$args[$i + 1] -match '^[\\/]') {
            $flag += ':' + [string]$args[++$i]
        }
        $flags += $flag
    }
    $policy = ConvertFrom-Json ([IO.File]::ReadAllText(
        (Join-Path $PSScriptRoot 'native_compile_policy.json')))
    if ($policy.schema -ne 1 -or $flags -notcontains '-DMK61_NATIVE_RUNTIME=1') {
        throw 'native Arduino compiler policy/flags mismatch'
    }
    $cc = Join-Path ([IO.Path]::GetDirectoryName($cpp)) (
        [IO.Path]::GetFileName($cpp).Replace('g++', 'gcc'))
    $cxxOnly = @('-std=gnu++17', '-fno-rtti', '-fno-exceptions',
        '-fno-use-cxa-atexit', '-fno-threadsafe-statics')
    $sketchBuild = Join-Path $build 'sketch'
    $objectsExist = @(Get-ChildItem -LiteralPath $sketchBuild -Recurse -File `
        -Filter '*.o' -ErrorAction SilentlyContinue).Count -gt 0
    $replacements = @{}
    $powerShell = (Get-Process -Id $PID).Path
    foreach ($unit in $policy.units) {
        $mcu = $unit.PSObject.Properties['mcu']
        if ($null -ne $mcu -and $mcu.Value -eq 'f411' -and
            $flags -notcontains '-DSTM32F411xE') { continue }
        $name = [string]$unit.source
        $source = Join-Path $sketchBuild $name
        if (-not [IO.File]::Exists($source)) { $source = Join-Path $sketch $name }
        $objects = @(Get-ChildItem -LiteralPath $sketchBuild -Recurse -File `
            -Filter "$name.o" -ErrorAction SilentlyContinue)
        if ($objects.Count -ne 1) {
            if (-not $objectsExist) { continue }
            throw "expected one native object for $name, found $($objects.Count)"
        }
        $compiler = $cpp
        $unitFlags = @($flags)
        if ($name.EndsWith('.c')) {
            $compiler = $cc
            $unitFlags = @($flags | Where-Object { $cxxOnly -notcontains $_ }) + @('-std=gnu17')
        }
        $unitFlags += @($unit.flags)
        foreach ($definition in $unit.defines) { $unitFlags += "-D$definition" }
        $unitFlags += @('-I', [IO.Path]::GetDirectoryName($source),
            $source, '-o', $objects[0].FullName)
        & $powerShell -NoLogo -NoProfile -File (Join-Path $PSScriptRoot 'mk61-safe-tool.ps1') `
            (Join-Path $build 'mk61-tool-temp') $compiler @unitFlags
        if ($LASTEXITCODE -ne 0) { throw "compiler failed for $name ($LASTEXITCODE)" }
        $replacements[$name] = @($compiler) + $unitFlags
        Write-Host "Native Arduino policy: $name"
    }
    $database = Join-Path $build 'compile_commands.json'
    if ([IO.File]::Exists($database)) {
        $entries = ConvertFrom-Json ([IO.File]::ReadAllText($database))
        foreach ($entry in $entries) {
            $name = [IO.Path]::GetFileName([string]$entry.file)
            if ($replacements.ContainsKey($name)) {
                $actual = $replacements[$name]
                $entry.PSObject.Properties.Remove('command')
                $entry | Add-Member -MemberType NoteProperty -Name arguments -Value $actual -Force
                $entry.file = $actual[$actual.Count - 3]
            }
        }
        [IO.File]::WriteAllText($database, (ConvertTo-Json -InputObject @($entries) -Depth 12),
            (New-Object Text.UTF8Encoding($false)))
    }
} catch {
    [Console]::Error.WriteLine("MK61s native Arduino prelink: $($_.Exception.Message)")
    exit 1
}
