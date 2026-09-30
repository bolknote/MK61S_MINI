[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('check-profile', 'build')]
    [string]$Command,
    [string]$Platform,
    [string]$Display,
    [string]$UsbScreen = '0',
    [string]$Sketch,
    [string]$Compiler,
    [string]$BuildPath,
    [string]$VariantLd,
    [string]$Project,
    [string]$Bundle,
    [ValidateSet('f401', 'f411')]
    [string]$Mcu,
    [string]$MaxSize,
    [string]$Focal,
    [string]$Basic,
    [string]$Wbmp,
    [string]$Markdown,
    [string]$Chip8 = '0',
    [string]$Setup,
    [string]$UsbDisk,
    [string]$Explorer,
    [string]$LocalFloatMath,
    [string]$CompileFlags
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Stop-Mk61Build {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s Arduino board: $Message"
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

function Resolve-Mk61Executable {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }

    # Arduino's STM32 platform describes compiler.cpp.cmd without the Windows
    # .exe suffix.  The command recipes resolve it through PATHEXT, whereas a
    # direct File.Exists check does not.  Accept the exact path first, then
    # the executable form used by the Windows toolchain package.
    foreach ($candidate in @($Path, "$Path.exe")) {
        if ([IO.File]::Exists($candidate)) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }
    $found = Get-Command $Path -CommandType Application `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $found) { return $found.Source }
    return $null
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

function Get-Mk61PowerShell {
    if ($PSVersionTable.PSEdition -eq 'Desktop') {
        $candidate = Join-Path $PSHOME 'powershell.exe'
    } else {
        $candidate = (Get-Process -Id $PID).Path
    }
    Test-RequiredFile $candidate 'PowerShell'
    return $candidate
}

function Remove-Mk61BundledUiFontLicenses {
    param([Parameter(Mandatory = $true)][string]$Output)
    $uiFontLicenses = Join-Path $Output 'licenses/ui-fonts'
    if ([IO.Directory]::Exists($uiFontLicenses)) {
        Remove-Item -LiteralPath $uiFontLicenses -Recurse -Force
    }
    # Leave the parent directory in place.  Removing an empty `licenses`
    # directory is unnecessary (the packager can reuse it) and can fail on
    # Windows when a sync client creates a file between the emptiness check
    # and Remove-Item.
}

function Check-Mk61Profile {
    if (-not (Test-Mk61Profile $Platform $Display)) {
        Stop-Mk61Build "incompatible platform/display pair: $Platform + $Display"
    }
    if ($UsbScreen -notmatch '^[01]$' -or $Chip8 -notmatch '^[01]$') {
        Stop-Mk61Build 'USB Screen and CHIP-8 selections must be 0 or 1'
    }
    if ($Chip8 -eq '1' -and $Display -ne 'uc1609' -and
        $UsbScreen -ne '1') {
        Stop-Mk61Build (
            'CHIP-8 выбран без графического экрана; для A00/A02 ' +
            'выберите «CHIP-8: Выключен» либо «USB-экран: Включён»')
    }
    if ([string]::IsNullOrWhiteSpace($Sketch) -or
        -not [IO.File]::Exists((Join-Path $Sketch 'mk61s-M.ino')) -or
        -not [IO.File]::Exists((Join-Path $Sketch 'config.h'))) {
        Stop-Mk61Build 'open code/mk61s-M.ino before selecting this board'
    }
    if (-not [string]::IsNullOrWhiteSpace($VariantLd)) {
        [IO.Directory]::CreateDirectory($BuildPath) | Out-Null
        Invoke-Mk61Tool (Get-Mk61PowerShell) @(
            '-NoLogo', '-NoProfile', '-File',
            (Join-Path $Sketch '../tools/.mk61-gcc/portable-layout.ps1'),
            $VariantLd, (Join-Path $BuildPath 'mk61-portable.ld'))
    }
}

function Build-Mk61Bundle {
    $requestedCompiler = $Compiler
    $Compiler = Resolve-Mk61Executable $requestedCompiler
    if ([string]::IsNullOrWhiteSpace($Compiler)) {
        Stop-Mk61Build "ARM compiler not found: $requestedCompiler"
    }
    if ([string]::IsNullOrWhiteSpace($BuildPath) -or
        -not [IO.Directory]::Exists($BuildPath)) {
        Stop-Mk61Build 'Arduino build path was not found'
    }

    # GCC also creates private assembler files while the portable APPs are
    # built after the resident image.  On Windows those files still follow
    # TEMP/TMP, independently of Arduino's --build-path and the resident-link
    # wrapper.  Keep every child process below Arduino's ASCII-only build
    # directory so a Cyrillic Windows user profile cannot break APP packing.
    $safeToolTemp = [IO.Path]::GetFullPath(
        (Join-Path $BuildPath 'mk61-tool-temp'))
    [IO.Directory]::CreateDirectory($safeToolTemp) | Out-Null
    $env:TEMP = $safeToolTemp
    $env:TMP = $safeToolTemp
    $env:TMPDIR = $safeToolTemp

    if ([string]::IsNullOrWhiteSpace($Project) -or
        [string]::IsNullOrWhiteSpace($Bundle)) {
        Stop-Mk61Build 'Arduino project or bundle name is missing'
    }
    $expectedSize = if ($Mcu -eq 'f401') { '262144' } else { '524288' }
    if ($MaxSize -cne $expectedSize) {
        Stop-Mk61Build "invalid MCU/Flash pair: $Mcu / $MaxSize"
    }
    if (-not $Bundle.EndsWith("-$Mcu", [StringComparison]::Ordinal)) {
        Stop-Mk61Build "bundle $Bundle does not match MCU $Mcu"
    }
    if ($Focal -notmatch '^[01]$' -or $Basic -notmatch '^[01]$' -or
        $Wbmp -notmatch '^[01]$' -or $Markdown -notmatch '^[01]$' -or
        $Chip8 -notmatch '^[01]$' -or $Setup -notmatch '^[01]$' -or
        $UsbDisk -notmatch '^[01]$' -or
        $Explorer -notmatch '^[01]$' -or $LocalFloatMath -notmatch '^[01]$') {
        Stop-Mk61Build 'System APP selections must be 0 or 1'
    }
    if ($Mcu -eq 'f401' -and $UsbDisk -ne '1') {
        Stop-Mk61Build 'F401 requires USBDISK.APP'
    }
    if ($Markdown -eq '1') { $Wbmp = '0' }
    if ($LocalFloatMath -eq '1' -and
        $CompileFlags -notmatch 'MK61_MATH_BACKEND=1') {
        Stop-Mk61Build 'local APP float math requires resident CORE math'
    }

    $build = [IO.Path]::GetFullPath($BuildPath)
    $residentElf = Join-Path $build "$Project.elf"
    $residentBin = Join-Path $build "$Project.bin"
    Test-RequiredFile $residentElf 'resident ELF'
    Test-RequiredFile $residentBin 'resident BIN'

    $sealer = Join-Path $PSScriptRoot 'seal-firmware.ps1'
    Test-RequiredFile $sealer 'resident firmware sealer; reinstall the MK61s board'
    $powerShell = Get-Mk61PowerShell
    Invoke-Mk61Tool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'seal',
        '-InputFile', $residentBin, '-MaxSize', $MaxSize)
    Invoke-Mk61Tool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'check',
        '-InputFile', $residentBin, '-MaxSize', $MaxSize)
    $objcopyName = if ([IO.Path]::GetExtension($Compiler) -ieq '.exe') {
        'arm-none-eabi-objcopy.exe'
    } else { 'arm-none-eabi-objcopy' }
    $objcopy = Resolve-Mk61Executable (
        Join-Path ([IO.Path]::GetDirectoryName($Compiler)) $objcopyName)
    if ([string]::IsNullOrWhiteSpace($objcopy)) {
        Stop-Mk61Build "ARM objcopy not found beside compiler: $Compiler"
    }
    Invoke-Mk61Tool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'seal-elf',
        '-InputFile', $residentBin, '-ElfFile', $residentElf,
        '-Objcopy', $objcopy)

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
    Copy-Item -LiteralPath $residentElf `
        -Destination (Join-Path $script:Stage "$Bundle.elf")

    # Arduino's Upload recipe does not reliably retain build.source.path on
    # Windows.  Keep the exact terminal installer used by this build beside
    # its System bundle, so the upload phase never has to rediscover the
    # repository from Arduino IDE's current working directory.
    $mkcSource = [IO.Path]::GetFullPath(
        (Join-Path $Sketch '../tools/.mkc/mkc.ps1'))
    Test-RequiredFile $mkcSource 'MKC terminal installer'
    $mkcStaged = Join-Path $script:Stage 'mk61-system-installer.ps1'
    Copy-Item -LiteralPath $mkcSource -Destination $mkcStaged -Force
    Test-RequiredFile $mkcStaged 'staged MKC terminal installer'

    $graphics = if ($CompileFlags -match
        'MK61_BOARD_CLASSIC|MK61_BOARD_40TH|DISPLAY_UC1609|MK61_ENABLE_USB_SCREEN=1|MK61_WS0010_GRAPHICS_100X16=1') { '1' } else { '0' }
    $uiFonts = if ($CompileFlags -match
        'MK61_BOARD_CLASSIC|MK61_BOARD_40TH|DISPLAY_UC1609') { '1' } else { '0' }
    $outputRoot = [IO.Path]::GetFullPath((Join-Path $Sketch '..\binary'))
    Invoke-Mk61Tool $powerShell @(
        '-NoLogo', '-NoProfile', '-File',
        (Join-Path $Sketch '../tools/build-system-app-bundle.ps1'),
        '-ResidentElf', $residentElf,
        '-ArmToolchainBin', [IO.Path]::GetDirectoryName($Compiler),
        '-OutputDirectory', (Join-Path $script:Stage 'System'),
        '-Graphics', $graphics, '-UiFonts', $uiFonts,
        '-Focal', $Focal, '-Basic', $Basic, '-Wbmp', $Wbmp,
        '-Markdown', $Markdown, '-Chip8', $Chip8,
        '-Setup', $Setup, '-UsbDisk', $UsbDisk, '-Explorer', $Explorer,
        '-LocalFloatMath', $LocalFloatMath,
        '-CatalogDirectory', (Join-Path $outputRoot 'apps\abi6'))
    $stagedUsbDisk = Join-Path (Join-Path $script:Stage 'System') 'USBDISK.APP'
    if ($UsbDisk -eq '1') {
        Test-RequiredFile $stagedUsbDisk `
            'selected USBDISK.APP; reinstall the MK61s board'
    } elseif ([IO.File]::Exists($stagedUsbDisk)) {
        Stop-Mk61Build 'resident USB-disk bundle unexpectedly contains USBDISK.APP'
    }

    # Older builders put a same-named BIN directly in binary/.  It is not the
    # result of this compile and is easily mistaken for the fresh bundle.
    # Remove only the obsolete flat files for the profile just built.
    $legacyResident = Join-Path $outputRoot "$Bundle.bin"
    foreach ($legacyPath in @($legacyResident, "$legacyResident.flags")) {
        if ([IO.File]::Exists($legacyPath)) {
            Remove-Item -LiteralPath $legacyPath -Force
        }
    }
    $output = Join-Path $outputRoot $Bundle
    $outputSystem = Join-Path $output 'System'
    [IO.Directory]::CreateDirectory($outputSystem) | Out-Null
    Copy-Item -LiteralPath (Join-Path $script:Stage "$Bundle.bin") `
        -Destination (Join-Path $output "$Bundle.bin") -Force
    Copy-Item -LiteralPath (Join-Path $script:Stage "$Bundle.elf") `
        -Destination (Join-Path $output "$Bundle.elf") -Force
    foreach ($canonical in @('FOCAL.APP', 'BASIC.APP', 'WBMP.APP',
            'MARKDOWN.APP', 'CHIP8.APP', 'SETUP.APP', 'USBDISK.APP',
            'EXPLORER.APP', 'HELP0.TXT', 'HELP1.TXT')) {
        $source = Join-Path (Join-Path $script:Stage 'System') $canonical
        $target = Join-Path $outputSystem $canonical
        if ([IO.File]::Exists($source)) {
            Copy-Item -LiteralPath $source -Destination $target -Force
        } elseif ([IO.File]::Exists($target)) {
            Remove-Item -LiteralPath $target -Force
        }
    }
    $publishedUsbDisk = Join-Path $outputSystem 'USBDISK.APP'
    if ($UsbDisk -eq '1') {
        Test-RequiredFile $publishedUsbDisk 'published USBDISK.APP'
    } elseif ([IO.File]::Exists($publishedUsbDisk)) {
        Stop-Mk61Build 'published resident USB-disk bundle contains stale USBDISK.APP'
    }
    Remove-Mk61BundledUiFontLicenses -Output $output
    if ($uiFonts -eq '1') {
        Invoke-Mk61Tool $powerShell @(
            '-NoLogo', '-NoProfile', '-File',
            (Join-Path $Sketch `
                '../tools/.fmk-font/package-ui-font-licenses.ps1'),
            '-Bundle', $output)
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $output 'build.flags'),
        $CompileFlags + " -DMK61_PORTABLE_UI_FONTS=$uiFonts" +
            " -DMK61_APP_LOCAL_FLOAT_MATH=$LocalFloatMath" +
            [Environment]::NewLine, $utf8)
    [IO.File]::WriteAllText((Join-Path $output 'build.apps'),
        'format 1' + [Environment]::NewLine +
            'abi 6' + [Environment]::NewLine, $utf8)
    Write-Host ''
    Write-Host "MK61s $($Mcu.ToUpperInvariant()) unified ABI 6 bundle built by Arduino IDE:"
    Write-Host "  $output"
    Write-Host 'Arduino IDE Upload will flash resident and install System APP through CDC.'
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
