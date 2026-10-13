# Parameter-free: compiler flags such as -o must not be PowerShell options.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try {
    if ($args.Count -lt 3) {
        throw 'Expected BUILD USB_LIBRARY COMPILER [FLAGS...]'
    }
    $buildPath = [IO.Path]::GetFullPath([string]$args[0])
    $library = [IO.Path]::GetFullPath([string]$args[1])
    $compiler = [string]$args[2]
    if (-not [IO.File]::Exists($compiler) -and [IO.File]::Exists("$compiler.exe")) {
        $compiler += '.exe'
    }
    $flags = @()
    for ($index = 3; $index -lt $args.Count; ++$index) {
        $argument = [string]$args[$index]
        # Even a parameter-free -File script receives -IC:/path as two
        # arguments, -IC and /path: PowerShell consumes the drive colon as
        # its parameter/value separator. Restore it before writing GCC's
        # response file. Separate -I C:/path and POSIX paths need no repair.
        if ($argument -cmatch '^-I[A-Za-z]$' -and
            $index + 1 -lt $args.Count -and
            [string]$args[$index + 1] -match '^[\\/]') {
            $argument += ':' + [string]$args[++$index]
        }
        $flags += $argument
    }
    $objectDirectory = Join-Path $buildPath 'libraries/USBDevice'
    $safeTemp = Join-Path $buildPath 'mk61-usb-lto'
    [IO.Directory]::CreateDirectory($safeTemp) | Out-Null
    $env:TEMP = $safeTemp
    $env:TMP = $safeTemp
    $env:TMPDIR = $safeTemp
    # Keep wrapped middleware definitions outside LTO; replace the F4 bridge below.
    foreach ($source in @('src/cdc/usbd_cdc.c', 'src/usb_device_core.c')) {
        $leaf = [IO.Path]::GetFileName($source)
        $objects = @([IO.Directory]::GetFiles($objectDirectory,
            "$leaf.o", [IO.SearchOption]::AllDirectories))
        if ($objects.Count -ne 1) {
            throw "Expected one $source object, found $($objects.Count)"
        }
        $command = @($flags) + @('-fno-lto', (Join-Path $library $source), '-o', $objects[0])
        $response = Join-Path $safeTemp "$leaf.rsp"
        $lines = foreach ($argument in $command) {
            '"' + ([string]$argument).Replace('\', '/').Replace('"', '\"') + '"'
        }
        [IO.File]::WriteAllLines($response, [string[]]$lines, [Text.Encoding]::Default)
        & $compiler ('@' + $response.Replace('\', '/'))
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "USB LTO barrier: $source"
    }
    if (@($flags | Where-Object { $_ -in @('-DSTM32F401xC','-DSTM32F401xE','-DSTM32F411xE') }).Count -gt 0) {
        $sketch = Join-Path $buildPath 'sketch'
        foreach ($item in @(
            @{ source='stm32f4_usb_device.cpp'; object='usbd_conf.c.o'; define='MK61_USB_BUILD_BRIDGE=1'; cxx=$true },
            @{ source='stm32f4_usbd_ctlreq.c'; object='usb_device_ctlreq.c.o'; define='MK61_USB_BUILD_CTLREQ=1'; cxx=$false })) {
            $source = Join-Path $sketch $item.source
            $objects = @([IO.Directory]::GetFiles($objectDirectory,$item.object,[IO.SearchOption]::AllDirectories))
            if ($objects.Count -ne 1 -or -not [IO.File]::Exists($source)) { throw "Missing owned USB object/source $($item.source)" }
            $command = @($flags)
            if ($item.cxx) { $command += @('-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics') }
            $command += @(('-D' + $item.define),$source,'-o',$objects[0])
            $response = Join-Path $safeTemp ($item.source + '.rsp')
            $lines = foreach ($argument in $command) {
                '"' + ([string]$argument).Replace('\','/').Replace('"','\"') + '"'
            }
            [IO.File]::WriteAllLines($response,[string[]]$lines,[Text.Encoding]::Default)
            & $compiler ('@' + $response.Replace('\','/'))
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            Write-Host "Owned F4 USB source: $($item.source)"
        }
    }
} catch {
    [Console]::Error.WriteLine("USB LTO barrier: $($_.Exception.Message)")
    exit 1
}
