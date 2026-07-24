[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('check-profile', 'build')]
    [string]$Command,

    [string]$Platform,
    [string]$Display,
    [string]$Sketch,
    [string]$Compiler,
    [string]$Objcopy,
    [string]$SizeTool,
    [string]$BuildPath,
    [string]$Project,
    [string]$Bundle,
    [string]$Focal,
    [string]$Basic,
    [string]$Wbmp,
    [string]$CompileFlags
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Stop-Mk61Build {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s F401 + APP: $Message"
}

function Test-Mk61Profile {
    param([string]$PlatformId, [string]$DisplayId)
    switch ("${PlatformId}:${DisplayId}") {
        'mini-v2:lcd1602-a00' { return $true }
        'mini-v2:lcd1602-a02' { return $true }
        'mini-v3:lcd1602-a00' { return $true }
        'mini-v3:lcd1602-a02' { return $true }
        'classic-v2:uc1609' { return $true }
        'classic-v3:uc1609' { return $true }
        '40th:uc1609' { return $true }
        default { return $false }
    }
}

function Test-RequiredFile {
    param([string]$Path, [string]$Description)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [IO.File]::Exists($Path)) {
        Stop-Mk61Build "$Description not found: $Path"
    }
}

function Invoke-Mk61Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Mk61Build "$([IO.Path]::GetFileName($Path)) failed with exit code $LASTEXITCODE"
    }
}

function Get-Mk61ToolOutput {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $result = @(& $Path @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        Stop-Mk61Build "$([IO.Path]::GetFileName($Path)) failed with exit code $LASTEXITCODE"
    }
    return $result
}

function Get-Mk61Symbol {
    param([string]$Elf, [string]$Name)
    foreach ($line in (Get-Mk61ToolOutput $script:NmTool @(
        '-g', '--defined-only', $Elf
    ))) {
        $text = [string]$line
        if ($text -match '^\s*([0-9A-Fa-f]+)\s+\S+\s+(.+?)\s*$' -and
            $Matches[2] -eq $Name) {
            return $Matches[1]
        }
    }
    Stop-Mk61Build "ELF symbol not found: $Name"
}

function Get-Crc32Bytes {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Bytes,
        [int]$Count = -1
    )
    if ($Count -lt 0) {
        $Count = $Bytes.Length
    }
    if ($Count -gt $Bytes.Length) {
        Stop-Mk61Build 'internal CRC32 byte count error'
    }
    [uint32]$state = [uint32]::MaxValue
    for ($index = 0; $index -lt $Count; $index++) {
        $state = [uint32]($state -bxor [uint32]$Bytes[$index])
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($state -band [uint32]1) -ne 0) {
                $state = [uint32](($state -shr 1) -bxor
                                  [uint32]3988292384)
            } else {
                $state = [uint32]($state -shr 1)
            }
        }
    }
    return [uint32]($state -bxor [uint32]::MaxValue)
}

function Get-Crc32File {
    param([string]$Path)
    $bytes = [IO.File]::ReadAllBytes($Path)
    return Get-Crc32Bytes $bytes
}

function Set-Le16 {
    param([byte[]]$Data, [int]$Offset, [uint16]$Value)
    $Data[$Offset] = [byte]($Value -band 0xFF)
    $Data[$Offset + 1] = [byte](($Value -shr 8) -band 0xFF)
}

function Set-Le32 {
    param([byte[]]$Data, [int]$Offset, [uint32]$Value)
    $Data[$Offset] = [byte]($Value -band 0xFF)
    $Data[$Offset + 1] = [byte](($Value -shr 8) -band 0xFF)
    $Data[$Offset + 2] = [byte](($Value -shr 16) -band 0xFF)
    $Data[$Offset + 3] = [byte](($Value -shr 24) -band 0xFF)
}

function Write-Mk61App {
    param(
        [byte]$Kind,
        [string]$Resident,
        [string]$Image,
        [uint32]$MemorySize,
        [uint32]$EntryOffset,
        [uint32]$LoadAddress,
        [string]$Output
    )
    [byte[]]$residentBytes = [IO.File]::ReadAllBytes($Resident)
    [byte[]]$imageBytes = [IO.File]::ReadAllBytes($Image)
    if ($residentBytes.Length -le 0 -or
        $residentBytes.Length -gt 512KB) {
        Stop-Mk61Build 'resident BIN has an invalid size'
    }
    if ($imageBytes.Length -le 0 -or
        $imageBytes.Length -gt $MemorySize) {
        Stop-Mk61Build 'System APP image has an invalid size'
    }
    if ($MemorySize -gt 20KB -or $imageBytes.Length + 64 -gt 20544) {
        Stop-Mk61Build 'System APP does not fit the 20 KiB container'
    }
    if ($EntryOffset -ge $imageBytes.Length -or
        ($EntryOffset -band 1) -ne 0) {
        Stop-Mk61Build 'System APP has an invalid entry point'
    }

    [byte[]]$header = New-Object byte[] 64
    [byte[]]$magic = [Text.Encoding]::ASCII.GetBytes("MK61APP`0")
    [Array]::Copy($magic, 0, $header, 0, $magic.Length)
    Set-Le16 $header 8 1
    Set-Le16 $header 10 64
    Set-Le16 $header 12 2
    $header[14] = $Kind
    $header[15] = 0
    Set-Le32 $header 16 0
    Set-Le32 $header 20 $LoadAddress
    Set-Le32 $header 24 ([uint32]$imageBytes.Length)
    Set-Le32 $header 28 ([uint32]$imageBytes.Length)
    Set-Le32 $header 32 $MemorySize
    Set-Le32 $header 36 $EntryOffset
    Set-Le32 $header 40 ([uint32]$residentBytes.Length)
    Set-Le32 $header 44 (Get-Crc32Bytes $residentBytes)
    Set-Le32 $header 48 (Get-Crc32Bytes $imageBytes)
    Set-Le32 $header 52 (Get-Crc32Bytes $imageBytes)
    Set-Le32 $header 56 0
    Set-Le32 $header 60 (Get-Crc32Bytes $header 60)

    [byte[]]$container = New-Object byte[] ($header.Length +
                                            $imageBytes.Length)
    [Buffer]::BlockCopy($header, 0, $container, 0, $header.Length)
    [Buffer]::BlockCopy($imageBytes, 0, $container, $header.Length,
                        $imageBytes.Length)
    [IO.File]::WriteAllBytes($Output, $container)
}

