#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputFile,

    [Parameter(Mandatory = $true)]
    [string]$ElfFile,

    [Parameter(Mandatory = $true)]
    [string]$Objcopy,

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
$ImageSizeOffset = 16

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

function Get-CurrentPowerShell {
    if ($PSVersionTable.PSEdition -eq 'Desktop') {
        return (Join-Path $PSHOME 'powershell.exe')
    }
    return (Get-Process -Id $PID).Path
}

try {
    $binPath = [IO.Path]::GetFullPath($InputFile)
    $elfPath = [IO.Path]::GetFullPath($ElfFile)
    $objcopyPath = [IO.Path]::GetFullPath($Objcopy)
    foreach ($required in @($binPath, $elfPath, $objcopyPath)) {
        if (-not [IO.File]::Exists($required)) {
            throw "required input not found: $required"
        }
    }

    # Keep the long-established BIN validator isolated from ELF mutation.
    # In particular, Windows Arduino IDE invokes this script through the
    # inbox Windows PowerShell 5.1 rather than PowerShell 7.
    $sealer = Join-Path $PSScriptRoot 'seal-firmware.ps1'
    if (-not [IO.File]::Exists($sealer)) {
        throw "resident firmware sealer not found: $sealer"
    }
    $powerShell = Get-CurrentPowerShell
    & $powerShell '-NoLogo' '-NoProfile' '-File' $sealer 'check' `
        '-InputFile' $binPath '-MaxSize' ([string]$MaxSize)
    if ($LASTEXITCODE -ne 0) {
        throw "resident firmware validation failed with exit code $LASTEXITCODE"
    }

    [byte[]]$binBytes = [IO.File]::ReadAllBytes($binPath)
    [byte[]]$elfBytes = [IO.File]::ReadAllBytes($elfPath)
    if ($binBytes.Length -eq 0 -or $binBytes.Length -gt $MaxSize) {
        throw 'resident image exceeds configured Flash capacity or is empty'
    }
    $binFooter = Find-Footer $binBytes
    $elfFooter = Find-Footer $elfBytes
    foreach ($fieldOffset in @(28, 32, 36)) {
        if ((Get-Le32 $binBytes ($binFooter + $fieldOffset)) -ne
            (Get-Le32 $elfBytes ($elfFooter + $fieldOffset))) {
            throw 'BIN and ELF resident footers do not match'
        }
    }
    [Array]::Copy($binBytes, $binFooter + $ImageSizeOffset,
        $elfBytes, $elfFooter + $ImageSizeOffset, 12)

    $outputPath = if ([string]::IsNullOrWhiteSpace($OutputFile)) {
        $elfPath
    } else {
        [IO.Path]::GetFullPath($OutputFile)
    }
    [IO.Directory]::CreateDirectory(
        [IO.Path]::GetDirectoryName($outputPath)) | Out-Null
    $token = "$PID.$([guid]::NewGuid().ToString('N'))"
    $temporaryElf = "$outputPath.$token.tmp"
    $temporaryBin = "$outputPath.$token.verify.bin"
    try {
        [IO.File]::WriteAllBytes($temporaryElf, $elfBytes)
        & $objcopyPath '-O' 'binary' $temporaryElf $temporaryBin
        if ($LASTEXITCODE -ne 0) {
            throw (('{0} failed with exit code {1}' -f
                [IO.Path]::GetFileName($objcopyPath), $LASTEXITCODE))
        }
        [byte[]]$rebuilt = [IO.File]::ReadAllBytes($temporaryBin)
        $same = $rebuilt.Length -eq $binBytes.Length
        $mismatch = [Math]::Min($rebuilt.Length, $binBytes.Length)
        if ($same) {
            for ($index = 0; $index -lt $binBytes.Length; $index++) {
                if ($rebuilt[$index] -ne $binBytes[$index]) {
                    $same = $false
                    $mismatch = $index
                    break
                }
            }
        }
        if (-not $same) {
            throw (('sealed ELF does not reproduce sealed BIN exactly ' +
                '(first mismatch {0}, ELF BIN {1} bytes, expected {2} bytes)') -f
                $mismatch, $rebuilt.Length, $binBytes.Length)
        }
        Move-Item -LiteralPath $temporaryElf `
            -Destination $outputPath -Force
        $temporaryElf = $null
    } finally {
        foreach ($temporary in @($temporaryElf, $temporaryBin)) {
            if ($null -ne $temporary -and
                [IO.File]::Exists($temporary)) {
                Remove-Item -LiteralPath $temporary -Force
            }
        }
    }
    $crc = Get-Le32 $binBytes ($binFooter + 20)
    $profile = Get-Le32 $binBytes ($binFooter + 28)
    Write-Output (('resident firmware ELF: sealed size={0} footer={1} ' +
        'crc={2:X8} profile={3:X8}') -f
        $binBytes.Length, $binFooter, $crc, $profile)
} catch {
    [Console]::Error.WriteLine(
        "mk61_firmware_elf_seal: $($_.Exception.Message)")
    exit 2
}
