#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$Profile = 'mini-v3-a00',

    [ValidatePattern('^[a-z0-9][a-z0-9-]*$')]
    [string]$ReleaseCase,

    [ValidateSet('0', '1')]
    [string]$Focal = '1',

    [ValidateSet('0', '1')]
    [string]$Basic = '1',

    [ValidateSet('auto', '0', '1')]
    [string]$Wbmp = 'auto',

    [ValidateSet('0', '1')]
    [string]$Markdown = '1',

    [ValidateSet('0', '1')]
    [string]$Chip8 = '0',

    [ValidateSet('0', '1')]
    [string]$UsbScreen = '0',

    [ValidateSet('0', '1')]
    [string]$Ws0010Graphics = '0',

    [ValidateSet('0', '1')]
    [string]$ExtendedFontSettings = '0',

    [ValidateSet('0', '1')]
    [string]$UserExplorer = '1',

    [ValidateSet('0', '1')]
    [string]$MathBackend = '0',

    [ValidateSet('0', '1')]
    [string]$Lto = '1',

    [string]$CorePath,
    [string]$ToolchainPath,
    [string]$LibrariesPath,
    [string]$BuildRoot,
    [string]$OutputDirectory,

    [ValidateRange(1, 128)]
    [int]$Jobs = [Environment]::ProcessorCount,

    [switch]$Clean,
    [switch]$Check,
    [switch]$Help
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:BackendRoot = $PSScriptRoot
$script:ProjectRoot = [IO.Path]::GetFullPath(
    (Join-Path $script:BackendRoot '../..'))
$script:Utf8NoBom = New-Object Text.UTF8Encoding($false)
$script:ReleaseManifest = $null
$script:CoreVersion = $null
$script:ToolchainVersion = $null
$script:CmsisVersion = $null
$script:CmsisDspVersion = $null

function Show-Usage {
    @'
Build matched STM32F401 resident firmware and System APP with GNU Arm GCC.
Arduino IDE and arduino-cli are not invoked.

Usage:
  tools\build-gcc.cmd [-Profile ID] [options]

Profiles and release budgets are defined by tools/release-contract.json.
Run `python3 tools/release_contract.py profiles` to list profile IDs.

System APP:
  -Focal 0|1       default 1
  -Basic 0|1       default 1
  -Wbmp auto|0|1   default auto; standalone viewer when Markdown=0
  -Markdown 0|1    default 1; handles both T2 and I1 on graphics
  -Chip8 0|1       default 0

Firmware options:
  -UsbScreen 0|1
  -Ws0010Graphics 0|1  WEH001602A 100x16 Markdown/WBMP qualification
  -ExtendedFontSettings 0|1
  -UserExplorer 0|1
  -MathBackend 0|1
  -Lto 0|1          default 1

Paths:
  -CorePath DIR       pinned STM32 Arduino Core
  -ToolchainPath DIR  pinned xPack GNU Arm directory or its bin directory
  -LibrariesPath DIR  Arduino libraries directory
  -BuildRoot DIR      default .build\gcc
  -OutputDirectory DIR default binary

Other:
  -Jobs N
  -Clean
  -Check             validate dependencies without building
  -Help

Required in PATH: CMake 3.21 or newer, Ninja, and a host C++17 compiler
when at least one System APP is enabled.
Required versions are read from tools/release-contract.json.

Environment overrides:
  MK61_GCC_CORE, MK61_GCC_TOOLCHAIN, MK61_ARDUINO_LIBRARY_ROOT,
  MK61_GCC_BUILD_ROOT, MK61_OUTPUT_DIR, MK61_HOST_CXX
'@ | Write-Host
}

function Stop-GccBuild {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s GCC build: $Message"
}

function Get-FullPath {
    param([string]$Path, [string]$Base = $script:ProjectRoot)
    if ([IO.Path]::IsPathRooted($Path)) {
        return [IO.Path]::GetFullPath($Path)
    }
    return [IO.Path]::GetFullPath((Join-Path $Base $Path))
}

function Test-RequiredFile {
    param([string]$Path, [string]$Description)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [IO.File]::Exists($Path)) {
        Stop-GccBuild "$Description not found: $Path"
    }
}

