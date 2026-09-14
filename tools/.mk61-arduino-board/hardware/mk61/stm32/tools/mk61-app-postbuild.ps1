[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('check-profile', 'build')]
    [string]$Command,
    [string]$Platform,
    [string]$Display,
    [string]$Sketch,
    [string]$Compiler,
    [string]$BuildPath,
    [string]$VariantLd,
    [string]$Project,
    [string]$Bundle,
    [string]$Focal,
    [string]$Basic,
    [string]$Wbmp,
    [string]$Markdown,
    [string]$Chip8,
    [string]$CompileFlags
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Stop-Mk61Build {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s F401 + APP: $Message"
}

function Get-Python {
    foreach ($name in @('python3', 'python')) {
        $found = Get-Command $name -CommandType Application `
            -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $found) { return $found.Source }
    }
    Stop-Mk61Build 'Python 3 is required for APP builds'
}

function Test-Mk61Profile {
    param([string]$PlatformId, [string]$DisplayId)
    return "${PlatformId}:${DisplayId}" -in @(
        'mini-v2:lcd1602-a00', 'mini-v2:lcd1602-a02',
        'mini-v3:lcd1602-a00', 'mini-v3:lcd1602-a02',
        'mini-v3:oled1602-ws0010', 'classic-v2:uc1609',
        'classic-v3:uc1609', '40th:uc1609')
}

function Test-RequiredFile {
    param([string]$Path, [string]$Description)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [IO.File]::Exists($Path)) {
        Stop-Mk61Build "$Description not found: $Path"
    }
}

function Invoke-Mk61Tool {
    param([Parameter(Mandatory = $true)][string]$Path,
          [Parameter(Mandatory = $true)][string[]]$Arguments)
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Mk61Build (
            "$([IO.Path]::GetFileName($Path)) failed with exit code " +
            "$LASTEXITCODE")
    }
}

function Check-Mk61Profile {
    if (-not (Test-Mk61Profile $Platform $Display)) {
        Stop-Mk61Build "incompatible platform/display pair: $Platform + $Display"
    }
    if ([string]::IsNullOrWhiteSpace($Sketch) -or
        -not [IO.File]::Exists((Join-Path $Sketch 'mk61s-M.ino')) -or
        -not [IO.File]::Exists((Join-Path $Sketch 'config.h'))) {
        Stop-Mk61Build 'open code/mk61s-M.ino before selecting this board'
    }
    if (-not [string]::IsNullOrWhiteSpace($VariantLd)) {
        [IO.Directory]::CreateDirectory($BuildPath) | Out-Null
        Invoke-Mk61Tool (Get-Python) @(
            (Join-Path $Sketch '../tools/.mk61-gcc/portable-layout.py'),
            $VariantLd, (Join-Path $BuildPath 'mk61-portable.ld'))
    }
}

function Build-Mk61Bundle {
    Test-RequiredFile $Compiler 'ARM compiler'
    if ([string]::IsNullOrWhiteSpace($BuildPath) -or
        -not [IO.Directory]::Exists($BuildPath)) {
        Stop-Mk61Build 'Arduino build path was not found'
    }
    if ([string]::IsNullOrWhiteSpace($Project) -or
        [string]::IsNullOrWhiteSpace($Bundle)) {
        Stop-Mk61Build 'Arduino project or bundle name is missing'
    }
    if ($Focal -notmatch '^[01]$' -or $Basic -notmatch '^[01]$' -or
        $Wbmp -notmatch '^[01]$' -or $Markdown -notmatch '^[01]$' -or
        $Chip8 -notmatch '^[01]$') {
        Stop-Mk61Build 'System APP selections must be 0 or 1'
    }
    if ($Markdown -eq '1') { $Wbmp = '0' }

    $build = [IO.Path]::GetFullPath($BuildPath)
    $residentElf = Join-Path $build "$Project.elf"
    $residentBin = Join-Path $build "$Project.bin"
    Test-RequiredFile $residentElf 'resident ELF'
    Test-RequiredFile $residentBin 'resident BIN'

    $sealer = Join-Path $PSScriptRoot 'seal-firmware.ps1'
    Test-RequiredFile $sealer 'resident firmware sealer; reinstall the MK61s board'
    $powerShell = if ($PSVersionTable.PSEdition -eq 'Desktop') {
        Join-Path $PSHOME 'powershell.exe'
    } else { (Get-Process -Id $PID).Path }
    Invoke-Mk61Tool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'seal',
        '-InputFile', $residentBin, '-MaxSize', '262144')
    Invoke-Mk61Tool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'check',
        '-InputFile', $residentBin, '-MaxSize', '262144')

    $stageRoot = Join-Path $build 'mk61-system-apps'
    $script:Stage = [IO.Path]::GetFullPath((Join-Path $stageRoot $Bundle))
    $safePrefix = $build.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $script:Stage.StartsWith(
        $safePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Mk61Build 'unsafe staging path'
    }
    if ([IO.Directory]::Exists($script:Stage)) {
        Remove-Item -LiteralPath $script:Stage -Recurse -Force
    }
    [IO.Directory]::CreateDirectory((Join-Path $script:Stage 'System')) | Out-Null
    Copy-Item -LiteralPath $residentBin `
        -Destination (Join-Path $script:Stage "$Bundle.bin")

    $graphics = if ($CompileFlags -match
        'MK61_BOARD_CLASSIC|MK61_BOARD_40TH|DISPLAY_UC1609|MK61_ENABLE_USB_SCREEN=1|MK61_WS0010_GRAPHICS_100X16=1') { '1' } else { '0' }
    Invoke-Mk61Tool (Get-Python) @(
        (Join-Path $Sketch '../tools/build_system_app_bundle.py'),
        '--resident-elf', $residentElf,
        '--arm-toolchain-bin', [IO.Path]::GetDirectoryName($Compiler),
        '--output-dir', (Join-Path $script:Stage 'System'),
        '--graphics', $graphics, '--ui-fonts', '0',
        '--focal', $Focal, '--basic', $Basic, '--wbmp', $Wbmp,
        '--markdown', $Markdown, '--chip8', $Chip8)

    $output = Join-Path ([IO.Path]::GetFullPath((Join-Path $Sketch '..\binary'))) $Bundle
    $outputSystem = Join-Path $output 'System'
    [IO.Directory]::CreateDirectory($outputSystem) | Out-Null
    Copy-Item -LiteralPath (Join-Path $script:Stage "$Bundle.bin") `
        -Destination (Join-Path $output "$Bundle.bin") -Force
    foreach ($canonical in @('FOCAL.APP', 'BASIC.APP', 'WBMP.APP',
            'MARKDOWN.APP', 'CHIP8.APP', 'SETUP.APP', 'HELP0.TXT', 'HELP1.TXT')) {
        $source = Join-Path (Join-Path $script:Stage 'System') $canonical
        $target = Join-Path $outputSystem $canonical
        if ([IO.File]::Exists($source)) {
            Copy-Item -LiteralPath $source -Destination $target -Force
        } elseif ([IO.File]::Exists($target)) {
            Remove-Item -LiteralPath $target -Force
        }
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $output 'build.flags'),
        $CompileFlags + [Environment]::NewLine, $utf8)
    [IO.File]::WriteAllText((Join-Path $output 'build.apps'),
        'format 1' + [Environment]::NewLine +
            'abi 5' + [Environment]::NewLine, $utf8)
    Write-Host ''
    Write-Host 'MK61s F401 unified ABI 5 bundle built by Arduino IDE:'
    Write-Host "  $output"
    Write-Host 'After Upload, copy the generated System directory to /System on MK61S C5.'
    Write-Host ''
}

try {
    switch ($Command) {
        'check-profile' { Check-Mk61Profile }
        'build' { Build-Mk61Bundle }
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
