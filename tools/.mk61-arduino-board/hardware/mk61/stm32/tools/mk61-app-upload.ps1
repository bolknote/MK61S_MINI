[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BuildPath,
    [Parameter(Mandatory = $true)][string]$Project,
    [Parameter(Mandatory = $true)][string]$Bundle,
    [Parameter(Mandatory = $true)][string]$Profile,
    [Parameter(Mandatory = $true)][string]$Sketch,
    [string]$Busybox,
    [string]$Stm32Script,
    [string]$Protocol = 'dfu',
    [string]$FlashOffset = '0x0',
    [string]$Vid = '0x0483',
    [string]$UsbPid = '0xdf11',
    [string]$Address = '0x8000000',
    [string]$Start = '0x8000000',
    [string]$Port,
    # Exercise the complete CDC installation in tests without touching DFU.
    [string]$TestMockDevice
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$closePortMessage = 'Close every program using the MK61s COM port.'

function Stop-Mk61Upload {
    param([string]$Message)
    throw "MK61s F401 + APP upload: $Message"
}

function Wait-Mk61SerialPortAccess {
    param([string]$PortName, [int]$TimeoutSeconds = 45)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $reportedBusy = $false
    $seenPort = $false
    do {
        if (@([IO.Ports.SerialPort]::GetPortNames()) -contains $PortName) {
            $seenPort = $true
            $probe = $null
            try {
                $probe = New-Object System.IO.Ports.SerialPort
                $probe.PortName = $PortName
                $probe.BaudRate = 115200
                $probe.DtrEnable = $false
                $probe.RtsEnable = $false
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
try {
    $expectedBundle = "mk61s-M-$Profile-f401"
    if ($Bundle -cne $expectedBundle) {
        Stop-Mk61Upload "bundle $Bundle does not match profile $Profile"
    }
    $system = Join-Path (Join-Path (Join-Path $BuildPath 'mk61-system-apps') `
        $Bundle) 'System'
    $usbDisk = Join-Path $system 'USBDISK.APP'
    if (-not [IO.File]::Exists($usbDisk) -or
        (Get-Item -LiteralPath $usbDisk).Length -eq 0) {
        Stop-Mk61Upload "current build has no System/USBDISK.APP: $system"
    }
    $mkc = [IO.Path]::GetFullPath((Join-Path $Sketch '../tools/.mkc/mkc.ps1'))
    if (-not [IO.File]::Exists($mkc)) {
        Stop-Mk61Upload "MKC terminal installer not found: $mkc"
    }
    $resident = Join-Path $BuildPath "$Project.bin"
    if ([string]::IsNullOrEmpty($TestMockDevice)) {
        if (-not [IO.File]::Exists($resident)) {
            Stop-Mk61Upload "resident image not found: $resident"
        }
        if (-not [IO.File]::Exists($Busybox) -or
            -not [IO.File]::Exists($Stm32Script)) {
            Stop-Mk61Upload 'STM32 DFU tools not found'
        }
        Write-Host 'System APP installation needs exclusive COM-port access.'
        Write-Host $closePortMessage
        Write-Host "Uploading resident via STM32 DFU: $resident"
        & $Busybox sh $Stm32Script -i $Protocol -f $resident `
            -o $FlashOffset -v $Vid -p $UsbPid -a $Address -s $Start
        if ($LASTEXITCODE -ne 0) {
            Stop-Mk61Upload "STM32 DFU failed with exit code $LASTEXITCODE"
        }
        if (-not [string]::IsNullOrWhiteSpace($Port) -and
            $Port -notmatch '^\{.*\}$') {
            if ($Port -notmatch '^COM[0-9]+$') {
                Stop-Mk61Upload "selected port is not a Windows COM port: $Port"
            }
            Wait-Mk61SerialPortAccess $Port 45
        } else {
            $Port = ''
            Write-Host 'No COM port selected; MKC will require a unique MK61s CDC device.'
            Start-Sleep -Seconds 4
        }
    }
    $hostPowerShell = (Get-Process -Id $PID).Path
    $installerArgs = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', $mkc,
        '--install-system', $system, '--expect-profile', $Profile)
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
    if (-not [string]::IsNullOrEmpty($system) -and
        [IO.Directory]::Exists($system)) {
        [Console]::Error.WriteLine(
            "Recovery without reflashing: tools\mkc.cmd --install-system `"$system`" --expect-profile $Profile --port COMx")
    }
    exit 1
}
