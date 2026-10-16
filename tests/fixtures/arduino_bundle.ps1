function New-Mk61TestArduinoBundle {
    param([string]$BuildPath, [string]$Bundle, [string]$Mcu = 'f401',
        [switch]$ResidentUsbDisk)
    $fixtureRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    . (Join-Path $fixtureRoot 'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-system-bundle.ps1')
    $stage = Join-Path (Join-Path $BuildPath 'mk61-system-apps') $Bundle
    $system = Join-Path $stage 'System'
    [void][IO.Directory]::CreateDirectory($system)
    foreach ($name in @('HELP0.TXT', 'HELP1.TXT')) {
        $path = Join-Path $system $name
        if (-not [IO.File]::Exists($path)) { [IO.File]::WriteAllText($path, "Help`n") }
    }
    if (-not $ResidentUsbDisk) {
        [IO.File]::WriteAllBytes((Join-Path $system 'USBDISK.APP'), [byte[]]::new(64))
    }
    $label = $Bundle.Substring(8, $Bundle.Length - 8 - $Mcu.Length - 1)
    [byte[]]$bytes = [byte[]]::new(56)
    # A real firmware contains this byte sequence in its integrity checker
    # as well as in its footer. The first occurrence is not a format header.
    [Array]::Copy([Text.Encoding]::ASCII.GetBytes('MK61FWC'), 0, $bytes, 0, 7)
    [Array]::Copy([Text.Encoding]::ASCII.GetBytes('MK61FWC'), 0, $bytes, 16, 7)
    foreach ($field in @(
        @(24, [BitConverter]::GetBytes([uint16]1)),
        @(26, [BitConverter]::GetBytes([uint16]40)),
        @(28, [BitConverter]::GetBytes([uint32]134217728)),
        @(44, [BitConverter]::GetBytes([Convert]::ToUInt32((Get-Mk61ProfileHash (Get-Mk61FirmwareProfile $label)), 16))),
        @(48, [BitConverter]::GetBytes([uint32]1)))) {
        [Array]::Copy($field[1], 0, $bytes, $field[0], $field[1].Length)
    }
    $resident = Join-Path $BuildPath 'code.ino.bin'
    [IO.File]::WriteAllBytes($resident, $bytes)
    & (Get-Process -Id $PID).Path -NoLogo -NoProfile -File (Join-Path $fixtureRoot 'tools/seal-firmware.ps1') seal -InputFile $resident | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot seal the test resident' }
    Copy-Item -LiteralPath $resident -Destination (Join-Path $stage "$Bundle.bin") -Force
    Copy-Item -LiteralPath $resident -Destination (Join-Path $stage "$Bundle.elf") -Force
    Write-Mk61SystemManifest $stage $Bundle $Mcu
    return Get-Mk61ResidentIdentity $resident
}
