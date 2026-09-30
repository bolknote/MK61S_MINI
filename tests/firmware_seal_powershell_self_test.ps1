#requires -Version 5.1

[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Set-Le16 {
    param([byte[]]$Bytes, [int]$Offset, [uint16]$Value)
    $Bytes[$Offset] = [byte]($Value -band 0xFF)
    $Bytes[$Offset + 1] = [byte](($Value -shr 8) -band 0xFF)
}

function Set-Le32 {
    param([byte[]]$Bytes, [int]$Offset, [uint32]$Value)
    $Bytes[$Offset] = [byte]($Value -band 0xFF)
    $Bytes[$Offset + 1] = [byte](($Value -shr 8) -band 0xFF)
    $Bytes[$Offset + 2] = [byte](($Value -shr 16) -band 0xFF)
    $Bytes[$Offset + 3] = [byte](($Value -shr 24) -band 0xFF)
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw (('{0} failed with exit code {1}' -f
            [IO.Path]::GetFileName($Executable), $LASTEXITCODE))
    }
}

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$powerShell = if ($PSVersionTable.PSEdition -eq 'Desktop') {
    Join-Path $PSHOME 'powershell.exe'
} else {
    (Get-Process -Id $PID).Path
}
$work = Join-Path ([IO.Path]::GetTempPath()) `
    ("mk61-seal-ps-$PID-$([guid]::NewGuid().ToString('N'))")
[IO.Directory]::CreateDirectory($work) | Out-Null

try {
    $inputBin = Join-Path $work 'input.bin'
    $sealedBin = Join-Path $work 'sealed.bin'
    $inputElf = Join-Path $work 'input.elf'
    $sealedElf = Join-Path $work 'sealed.elf'
    $rebuiltBin = Join-Path $work 'rebuilt.bin'
    $fakeObjcopy = Join-Path $work 'fake-objcopy.ps1'
    $binSealer = Join-Path $root 'tools/seal-firmware.ps1'
    $elfSealer = Join-Path $root 'tools/seal-firmware-elf.ps1'

    [byte[]]$image = New-Object byte[] 512
    $footer = 128
    [byte[]]$magic = 0x4D, 0x4B, 0x36, 0x31, 0x46, 0x57, 0x43, 0x00
    [Array]::Copy($magic, 0, $image, $footer, $magic.Length)
    Set-Le16 $image ($footer + 8) 1
    Set-Le16 $image ($footer + 10) 40
    Set-Le32 $image ($footer + 12) ([uint32]0x08000000)
    Set-Le32 $image ($footer + 28) ([uint32]0x12345678)
    Set-Le32 $image ($footer + 32) 1
    [IO.File]::WriteAllBytes($inputBin, $image)

    Invoke-Checked $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $binSealer, 'seal',
        '-InputFile', $inputBin, '-OutputFile', $sealedBin,
        '-MaxSize', '512')
    Invoke-Checked $powerShell @(
        '-NoLogo', '-NoProfile', '-File', $binSealer, 'check',
        '-InputFile', $sealedBin, '-MaxSize', '512')

    [byte[]]$elf = New-Object byte[] 608
    [Array]::Copy($image, 0, $elf, 64, $image.Length)
    [IO.File]::WriteAllBytes($inputElf, $elf)
    @'
$inputFile = $args[$args.Count - 2]
$destination = $args[$args.Count - 1]
$bytes = [IO.File]::ReadAllBytes($inputFile)
[byte[]]$binary = New-Object byte[] ($bytes.Length - 96)
[Array]::Copy($bytes, 64, $binary, 0, $binary.Length)
[IO.File]::WriteAllBytes($Destination, $binary)
'@ | Set-Content -LiteralPath $fakeObjcopy -Encoding Ascii

    Invoke-Checked $powerShell @(
        '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $elfSealer,
        '-InputFile', $sealedBin, '-ElfFile', $inputElf,
        '-OutputFile', $sealedElf, '-Objcopy', $fakeObjcopy,
        '-MaxSize', '512')
    Invoke-Checked $powerShell @(
        '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $fakeObjcopy, '-O', 'binary', $sealedElf, $rebuiltBin)

    [byte[]]$expected = [IO.File]::ReadAllBytes($sealedBin)
    [byte[]]$actual = [IO.File]::ReadAllBytes($rebuiltBin)
    if ($expected.Length -ne $actual.Length) {
        throw 'PowerShell ELF sealer changed the resident image size'
    }
    for ($index = 0; $index -lt $expected.Length; $index++) {
        if ($expected[$index] -ne $actual[$index]) {
            throw "PowerShell ELF sealer mismatch at byte $index"
        }
    }
    Write-Output ('firmware_seal_powershell_self_test: ok ({0})' -f
        $PSVersionTable.PSVersion)
} finally {
    if ([IO.Directory]::Exists($work)) {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
}
