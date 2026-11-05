[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BuildPath,
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$Bundle,
    [Parameter(Mandatory = $true)][string]$Profile,
    [ValidateSet('f401', 'f411')]
    [string]$Mcu = 'f401',
    [ValidateSet('0', '1')]
    [string]$RequireUsbDisk = '1',
    # Kept optional for compatibility with already installed platform.txt.
    # Arduino IDE may expand build.source.path relative to its own directory
    # during Upload, so it must not be used to locate host-side tools.
    [string]$Sketch,
    [string]$Programmer,
    [string]$Protocol = 'dfu',
    [string]$FlashOffset = '0x0',
    [string]$Vid = '0x0483',
    [string]$UsbPid = '0xdf11',
    [string]$Address = '0x8000000',
    [string]$Start = '0x8000000',
    [string]$Port,
    # Exercise the complete CDC installation in tests without touching DFU.
    [string]$TestMockDevice,
    # Also exercise DFU tool discovery with a fake tool from the test tree.
    [switch]$TestMockDfu
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$closePortMessage = 'Close every program using the MK61s COM port.'

function Stop-Mk61Upload {
    param([string]$Message)
    throw "MK61s Arduino upload: $Message"
}

. (Join-Path $PSScriptRoot 'mk61-dfu.ps1')

function Get-Mk61UploadSerialPorts {
    return @([IO.Ports.SerialPort]::GetPortNames())
}

function New-Mk61UploadProbeSerialPort {
    param([string]$PortName)
    $serial = New-Object System.IO.Ports.SerialPort
    $serial.PortName = $PortName
    $serial.BaudRate = 115200
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    return $serial
}

function Wait-Mk61SerialPortAccess {
    param([string]$PortName, [int]$TimeoutSeconds = 45)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $reportedBusy = $false
    $seenPort = $false
    do {
        if (@(Get-Mk61UploadSerialPorts) -contains $PortName) {
            $seenPort = $true
            $probe = $null
            try {
                $probe = New-Mk61UploadProbeSerialPort $PortName
                $probe.Open()
                return
            } catch [UnauthorizedAccessException] {
                if (-not $reportedBusy) {
                    Write-Host "$PortName is in use by another program. $closePortMessage Waiting for access..."
                    $reportedBusy = $true
                }
            } catch [IO.IOException] {
                # CDC may be listed just before its endpoint is ready after
                # DFU. Keep this inside the same bounded readiness wait.
            } finally {
                if ($null -ne $probe) {
                    try { if ($probe.IsOpen) { $probe.Close() } } catch {}
                    try { $probe.Dispose() } catch {}
                }
            }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $seenPort) {
        Stop-Mk61Upload "CDC port $PortName did not return after DFU"
    }
    Stop-Mk61Upload ("cannot get exclusive access to $PortName. " +
        "$closePortMessage Retry Upload after the port is released")
}

$system = ''
$residentUploaded = $false
try {
    if ($Port -eq 'auto') { $Port = '' }
    if ($Mcu -eq 'f401' -and $RequireUsbDisk -ne '1') {
        Stop-Mk61Upload 'F401 requires System/USBDISK.APP'
    }
    $expectedBundle = "mk61s-M-$Profile-$Mcu"
    if ($Bundle -cne $expectedBundle) {
        Stop-Mk61Upload "bundle $Bundle does not match profile $Profile"
    }
    $system = Join-Path (Join-Path (Join-Path $BuildPath 'mk61-system-apps') `
        $Bundle) 'System'
    $usbDisk = Join-Path $system 'USBDISK.APP'
    if ($RequireUsbDisk -eq '1') {
        if (-not [IO.File]::Exists($usbDisk) -or
            (Get-Item -LiteralPath $usbDisk).Length -eq 0) {
            Stop-Mk61Upload "current build has no selected System/USBDISK.APP: $system"
        }
    } elseif ([IO.File]::Exists($usbDisk)) {
        Stop-Mk61Upload "resident USB-disk build contains stale System/USBDISK.APP: $system"
    }
    $stage = Split-Path -Parent $system
    $mkc = Join-Path $stage 'mk61-system-installer.ps1'
    if (-not [IO.File]::Exists($mkc)) {
        Stop-Mk61Upload (
            "current build has no staged MKC terminal installer: $mkc. " +
            'Recompile with the current MK61s board package')
    }
    $resident = Join-Path $BuildPath "$Project.bin"
    if (-not [string]::IsNullOrWhiteSpace($Port) -and
        $Port -notmatch '^\{.*\}$' -and $Port -notmatch '^COM[0-9]+$') {
        Stop-Mk61Upload "selected port is not a Windows COM port: $Port"
    }
    . (Join-Path $PSScriptRoot 'mk61-system-bundle.ps1')
    $manifest = Get-VerifiedMk61SystemManifest $stage $Bundle $Mcu $resident
    $firmwareProfile = $manifest.profile
    $firmwareBuild = $manifest.build_id
    $hostPowerShell = (Get-Process -Id $PID).Path
    $checkArgs = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $mkc, '--check-system', $system)
    if ($RequireUsbDisk -eq '0') { $checkArgs += '--resident-usbdisk' }
    & $hostPowerShell @checkArgs
    if ($LASTEXITCODE -ne 0) {
        Stop-Mk61Upload "System bundle preflight failed with exit code $LASTEXITCODE"
    }
    if ([string]::IsNullOrEmpty($TestMockDevice) -or $TestMockDfu) {
        if (-not [IO.File]::Exists($resident)) {
            Stop-Mk61Upload "resident image not found: $resident"
        }
        Write-Host 'System APP installation needs exclusive COM-port access.'
        Write-Host $closePortMessage
        Invoke-Mk61ResidentDfu -InputFile $resident -Programmer $Programmer `
            -Vid $Vid -UsbPid $UsbPid -Address $Address -Start $Start
        $residentUploaded = $true
    }
    if ([string]::IsNullOrEmpty($TestMockDevice)) {
        if (-not [string]::IsNullOrWhiteSpace($Port) -and
            $Port -notmatch '^\{.*\}$') {
            Wait-Mk61SerialPortAccess $Port 45
        } else {
            $Port = ''
            Write-Host 'No COM port selected; MKC will require a unique MK61s CDC device.'
            Start-Sleep -Seconds 4
        }
    }
    $installerArgs = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $mkc,
        '--install-system', $system, '--expect-profile', $firmwareProfile,
        '--expect-build', $firmwareBuild,
        '--wait-ready', '45')
    if ($RequireUsbDisk -eq '0') {
        $installerArgs += '--resident-usbdisk'
    }
    if (-not [string]::IsNullOrEmpty($TestMockDevice)) {
        $installerArgs += @('--mock', $TestMockDevice)
    } elseif (-not [string]::IsNullOrEmpty($Port)) {
        $installerArgs += @('--port', $Port)
    }
    Write-Host "Installing current build System APP through CDC: $system"
    & $hostPowerShell @installerArgs
    if ($LASTEXITCODE -ne 0) {
        Stop-Mk61Upload "System APP installation failed with exit code $LASTEXITCODE"
    }
    Write-Host 'Resident and System APP upload complete.'
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    if ($residentUploaded -and
        -not [string]::IsNullOrEmpty($system) -and
        [IO.Directory]::Exists($system)) {
        $residentUsbDisk = if ($RequireUsbDisk -eq '0') {
            ' --resident-usbdisk'
        } else { '' }
        [Console]::Error.WriteLine(
            "Recovery without reflashing: tools\mkc.cmd --install-system `"$system`" --expect-profile $firmwareProfile --expect-build $firmwareBuild$residentUsbDisk --wait-ready 45 --port COMx")
    } elseif (-not [string]::IsNullOrEmpty($system) -and
        [IO.Directory]::Exists($system)) {
        [Console]::Error.WriteLine(
            'Resident firmware was not uploaded; correct the DFU setup and retry Upload.')
    }
    exit 1
}