function Test-RequiredDirectory {
    param([string]$Path, [string]$Description)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [IO.Directory]::Exists($Path)) {
        Stop-GccBuild "$Description not found: $Path"
    }
}

function Get-CommandPath {
    param([string]$Name, [string]$Description)
    $command = Get-Command $Name -CommandType Application `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        Stop-GccBuild "$Description is not in PATH: $Name"
    }
    return $command.Source
}

function Invoke-GccTool {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-GccBuild (
            "$([IO.Path]::GetFileName($Path)) failed with exit code " +
            "$LASTEXITCODE")
    }
}

function Get-FirstExistingDirectory {
    param([string[]]$Candidates)
    foreach ($candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and
            [IO.Directory]::Exists($candidate)) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }
    return $null
}

function Get-DefaultCorePath {
    $relative = "packages/STMicroelectronics/hardware/stm32/$script:CoreVersion"
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if (-not [string]::IsNullOrWhiteSpace($env:MK61_GCC_CORE)) {
        $candidates.Add($env:MK61_GCC_CORE)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates.Add((Join-Path (
            Join-Path $env:LOCALAPPDATA 'Arduino15') $relative))
    }
    if (-not [string]::IsNullOrWhiteSpace($HOME)) {
        $candidates.Add((Join-Path (
            Join-Path $HOME 'Library/Arduino15') $relative))
        $candidates.Add((Join-Path (
            Join-Path $HOME '.arduino15') $relative))
    }
    return Get-FirstExistingDirectory $candidates.ToArray()
}

function Get-DefaultLibrariesPath {
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if (-not [string]::IsNullOrWhiteSpace(
            $env:MK61_ARDUINO_LIBRARY_ROOT)) {
        $candidates.Add($env:MK61_ARDUINO_LIBRARY_ROOT)
    }
    $documents = [Environment]::GetFolderPath('MyDocuments')
    if (-not [string]::IsNullOrWhiteSpace($documents)) {
        $candidates.Add((Join-Path $documents 'Arduino/libraries'))
    }
    if (-not [string]::IsNullOrWhiteSpace($HOME)) {
        $candidates.Add((Join-Path $HOME 'Documents/Arduino/libraries'))
        $candidates.Add((Join-Path $HOME 'Arduino/libraries'))
    }
    return Get-FirstExistingDirectory $candidates.ToArray()
}

function Get-LibraryVersion {
    param([string]$Directory)
    $properties = Join-Path $Directory 'library.properties'
    Test-RequiredFile $properties 'Arduino library.properties'
    foreach ($line in [IO.File]::ReadAllLines($properties)) {
        if ($line -match '^\s*version\s*=\s*(\S+)\s*$') {
            return $Matches[1]
        }
    }
    Stop-GccBuild "library version is missing in $properties"
}

function Get-ProfileInfo {
    param([string]$Id)
    $matches = @($script:ReleaseManifest.profiles | Where-Object {
        $_.id -eq $Id
    })
    if ($matches.Count -ne 1) {
        Stop-GccBuild "unsupported profile: $Id"
    }
    $selected = $matches[0]
    return @{
        Bundle = [string]$selected.artifacts.f401
        Flags = @($selected.defines | ForEach-Object { "-D$_" })
        Graphics = [bool]$selected.graphics
    }
}

function Get-ReleaseCase {
    param([string]$Id)
    if ([string]::IsNullOrWhiteSpace($Id)) {
        return $null
    }
    $matches = @($script:ReleaseManifest.cases | Where-Object {
        $_.id -eq $Id
    })
    if ($matches.Count -ne 1) {
        Stop-GccBuild "unknown release case: $Id"
    }
    $selected = $matches[0]
    if ($selected.mcu -ne 'f401' -or $selected.builder -ne 'gcc') {
        Stop-GccBuild "release case is not an F401 GCC case: $Id"
    }
    if ($selected.profile -ne $Profile) {
        Stop-GccBuild (
            "release case $Id requires profile $($selected.profile), " +
            "not $Profile")
    }
    return $selected
}

function Test-SafeBuildDirectory {
    param([string]$Directory, [string]$Root)
    $directoryValue = [IO.Path]::GetFullPath($Directory).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar)
    $rootValue = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar)
    $prefix = $rootValue + [IO.Path]::DirectorySeparatorChar
    if (-not $directoryValue.StartsWith(
            $prefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-GccBuild "unsafe build directory: $Directory"
    }
}

function Remove-GeneratedBundleFiles {
    param([string]$Directory, [string]$ResidentName)
    foreach ($name in @($ResidentName, 'build.flags', 'build.apps')) {
        $path = Join-Path $Directory $name
        if ([IO.File]::Exists($path)) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    $system = Join-Path $Directory 'System'
    foreach ($name in @(
        'FOCAL.APP', 'BASIC.APP', 'WBMP.APP', 'MARKDOWN.APP', 'CHIP8.APP'
    )) {
        $path = Join-Path $system $name
        if ([IO.File]::Exists($path)) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    if ([IO.Directory]::Exists($system) -and
        @(Get-ChildItem -LiteralPath $system -Force).Count -eq 0) {
        Remove-Item -LiteralPath $system
    }
    $customApps = Join-Path $Directory 'Apps'
    if ([IO.Directory]::Exists($customApps)) {
        Remove-Item -LiteralPath $customApps -Recurse -Force
    }
}

function Get-CurrentPowerShell {
    if ($PSVersionTable.PSEdition -eq 'Desktop') {
        $candidate = Join-Path $PSHOME 'powershell.exe'
        Test-RequiredFile $candidate 'Windows PowerShell'
        return $candidate
    }
    $candidate = (Get-Process -Id $PID).Path
    Test-RequiredFile $candidate 'PowerShell'
    return $candidate
}

if ($Help) {
    Show-Usage
    exit 0
}

try {
    $manifestPath = Join-Path $script:ProjectRoot 'tools/release-contract.json'
    $contractTool = Join-Path $script:ProjectRoot 'tools/release_contract.py'
    Test-RequiredFile $manifestPath 'release contract manifest'
    Test-RequiredFile $contractTool 'release contract tool'
    $python = Get-CommandPath 'python3' 'Python 3'
    Invoke-GccTool $python @($contractTool, 'validate')
    $script:ReleaseManifest = ConvertFrom-Json -InputObject (
        [IO.File]::ReadAllText($manifestPath))
    $script:CoreVersion = [string]$script:ReleaseManifest.toolchain.stm32_core
    $script:ToolchainVersion = [string]$script:ReleaseManifest.toolchain.gnu_arm
    $script:CmsisVersion = [string]$script:ReleaseManifest.toolchain.cmsis
    $script:CmsisDspVersion = [string]$script:ReleaseManifest.toolchain.cmsis_dsp

    $profileInfo = Get-ProfileInfo $Profile
    $ws0010Bitmap = $Profile -eq 'mini-v3-ws0010' -and
        $Ws0010Graphics -eq '1'
    $fullGraphics = $profileInfo.Graphics -or $UsbScreen -eq '1'
    $wbmpGraphics = $fullGraphics -or $ws0010Bitmap
    if ($Wbmp -eq 'auto') {
        $Wbmp = if ($wbmpGraphics -and $Markdown -ne '1') {
            '1'
        } else {
            '0'
        }
    }
    if ($Markdown -eq '1' -and $wbmpGraphics) {
        $Wbmp = '0'
    }
    if (-not $wbmpGraphics -and $Wbmp -eq '1') {
        Stop-GccBuild (
            'WBMP requires UC1609, -UsbScreen 1, or WS0010 with ' +
            '-Ws0010Graphics 1')
    }
    if (-not $fullGraphics -and $Chip8 -eq '1') {
        Stop-GccBuild (
            'CHIP-8 requires a UC1609 profile or -UsbScreen 1')
    }
    if ($Ws0010Graphics -eq '1' -and $Profile -ne 'mini-v3-ws0010') {
        Stop-GccBuild (
            '-Ws0010Graphics 1 requires profile mini-v3-ws0010')
    }
    $systemRequested = $Focal -eq '1' -or $Basic -eq '1' -or
        $Wbmp -eq '1' -or $Markdown -eq '1' -or $Chip8 -eq '1'
    $releaseCaseInfo = Get-ReleaseCase $ReleaseCase
    if ($null -ne $releaseCaseInfo) {
        $actualFeatures = @{
            focal = $Focal
            basic = $Basic
            wbmp = $Wbmp
            markdown = $Markdown
            chip8 = $Chip8
            usb_screen = $UsbScreen
            ws0010_graphics = $Ws0010Graphics
            extended_font_settings = $ExtendedFontSettings
            user_explorer = $UserExplorer
            math_backend = $MathBackend
            lto = $Lto
        }
        foreach ($name in $actualFeatures.Keys) {
            $expected = [string](
                $releaseCaseInfo.features.PSObject.Properties[$name].Value)
            if ($actualFeatures[$name] -ne $expected) {
                Stop-GccBuild (
                    "release case $ReleaseCase requires $name=$expected, " +
                    "not $($actualFeatures[$name])")
            }
        }
        $flashCapacity = [string]$releaseCaseInfo.budgets.flash_capacity
        $flashHeadroom = [string](
            $releaseCaseInfo.budgets.flash_min_headroom)
        $ramLimit = [string]$releaseCaseInfo.budgets.ram_limit
        $stackFrameLimit = [string](
            $releaseCaseInfo.budgets.stack_frame_limit)
    } else {
        $flashCapacity = '262144'
        $flashHeadroom = '512'
        $ramLimit = if ($Lto -eq '1' -and $UsbScreen -ne '1') {
            '52428'
        } else {
            '65536'
        }
        $stackFrameLimit = '5120'
    }

    if ([string]::IsNullOrWhiteSpace($CorePath)) {
        $CorePath = Get-DefaultCorePath
    } else {
        $CorePath = Get-FullPath $CorePath (Get-Location).Path
    }
    Test-RequiredDirectory $CorePath `
        "STM32 Arduino Core $script:CoreVersion"
    $platformText = Join-Path $CorePath 'platform.txt'
    Test-RequiredFile $platformText 'STM32 Core platform.txt'
    if (-not ([IO.File]::ReadAllText($platformText) -match
            "(?m)^version=$([regex]::Escape($script:CoreVersion))\s*$")) {
        Stop-GccBuild "STM32 Arduino Core $script:CoreVersion is required"
    }

    $stm32Hardware = [IO.Directory]::GetParent($CorePath).FullName
    $hardware = [IO.Directory]::GetParent($stm32Hardware).FullName
    $vendorRoot = [IO.Directory]::GetParent($hardware).FullName
    $toolSuffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }

    if ([string]::IsNullOrWhiteSpace($ToolchainPath)) {
        if (-not [string]::IsNullOrWhiteSpace(
                $env:MK61_GCC_TOOLCHAIN)) {
            $ToolchainPath = $env:MK61_GCC_TOOLCHAIN
        } else {
            $ToolchainPath = Join-Path $vendorRoot (
                "tools/xpack-arm-none-eabi-gcc/" +
                $script:ToolchainVersion)
        }
    } else {
        $ToolchainPath = Get-FullPath $ToolchainPath (Get-Location).Path
    }
    if ([IO.File]::Exists((Join-Path $ToolchainPath (
            "arm-none-eabi-g++$toolSuffix")))) {
        $toolchainBin = [IO.Path]::GetFullPath($ToolchainPath)
    } else {
        $toolchainBin = Join-Path $ToolchainPath 'bin'
    }
    Test-RequiredFile (Join-Path $toolchainBin (
        "arm-none-eabi-g++$toolSuffix")) `
        "GNU Arm C++ compiler $script:ToolchainVersion"

    $cmsisRoot = Join-Path $vendorRoot (
        "tools/CMSIS/$script:CmsisVersion")
    $cmsisDspRoot = Join-Path $vendorRoot (
        "tools/CMSIS_DSP/$script:CmsisDspVersion")
    Test-RequiredDirectory $cmsisRoot "CMSIS $script:CmsisVersion"
    Test-RequiredDirectory $cmsisDspRoot `
        "CMSIS DSP $script:CmsisDspVersion"

    if ([string]::IsNullOrWhiteSpace($LibrariesPath)) {
        $LibrariesPath = Get-DefaultLibrariesPath
    } else {
        $LibrariesPath = Get-FullPath $LibrariesPath (Get-Location).Path
    }
    Test-RequiredDirectory $LibrariesPath 'Arduino libraries directory'
    $liquidCrystal = Join-Path $LibrariesPath 'LiquidCrystal'
    $rtc = Join-Path $LibrariesPath 'STM32duino_RTC'
    Test-RequiredDirectory $liquidCrystal 'LiquidCrystal library'
    Test-RequiredDirectory $rtc 'STM32duino RTC library'
    $lcdVersion = [string](
        $script:ReleaseManifest.toolchain.libraries.LiquidCrystal)
    $rtcVersion = [string](
        $script:ReleaseManifest.toolchain.libraries.'STM32duino RTC')
    if ((Get-LibraryVersion $liquidCrystal) -ne $lcdVersion) {
        Stop-GccBuild "LiquidCrystal $lcdVersion is required"
    }
    if ((Get-LibraryVersion $rtc) -ne $rtcVersion) {
        Stop-GccBuild "STM32duino RTC $rtcVersion is required"
    }

    $cmake = Get-CommandPath 'cmake' 'CMake 3.21 or newer'
    $ninja = Get-CommandPath 'ninja' 'Ninja'
    $cmakeVersion = @(& $cmake '--version')[0]
    if ($LASTEXITCODE -ne 0 -or
        $cmakeVersion -notmatch 'cmake version ([0-9.]+)' -or
        [version]$Matches[1] -lt [version]'3.21') {
        Stop-GccBuild 'CMake 3.21 or newer is required'
    }
    if ($systemRequested) {
        $hostPackerBuilder = Join-Path $script:ProjectRoot `
            'tools/.mk61-app/build.ps1'
        Test-RequiredFile $hostPackerBuilder 'MK61 APP host packer builder'
        & $hostPackerBuilder -Check | Out-Host
    }

    if ($Check) {
        [Console]::WriteLine('MK61s direct GCC dependencies: ready')
        [Console]::WriteLine("  STM32 Core: $CorePath")
        [Console]::WriteLine("  GNU Arm: $toolchainBin")
        [Console]::WriteLine("  CMSIS: $cmsisRoot")
        [Console]::WriteLine("  CMSIS DSP: $cmsisDspRoot")
        [Console]::WriteLine("  Arduino libraries: $LibrariesPath")
        [Console]::WriteLine("  CMake: $cmakeVersion")
        [Console]::WriteLine("  Ninja: $ninja")
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($BuildRoot)) {
        $BuildRoot = if (-not [string]::IsNullOrWhiteSpace(
                $env:MK61_GCC_BUILD_ROOT)) {
            $env:MK61_GCC_BUILD_ROOT
        } else {
            Join-Path $script:ProjectRoot '.build/gcc'
        }
    }
    $BuildRoot = Get-FullPath $BuildRoot
    $buildDirectory = Join-Path $BuildRoot $Profile
    Test-SafeBuildDirectory $buildDirectory $BuildRoot
    if ($Clean -and [IO.Directory]::Exists($buildDirectory)) {
        Remove-Item -LiteralPath $buildDirectory -Recurse -Force
    }
    [IO.Directory]::CreateDirectory($buildDirectory) | Out-Null

    if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
        $OutputDirectory = if (-not [string]::IsNullOrWhiteSpace(
                $env:MK61_OUTPUT_DIR)) {
            $env:MK61_OUTPUT_DIR
        } else {
            Join-Path $script:ProjectRoot 'binary'
        }
    }
    $OutputDirectory = Get-FullPath $OutputDirectory

    $toolchainFile = Join-Path $script:BackendRoot 'arm-none-eabi.cmake'
    Test-RequiredFile $toolchainFile 'GNU Arm CMake toolchain'
    $configureArguments = @(
        '-S', $script:BackendRoot,
        '-B', $buildDirectory,
        '-G', 'Ninja',
        "-DCMAKE_MAKE_PROGRAM=$ninja",
        "-DCMAKE_TOOLCHAIN_FILE=$toolchainFile",
        "-DMK61_ARM_TOOLCHAIN_BIN=$toolchainBin",
        "-DMK61_PROJECT_ROOT=$script:ProjectRoot",
        "-DMK61_CORE_VERSION=$script:CoreVersion",
        "-DMK61_STM32_CORE=$CorePath",
        "-DMK61_CMSIS_ROOT=$cmsisRoot",
        "-DMK61_CMSIS_DSP_ROOT=$cmsisDspRoot",
        "-DMK61_LIQUIDCRYSTAL_ROOT=$liquidCrystal",
        "-DMK61_RTC_ROOT=$rtc",
        "-DMK61_PROFILE=$Profile",
        "-DMK61_ENABLE_FOCAL=$Focal",
        "-DMK61_ENABLE_TINYBASIC=$Basic",
        "-DMK61_ENABLE_WBMP_VIEWER=$Wbmp",
        "-DMK61_ENABLE_MARKDOWN_VIEWER=$Markdown",
        "-DMK61_ENABLE_CHIP8=$Chip8",
        "-DMK61_ENABLE_USB_SCREEN=$UsbScreen",
        "-DMK61_WS0010_GRAPHICS_100X16=$Ws0010Graphics",
        "-DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$ExtendedFontSettings",
        "-DMK61_USER_EXPLORER_SHORTCUT=$UserExplorer",
        "-DMK61_MATH_BACKEND=$MathBackend",
        '-DMK61_REQUIRE_RESIDENT_CRC=1',
        "-DMK61_ENABLE_LTO=$Lto",
        "-DMK61_FLASH_MIN_HEADROOM=$flashHeadroom",
        "-DMK61_GLOBAL_RAM_LIMIT=$ramLimit",
        "-DMK61_STACK_FRAME_LIMIT=$stackFrameLimit"
    )
    Invoke-GccTool $cmake $configureArguments
    Invoke-GccTool $cmake @(
        '--build', $buildDirectory,
        '--target', 'resident',
        '--parallel', [string]$Jobs)

    $residentElf = Join-Path $buildDirectory 'resident.elf'
    $residentBin = Join-Path $buildDirectory 'resident.bin'
    $residentHex = Join-Path $buildDirectory 'resident.hex'
    $compileCommands = Join-Path $buildDirectory 'compile_commands.json'
    Test-RequiredFile $residentElf 'resident ELF'
    Test-RequiredFile $residentBin 'resident BIN'
    Test-RequiredFile $compileCommands 'CMake compile database'

    $powerShell = Get-CurrentPowerShell
    $sealer = Join-Path $script:ProjectRoot 'tools/seal-firmware.ps1'
    Test-RequiredFile $sealer 'resident firmware sealer'
    Invoke-GccTool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'seal',
        '-InputFile', $residentBin, '-MaxSize', $flashCapacity)
    Invoke-GccTool $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $sealer, 'check',
        '-InputFile', $residentBin, '-MaxSize', $flashCapacity)

    if ($null -ne $releaseCaseInfo) {
        $sizeTool = Join-Path $toolchainBin "arm-none-eabi-size$toolSuffix"
        $nmTool = Join-Path $toolchainBin "arm-none-eabi-nm$toolSuffix"
        Test-RequiredFile $sizeTool 'GNU Arm size tool'
        Test-RequiredFile $nmTool 'GNU Arm nm tool'
        Invoke-GccTool $python @(
            $contractTool, 'resource-report',
            '--case', $ReleaseCase,
            '--elf', $residentElf,
            '--bin', $residentBin,
            '--size-tool', $sizeTool,
            '--nm-tool', $nmTool,
            '--stack-summary', (Join-Path $buildDirectory 'stack-usage.json'),
            '--output-prefix', (Join-Path $buildDirectory 'resource-report'))
    }

    # CMake emitted HEX before the post-link footer was sealed. Regenerate it
    # from the authoritative sealed BIN so neither public format can bypass
    # the startup integrity check.
    $objcopy = Join-Path $toolchainBin "arm-none-eabi-objcopy$toolSuffix"
    Test-RequiredFile $objcopy 'GNU Arm objcopy'
    Invoke-GccTool $objcopy @(
        '-I', 'binary', '-O', 'ihex', '--change-addresses', '0x08000000',
        $residentBin, $residentHex)
    Test-RequiredFile $residentHex 'sealed resident HEX'

    $stage = Join-Path $buildDirectory 'bundle'
    if ([IO.Directory]::Exists($stage)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    if ($systemRequested) {
        $systemBuilder = Join-Path $script:ProjectRoot `
            'system_apps/.tool/build.ps1'
        Test-RequiredFile $systemBuilder 'System APP builder'
        $powerShell = Get-CurrentPowerShell
        Invoke-GccTool $powerShell @(
            '-NoLogo',
            '-NoProfile',
            '-File', $systemBuilder,
            '-BuildPath', $buildDirectory,
            '-ResidentElf', $residentElf,
            '-ResidentBin', $residentBin,
            '-CompileCommands', $compileCommands,
            '-OutputDirectory', (Join-Path $stage 'System'),
            '-Focal', $Focal,
            '-Basic', $Basic,
            '-Wbmp', $Wbmp,
            '-Markdown', $Markdown,
            '-Chip8', $Chip8)
    }

    $bundle = [string]$profileInfo.Bundle
    if ($ws0010Bitmap) {
        $variant = if ($Markdown -eq '1') {
            'graphics-markdown'
        } elseif ($Wbmp -eq '1') {
            'graphics-wbmp'
        } else {
            'graphics'
        }
        $bundle = $bundle -replace '-f401$', "-$variant-f401"
    }
    $residentName = "$bundle.bin"
    [IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
    $outputBundle = Join-Path $OutputDirectory $bundle
    [IO.Directory]::CreateDirectory($outputBundle) | Out-Null
    Remove-GeneratedBundleFiles $outputBundle $residentName
    Copy-Item -LiteralPath $residentBin `
        -Destination (Join-Path $outputBundle $residentName)
    if ([IO.Directory]::Exists((Join-Path $stage 'System'))) {
        Copy-Item -LiteralPath (Join-Path $stage 'System') `
            -Destination $outputBundle -Recurse
    }

    $flagValues = New-Object 'System.Collections.Generic.List[string]'
    foreach ($flag in $profileInfo.Flags) {
        $flagValues.Add([string]$flag)
    }
    $flagValues.Add("-DMK61_ENABLE_FOCAL=$Focal")
    $flagValues.Add("-DMK61_ENABLE_TINYBASIC=$Basic")
    $flagValues.Add("-DMK61_ENABLE_WBMP_VIEWER=$Wbmp")
    $flagValues.Add("-DMK61_ENABLE_MARKDOWN_VIEWER=$Markdown")
    $flagValues.Add("-DMK61_ENABLE_CHIP8=$Chip8")
    $flagValues.Add("-DMK61_ENABLE_USB_SCREEN=$UsbScreen")
    $flagValues.Add("-DMK61_WS0010_GRAPHICS_100X16=$Ws0010Graphics")
    $flagValues.Add(
        "-DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$ExtendedFontSettings")
    $flagValues.Add("-DMK61_USER_EXPLORER_SHORTCUT=$UserExplorer")
    $flagValues.Add("-DMK61_MATH_BACKEND=$MathBackend")
    $flagValues.Add('-DMK61_REQUIRE_RESIDENT_CRC=1')
    $flagValues.Add("-DMK61_ENABLE_LTO=$Lto")
    [IO.File]::WriteAllText(
        (Join-Path $outputBundle 'build.flags'),
        ($flagValues -join ' ') + [Environment]::NewLine,
        $script:Utf8NoBom)
    [IO.File]::WriteAllText(
        (Join-Path $outputBundle 'build.apps'),
        'format 1' + [Environment]::NewLine,
        $script:Utf8NoBom)

    [Console]::WriteLine('')
    [Console]::WriteLine('MK61s GNU Arm GCC bundle built:')
    [Console]::WriteLine("  $outputBundle")
    [Console]::WriteLine("  resident: $residentName")
    if ($systemRequested) {
        [Console]::WriteLine('  System APP: matched to this resident')
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
