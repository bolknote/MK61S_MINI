#requires -Version 5.1

[CmdletBinding()]
param(
    [ValidateSet(
        'mini-v3-a00',
        'mini-v3-a02',
        'mini-v2-a00',
        'mini-v2-a02',
        'classic-v2',
        'classic-v3',
        '40th')]
    [string]$Profile = 'mini-v3-a00',

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
$script:CoreVersion = '2.12.0'
$script:ToolchainVersion = '14.2.1-1.1'
$script:CmsisVersion = '6.2.0'
$script:CmsisDspVersion = '1.16.2'

function Show-Usage {
    @'
Build matched STM32F401 resident firmware and System APP with GNU Arm GCC.
Arduino IDE and arduino-cli are not invoked.

Usage:
  tools\build-gcc.cmd [-Profile ID] [options]

Profiles:
  mini-v3-a00 (default), mini-v3-a02, mini-v2-a00, mini-v2-a02,
  classic-v2, classic-v3, 40th

System APP:
  -Focal 0|1       default 1
  -Basic 0|1       default 1
  -Wbmp auto|0|1   default auto; standalone viewer when Markdown=0
  -Markdown 0|1    default 1; handles both T2 and I1 on graphics
  -Chip8 0|1       default 0

Firmware options:
  -UsbScreen 0|1
  -ExtendedFontSettings 0|1
  -UserExplorer 0|1
  -MathBackend 0|1
  -Lto 0|1          default 1

Paths:
  -CorePath DIR       STM32 Arduino Core 2.12.0
  -ToolchainPath DIR  xPack GNU Arm 14.2.1-1.1 or its bin directory
  -LibrariesPath DIR  Arduino libraries directory
  -BuildRoot DIR      default .build\gcc
  -OutputDirectory DIR default binary

Other:
  -Jobs N
  -Clean
  -Check             validate dependencies without building
  -Help

Required in PATH: CMake 3.21 or newer and Ninja.
Required Arduino libraries: LiquidCrystal 1.0.7, STM32duino RTC 1.9.0.

Environment overrides:
  MK61_GCC_CORE, MK61_GCC_TOOLCHAIN, MK61_ARDUINO_LIBRARY_ROOT,
  MK61_GCC_BUILD_ROOT, MK61_OUTPUT_DIR
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
    switch ($Id) {
        'mini-v3-a00' {
            return @{
                Bundle = 'mk61s-M-mini-v3-lcd1602-a00-f401'
                Flags = @('-DMK61_LCD1602_A00')
                Graphics = $false
            }
        }
        'mini-v3-a02' {
            return @{
                Bundle = 'mk61s-M-mini-v3-lcd1602-a02-f401'
                Flags = @('-DMK61_LCD1602_A02')
                Graphics = $false
            }
        }
        'mini-v2-a00' {
            return @{
                Bundle = 'mk61s-M-mini-v2-lcd1602-a00-f401'
                Flags = @('-DREVISION_V2', '-DMK61_LCD1602_A00')
                Graphics = $false
            }
        }
        'mini-v2-a02' {
            return @{
                Bundle = 'mk61s-M-mini-v2-lcd1602-a02-f401'
                Flags = @('-DREVISION_V2', '-DMK61_LCD1602_A02')
                Graphics = $false
            }
        }
        'classic-v2' {
            return @{
                Bundle = 'mk61s-M-classic-v2-uc1609-f401'
                Flags = @('-DMK61_BOARD_CLASSIC_V2')
                Graphics = $true
            }
        }
        'classic-v3' {
            return @{
                Bundle = 'mk61s-M-classic-v3-uc1609-f401'
                Flags = @('-DMK61_BOARD_CLASSIC_V3')
                Graphics = $true
            }
        }
        '40th' {
            return @{
                Bundle = 'mk61s-M-40th-f401'
                Flags = @('-DMK61_BOARD_40TH')
                Graphics = $true
            }
        }
    }
    Stop-GccBuild "unsupported profile: $Id"
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
    $profileInfo = Get-ProfileInfo $Profile
    if ($Markdown -eq '1') {
        $Wbmp = '0'
    } elseif ($Wbmp -eq 'auto') {
        $Wbmp = if ($profileInfo.Graphics -or $UsbScreen -eq '1') {
            '1'
        } else {
            '0'
        }
    }
    if (-not $profileInfo.Graphics -and $UsbScreen -eq '0' -and
        ($Wbmp -eq '1' -or $Chip8 -eq '1')) {
        Stop-GccBuild (
            'WBMP/CHIP-8 requires a UC1609 profile or -UsbScreen 1')
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
    if ((Get-LibraryVersion $liquidCrystal) -ne '1.0.7') {
        Stop-GccBuild 'LiquidCrystal 1.0.7 is required'
    }
    if ((Get-LibraryVersion $rtc) -ne '1.9.0') {
        Stop-GccBuild 'STM32duino RTC 1.9.0 is required'
    }

    $cmake = Get-CommandPath 'cmake' 'CMake 3.21 or newer'
    $ninja = Get-CommandPath 'ninja' 'Ninja'
    $cmakeVersion = @(& $cmake '--version')[0]
    if ($LASTEXITCODE -ne 0 -or
        $cmakeVersion -notmatch 'cmake version ([0-9.]+)' -or
        [version]$Matches[1] -lt [version]'3.21') {
        Stop-GccBuild 'CMake 3.21 or newer is required'
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
        "-DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$ExtendedFontSettings",
        "-DMK61_USER_EXPLORER_SHORTCUT=$UserExplorer",
        "-DMK61_MATH_BACKEND=$MathBackend",
        "-DMK61_ENABLE_LTO=$Lto"
    )
    Invoke-GccTool $cmake $configureArguments
    Invoke-GccTool $cmake @(
        '--build', $buildDirectory,
        '--target', 'resident',
        '--parallel', [string]$Jobs)

    $residentElf = Join-Path $buildDirectory 'resident.elf'
    $residentBin = Join-Path $buildDirectory 'resident.bin'
    $compileCommands = Join-Path $buildDirectory 'compile_commands.json'
    Test-RequiredFile $residentElf 'resident ELF'
    Test-RequiredFile $residentBin 'resident BIN'
    Test-RequiredFile $compileCommands 'CMake compile database'

    $stage = Join-Path $buildDirectory 'bundle'
    if ([IO.Directory]::Exists($stage)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    $systemRequested = $Focal -eq '1' -or $Basic -eq '1' -or
        $Wbmp -eq '1' -or $Markdown -eq '1' -or $Chip8 -eq '1'
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
    $flagValues.Add(
        "-DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$ExtendedFontSettings")
    $flagValues.Add("-DMK61_USER_EXPLORER_SHORTCUT=$UserExplorer")
    $flagValues.Add("-DMK61_MATH_BACKEND=$MathBackend")
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