function Get-HexUInt32 {
    param([string]$Text)
    return [Convert]::ToUInt32($Text, 16)
}

function Build-Mk61Module {
    param(
        [string]$Id,
        [string]$FileName,
        [byte]$Kind,
        [string]$EntrySymbol,
        [string]$ObjectName
    )
    $object = Join-Path (Join-Path $script:BuildPathValue 'sketch') $ObjectName
    Test-RequiredFile $object "Arduino object $ObjectName"

    $moduleDir = Join-Path (Join-Path $script:Stage 'modules') $Id
    $systemDir = Join-Path $script:Stage 'System'
    [IO.Directory]::CreateDirectory($moduleDir) | Out-Null
    [IO.Directory]::CreateDirectory($systemDir) | Out-Null
    $moduleElf = Join-Path $moduleDir "$Id.elf"
    $moduleMap = Join-Path $moduleDir "$Id.map"
    $moduleImage = Join-Path $moduleDir "$Id.bin"

    Invoke-Mk61Tool $Compiler @(
        '-mcpu=cortex-m4',
        '-mfpu=fpv4-sp-d16',
        '-mfloat-abi=hard',
        '-mthumb',
        '-Os',
        '-nostartfiles',
        '-nostdlib',
        '-Wl,--gc-sections',
        "-Wl,--just-symbols=$script:ResidentElf",
        "-Wl,--defsym=MK61_MODULE_ORIGIN=0x$script:OverlayHex",
        "-Wl,--defsym=mk61_module_entry=$EntrySymbol",
        "-Wl,-T,$script:LinkerScript",
        "-Wl,-Map,$moduleMap",
        $object,
        '-o',
        $moduleElf
    )

    $unexpected = New-Object System.Collections.Generic.List[string]
    foreach ($line in (Get-Mk61ToolOutput $SizeTool @('-A', $moduleElf))) {
        if ([string]$line -match '^\s*(\.\S+)\s+([0-9]+)\s+' -and
            [uint64]$Matches[2] -ne 0 -and
            $Matches[1] -ne '.module_image' -and
            $Matches[1] -ne '.module_bss') {
            $unexpected.Add($Matches[1])
        }
    }
    if ($unexpected.Count -ne 0) {
        Stop-Mk61Build "$FileName has unexpected ELF sections: $($unexpected -join ', ')"
    }

    [uint32]$imageStart = Get-HexUInt32 (
        Get-Mk61Symbol $moduleElf '__module_image_start')
    [uint32]$memoryEnd = Get-HexUInt32 (
        Get-Mk61Symbol $moduleElf '__module_memory_end')
    [uint32]$entryAddress = Get-HexUInt32 (
        Get-Mk61Symbol $moduleElf $EntrySymbol)
    [uint32]$memorySize = $memoryEnd - $imageStart
    [uint32]$entryOffset = $entryAddress - $imageStart
    if ($memorySize -le 0 -or $memorySize -gt 20KB -or
        $entryOffset -ge 20KB -or ($entryOffset -band 1) -ne 0) {
        Stop-Mk61Build "$FileName does not fit the 20 KiB SRAM overlay"
    }

    Invoke-Mk61Tool $Objcopy @(
        '-O', 'binary', '-j', '.module_image', $moduleElf, $moduleImage
    )
    if ($entryOffset -ge (Get-Item -LiteralPath $moduleImage).Length) {
        Stop-Mk61Build "$FileName entry point is outside its stored image"
    }
    $target = Join-Path $systemDir $FileName
    Write-Mk61App $Kind $script:ResidentBin $moduleImage $memorySize `
        $entryOffset (Get-HexUInt32 $script:OverlayHex) $target
    Write-Host ('MK61s APP: {0,-10} {1,5} bytes, SRAM {2,5} / 20480' -f
        $FileName, (Get-Item -LiteralPath $target).Length, $memorySize)
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
}

function Build-Mk61Bundle {
    Test-RequiredFile $Compiler 'ARM compiler'
    Test-RequiredFile $Objcopy 'ARM objcopy'
    Test-RequiredFile $SizeTool 'ARM size tool'
    if ([string]::IsNullOrWhiteSpace($BuildPath) -or
        -not [IO.Directory]::Exists($BuildPath)) {
        Stop-Mk61Build 'Arduino build path was not found'
    }
    if ([string]::IsNullOrWhiteSpace($Project) -or
        [string]::IsNullOrWhiteSpace($Bundle)) {
        Stop-Mk61Build 'Arduino project or bundle name is missing'
    }
    if ($Focal -notmatch '^[01]$' -or $Basic -notmatch '^[01]$' -or
        $Wbmp -notmatch '^[01]$') {
        Stop-Mk61Build 'System APP selections must be 0 or 1'
    }

    $script:BuildPathValue = [IO.Path]::GetFullPath($BuildPath)
    $compilerDirectory = [IO.Path]::GetDirectoryName(
        [IO.Path]::GetFullPath($Compiler))
    $script:NmTool = Join-Path $compilerDirectory 'arm-none-eabi-nm.exe'
    if (-not [IO.File]::Exists($script:NmTool)) {
        $script:NmTool = Join-Path $compilerDirectory 'arm-none-eabi-nm'
    }
    Test-RequiredFile $script:NmTool 'ARM nm tool'
    $script:LinkerScript = Join-Path $PSScriptRoot 'mk61_module.ld'
    Test-RequiredFile $script:LinkerScript 'MK61 APP linker script'
    $script:ResidentElf = Join-Path $script:BuildPathValue "$Project.elf"
    $script:ResidentBin = Join-Path $script:BuildPathValue "$Project.bin"
    Test-RequiredFile $script:ResidentElf 'resident ELF'
    Test-RequiredFile $script:ResidentBin 'resident BIN'
    $script:OverlayHex = Get-Mk61Symbol $script:ResidentElf `
        'mk61_module_overlay'

    $stageRoot = Join-Path $script:BuildPathValue 'mk61-system-apps'
    $script:Stage = [IO.Path]::GetFullPath((Join-Path $stageRoot $Bundle))
    $safePrefix = $script:BuildPathValue.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar
    if (-not $script:Stage.StartsWith(
        $safePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Mk61Build 'unsafe staging path'
    }
    if ([IO.Directory]::Exists($script:Stage)) {
        Remove-Item -LiteralPath $script:Stage -Recurse -Force
    }
    [IO.Directory]::CreateDirectory(
        (Join-Path $script:Stage 'System')) | Out-Null
    Copy-Item -LiteralPath $script:ResidentBin `
        -Destination (Join-Path $script:Stage "$Bundle.bin")

    if ($Focal -eq '1') {
        Build-Mk61Module 'focal' 'FOCAL.APP' 1 `
            'mk61_ide_focal_module_entry' 'mk61_ide_focal_app.cpp.o'
    }
    if ($Basic -eq '1') {
        Build-Mk61Module 'basic' 'BASIC.APP' 2 `
            'mk61_ide_basic_module_entry' 'mk61_ide_basic_app.cpp.o'
    }
    if ($Wbmp -eq '1') {
        Build-Mk61Module 'wbmp' 'WBMP.APP' 3 `
            'mk61_ide_wbmp_module_entry' 'mk61_ide_wbmp_app.cpp.o'
    }

    $outputRoot = [IO.Path]::GetFullPath((Join-Path $Sketch '..\binary'))
    $output = Join-Path $outputRoot $Bundle
    $outputSystem = Join-Path $output 'System'
    [IO.Directory]::CreateDirectory($outputSystem) | Out-Null
    Copy-Item -LiteralPath (Join-Path $script:Stage "$Bundle.bin") `
        -Destination (Join-Path $output "$Bundle.bin") -Force
    foreach ($canonical in @('FOCAL.APP', 'BASIC.APP', 'WBMP.APP')) {
        $source = Join-Path (Join-Path $script:Stage 'System') $canonical
        $target = Join-Path $outputSystem $canonical
        if ([IO.File]::Exists($source)) {
            Copy-Item -LiteralPath $source -Destination $target -Force
        } elseif ([IO.File]::Exists($target)) {
            Remove-Item -LiteralPath $target -Force
        }
    }
    if ((Get-ChildItem -LiteralPath $outputSystem -Force).Count -eq 0) {
        Remove-Item -LiteralPath $outputSystem
    }
    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText(
        (Join-Path $output 'build.flags'),
        $CompileFlags + [Environment]::NewLine,
        $utf8NoBom)
    [IO.File]::WriteAllText(
        (Join-Path $output 'build.apps'),
        'format 1' + [Environment]::NewLine,
        $utf8NoBom)

    Write-Host ''
    Write-Host 'MK61s F401 bundle built by Arduino IDE:'
    Write-Host "  $output"
    Write-Host ('After Upload, copy the generated System directory to ' +
                '/System on MK61S C5.')
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
