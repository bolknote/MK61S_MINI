#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BuildRoot,
    [string]$ConfigFile,
    [string]$Sketch
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
# Windows PowerShell 5.1 leaves PSScriptRoot empty during default-parameter
# binding. Resolve the optional sketch only after entering the script body.
if ([string]::IsNullOrWhiteSpace($Sketch)) { $Sketch = Join-Path $root 'code' }
$cliOptions = @()
if ($ConfigFile) { $cliOptions = @('--config-file', $ConfigFile) }
foreach ($revision in @('v2', 'v3')) {
    $build = Join-Path $BuildRoot "arduino-ide-f401-classic-$revision"
    # V2 reproduces the reporter's saved menu choice through the real recipe;
    # V3 also covers the current CORE choice. Both must produce a full bundle.
    $math = if ($revision -eq 'v2') { 'core_app_float' } else { 'core' }
    $fqbn = "mk61:stm32:mk61_f401_app:mk61_platform=classic_$revision,mk61_display=uc1609,mk61_focal=app,mk61_basic=app,mk61_documents=markdown,mk61_chip8=app,mk61_setup=app,mk61_explorer_module=app,mk61_usb_screen=disabled,mk61_explorer=enabled,mk61_math=$math"
    & arduino-cli @cliOptions compile --fqbn $fqbn --build-path $build $Sketch
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $bundleName = "mk61s-M-classic-$revision-uc1609-f401"
    $project = Split-Path -Parent ([IO.Path]::GetFullPath($Sketch))
    $bundle = Join-Path $project ".build/firmware/$bundleName"
    $image = Join-Path $bundle "$bundleName.bin"
    $size = (Get-Item -LiteralPath $image).Length
    $free = 262144 - $size
    # Same 2-KiB floor as the existing Arduino Classic comparison. Native
    # published products keep their separate 4-KiB release floor.
    if ($size -le 0 -or $free -lt 2048) {
        throw "Classic $revision sealed Flash reserve: $free < 2048 bytes"
    }
    & (Get-Process -Id $PID).Path -NoLogo -NoProfile -File `
        (Join-Path $root 'tools/seal-firmware.ps1') check -InputFile $image -MaxSize 262144
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $flags = [IO.File]::ReadAllText((Join-Path $bundle 'build.flags'))
    foreach ($flag in @('-DMK61_REQUIRE_RESIDENT_CRC=1', '-DMK61_NATIVE_RUNTIME=1', '-DMK61_USE_NATIVE_LIBC=1', '-DMK61_USE_NATIVE_EABI=1', '-DMK61_USE_COMPACT_LIBM=1',
        '-DMK61_MATH_BACKEND=1', '-DMK61_APP_LOCAL_FLOAT_MATH=0',
        '-DMK61_FOCAL_AS_APP=1', '-DMK61_TINYBASIC_AS_APP=1',
        '-DMK61_CHIP8_AS_APP=1', '-DMK61_MARKDOWN_VIEWER_AS_APP=1')) {
        if (-not $flags.Contains($flag)) { throw "Classic $revision missing $flag" }
    }
    if ($flags.Contains('-DMK61_APP_LOCAL_FLOAT_MATH=1')) {
        throw "Classic $revision retained retired local APP math"
    }
    foreach ($file in @('BASIC.APP', 'FOCAL.APP', 'CHIP8.APP', 'MARKDOWN.APP',
        'LANGVM.APP', 'LANGIN.APP', 'SETUP.APP', 'EXPLORER.APP', 'USBDISK.APP',
        'HELP0.TXT', 'HELP1.TXT')) {
        if (-not (Test-Path -LiteralPath (Join-Path $bundle "System/$file") -PathType Leaf)) {
            throw "Classic $revision missing System/$file"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $bundle 'System/WBMP.APP')) {
        throw "Classic $revision contains disabled WBMP.APP"
    }
    Write-Host "Classic $revision Arduino IDE: sealed Flash $size/262144, $free bytes free; full System bundle PASS"
}
