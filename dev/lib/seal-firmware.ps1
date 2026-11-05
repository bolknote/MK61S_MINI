#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('seal', 'check')]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$InputFile,

    [string]$OutputFile,

    [ValidateRange(1, 1048576)]
    [int]$MaxSize = 524288
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Magic = [byte[]](0x4D, 0x4B, 0x36, 0x31, 0x46, 0x57, 0x43, 0x00)
$FooterSize = 40
$Version = 1
$ImageStart = [uint32]0x08000000
$RequiredFlag = [uint32]1
$KnownFlags = [uint32]1
$CrcPolynomial = [uint32]3988292384
$ImageSizeOffset = 16
$CrcOffset = 20
$BuildIdOffset = 24

function Get-Le16 {
    param([byte[]]$Bytes, [int]$Offset)
    if ($Offset -lt 0 -or $Offset + 2 -gt $Bytes.Length) {
        throw 'truncated 16-bit field'
    }
    return [uint16]([uint16]$Bytes[$Offset] -bor
        ([uint16]$Bytes[$Offset + 1] -shl 8))
}

function Get-Le32 {
    param([byte[]]$Bytes, [int]$Offset)
    if ($Offset -lt 0 -or $Offset + 4 -gt $Bytes.Length) {
        throw 'truncated 32-bit field'
    }
    return [uint32](
        [uint32]$Bytes[$Offset] -bor
        ([uint32]$Bytes[$Offset + 1] -shl 8) -bor
        ([uint32]$Bytes[$Offset + 2] -shl 16) -bor
        ([uint32]$Bytes[$Offset + 3] -shl 24))
}

function Set-Le32 {
    param([byte[]]$Bytes, [int]$Offset, [uint32]$Value)
    if ($Offset -lt 0 -or $Offset + 4 -gt $Bytes.Length) {
        throw 'truncated 32-bit field'
    }
    $Bytes[$Offset] = [byte]($Value -band 0xFF)
    $Bytes[$Offset + 1] = [byte](($Value -shr 8) -band 0xFF)
    $Bytes[$Offset + 2] = [byte](($Value -shr 16) -band 0xFF)
    $Bytes[$Offset + 3] = [byte](($Value -shr 24) -band 0xFF)
}

function Test-MagicAt {
    param([byte[]]$Bytes, [int]$Offset)
    if ($Offset -lt 0 -or $Offset + $Magic.Length -gt $Bytes.Length) {
        return $false
    }
    for ($index = 0; $index -lt $Magic.Length; $index++) {
        if ($Bytes[$Offset + $index] -ne $Magic[$index]) {
            return $false
        }
    }
    return $true
}

function Find-Footer {
    param([byte[]]$Bytes)
    $found = -1
    for ($offset = 0; $offset + $FooterSize -le $Bytes.Length; $offset++) {
        if (-not (Test-MagicAt $Bytes $offset)) { continue }
        if ((Get-Le16 $Bytes ($offset + 8)) -ne $Version -or
            (Get-Le16 $Bytes ($offset + 10)) -ne $FooterSize -or
            (Get-Le32 $Bytes ($offset + 12)) -ne $ImageStart) {
            continue
        }
        if ($found -ge 0) { throw 'multiple resident firmware footers' }
        $found = $offset
    }
    if ($found -lt 0) { throw 'resident firmware footer not found' }
    if (($found -band 3) -ne 0) {
        throw 'resident firmware footer is not aligned'
    }
    return $found
}

function Get-CanonicalCrc32 {
    param([byte[]]$Bytes, [int]$Footer)
    [uint32]$state = [uint32]::MaxValue
    $crcZero = $Footer + $CrcOffset
    $buildZero = $Footer + $BuildIdOffset
    for ($index = 0; $index -lt $Bytes.Length; $index++) {
        [uint32]$value = if (
            ($index -ge $crcZero -and $index -lt $crcZero + 4) -or
            ($index -ge $buildZero -and $index -lt $buildZero + 4)) {
            0
        } else {
            $Bytes[$index]
        }
        $state = [uint32]($state -bxor $value)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($state -band 1) -ne 0) {
                $state = [uint32](($state -shr 1) -bxor $CrcPolynomial)
            } else {
                $state = [uint32]($state -shr 1)
            }
        }
    }
    return [uint32]($state -bxor [uint32]::MaxValue)
}

try {
    $inputPath = [IO.Path]::GetFullPath($InputFile)
    if (-not [IO.File]::Exists($inputPath)) {
        throw "cannot open input: $inputPath"
    }
    [byte[]]$bytes = [IO.File]::ReadAllBytes($inputPath)
    if ($bytes.Length -eq 0 -or $bytes.Length -gt $MaxSize) {
        throw 'resident image exceeds configured Flash capacity or is empty'
    }
    $footer = Find-Footer $bytes
    $build = Get-Le32 $bytes ($footer + 24)
    $profile = Get-Le32 $bytes ($footer + 28)
    $flags = Get-Le32 $bytes ($footer + 32)
    $reserved = Get-Le32 $bytes ($footer + 36)
    if ($profile -eq 0) {
        throw 'resident footer has an invalid profile identity'
    }
    if (($flags -band $RequiredFlag) -eq 0) {
        throw 'resident image was not compiled with CRC required'
    }
    if (($flags -band ([uint32]::MaxValue -bxor $KnownFlags)) -ne 0 -or
        $reserved -ne 0) {
        throw 'resident footer has unsupported flags/reserved data'
    }

    if ($Mode -eq 'seal') {
        Set-Le32 $bytes ($footer + $ImageSizeOffset) ([uint32]$bytes.Length)
        Set-Le32 $bytes ($footer + $CrcOffset) 0
        Set-Le32 $bytes ($footer + $BuildIdOffset) 0
        $checksum = Get-CanonicalCrc32 $bytes $footer
        Set-Le32 $bytes ($footer + $CrcOffset) $checksum
        Set-Le32 $bytes ($footer + $BuildIdOffset) $checksum
        if ([string]::IsNullOrWhiteSpace($OutputFile)) {
            $outputPath = $inputPath
        } else {
            $outputPath = [IO.Path]::GetFullPath($OutputFile)
        }
        $temporary = "$outputPath.mk61-seal.$PID.tmp"
        [IO.File]::WriteAllBytes($temporary, $bytes)
        Move-Item -LiteralPath $temporary -Destination $outputPath -Force
    }

    $declaredSize = Get-Le32 $bytes ($footer + $ImageSizeOffset)
    $expected = Get-Le32 $bytes ($footer + $CrcOffset)
    $build = Get-Le32 $bytes ($footer + $BuildIdOffset)
    $actual = Get-CanonicalCrc32 $bytes $footer
    if ($declaredSize -ne $bytes.Length) {
        throw 'resident footer image size does not match BIN'
    }
    if ($actual -ne $expected) {
        throw 'resident firmware CRC mismatch'
    }
    if ($build -eq 0 -or $build -ne $expected) {
        throw 'resident firmware build identity mismatch'
    }
    $state = if ($Mode -eq 'seal') { 'sealed' } else { 'valid' }
    [Console]::WriteLine(
        ('resident firmware: {0} size={1} footer={2} crc={3:X8} ' +
         'build={4:X8} profile={5:X8}'),
        $state, $bytes.Length, $footer, $expected, $build, $profile)
} catch {
    [Console]::Error.WriteLine(
        "mk61_firmware_seal: $($_.Exception.Message)")
    exit 2
}
