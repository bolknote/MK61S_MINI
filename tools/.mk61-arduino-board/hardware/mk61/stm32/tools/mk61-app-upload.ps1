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

function Add-Mk61UniquePath {
    param(
        [Collections.Generic.List[string]]$Paths,
        [Collections.Generic.HashSet[string]]$Seen,
        [string]$Path
    )
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    try { $full = [IO.Path]::GetFullPath($Path) } catch { return }
    if ($Seen.Add($full)) { $Paths.Add($full) }
}

function Find-Mk61Stm32DfuTools {
    param([string]$RequestedBusybox, [string]$RequestedScript)

    $resolvedBusybox = $RequestedBusybox
    $resolvedScript = $RequestedScript

    # When Arduino expanded only one of the inherited STM32 platform
    # properties, derive the other path from the same STM32Tools package.
    if ([IO.File]::Exists($resolvedScript) -and
        -not [IO.File]::Exists($resolvedBusybox)) {
        $candidate = Join-Path (Split-Path -Parent $resolvedScript) `
            'win\busybox.exe'
        if ([IO.File]::Exists($candidate)) { $resolvedBusybox = $candidate }
    }
    if ([IO.File]::Exists($resolvedBusybox) -and
        -not [IO.File]::Exists($resolvedScript)) {
        $busyboxDirectory = Split-Path -Parent $resolvedBusybox
        $candidate = Join-Path (Split-Path -Parent $busyboxDirectory) `
            'stm32CubeProg.sh'
        if ([IO.File]::Exists($candidate)) { $resolvedScript = $candidate }
    }
    if ([IO.File]::Exists($resolvedBusybox) -and
        [IO.File]::Exists($resolvedScript)) {
        return [pscustomobject]@{
            Busybox = [IO.Path]::GetFullPath($resolvedBusybox)
            Script = [IO.Path]::GetFullPath($resolvedScript)
            Searched = @()
        }
    }

    # Arduino IDE 1.x does not reliably export inherited runtime.tools.*
    # properties to a manually installed hardware platform. Locate the exact
    # package that Boards Manager installed instead of requiring that property.
    $dataDirectories = New-Object 'Collections.Generic.List[string]'
    $seenDataDirectories = New-Object `
        'Collections.Generic.HashSet[string]' `
        ([StringComparer]::OrdinalIgnoreCase)
    Add-Mk61UniquePath $dataDirectories $seenDataDirectories `
        $env:MK61_ARDUINO_DATA_DIR
    $localData = [Environment]::GetFolderPath('LocalApplicationData')
    if (-not [string]::IsNullOrWhiteSpace($localData)) {
        Add-Mk61UniquePath $dataDirectories $seenDataDirectories `
            (Join-Path $localData 'Arduino15')
    }
    $profile = [Environment]::GetFolderPath('UserProfile')
    if (-not [string]::IsNullOrWhiteSpace($profile)) {
        Add-Mk61UniquePath $dataDirectories $seenDataDirectories `
            (Join-Path $profile '.arduino15')
    }

    $searched = New-Object 'Collections.Generic.List[string]'
    foreach ($dataDirectory in $dataDirectories) {
        $toolsDirectory = Join-Path $dataDirectory `
            'packages\STMicroelectronics\tools\STM32Tools'
        $searched.Add($toolsDirectory)
        if (-not [IO.Directory]::Exists($toolsDirectory)) { continue }
        $versions = @(Get-ChildItem -LiteralPath $toolsDirectory `
            -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending)
        foreach ($version in $versions) {
            $candidateScript = Join-Path $version.FullName `
                'stm32CubeProg.sh'
            $candidateBusybox = Join-Path $version.FullName `
                'win\busybox.exe'
            if ([IO.File]::Exists($candidateScript) -and
                [IO.File]::Exists($candidateBusybox)) {
                return [pscustomobject]@{
                    Busybox = $candidateBusybox
                    Script = $candidateScript
                    Searched = $searched.ToArray()
                }
            }
        }
    }

    $busyboxDescription = if (
        [string]::IsNullOrWhiteSpace($RequestedBusybox)) {
        '<empty>'
    } else { $RequestedBusybox }
    $scriptDescription = if (
        [string]::IsNullOrWhiteSpace($RequestedScript)) {
        '<empty>'
    } else { $RequestedScript }
    $searchedDescription = if ($searched.Count -eq 0) {
        '<no Arduino data directory found>'
    } else { $searched -join '; ' }
    Stop-Mk61Upload (
        "STM32 DFU tools not found. BusyBox from Arduino: " +
        "'$busyboxDescription'; STM32 script from Arduino: " +
        "'$scriptDescription'; searched: $searchedDescription. " +
        'Install STM32 MCU based boards 2.12.0 in Boards Manager')
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
$residentUploaded = $false
try {
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
    if ([string]::IsNullOrEmpty($TestMockDevice) -or $TestMockDfu) {
        if (-not [IO.File]::Exists($resident)) {
            Stop-Mk61Upload "resident image not found: $resident"
        }
        $dfuTools = Find-Mk61Stm32DfuTools $Busybox $Stm32Script
        Write-Host 'System APP installation needs exclusive COM-port access.'
        Write-Host $closePortMessage
        Write-Host "Uploading resident via STM32 DFU: $resident"
        # Pass every option and its value as one token. Windows PowerShell 5.1
        # can otherwise hand BusyBox/getopt a detached -f without its path;
        # STM32's wrapper then reports a misleading "missing binary file".
        # Forward slashes also keep the subsequent shell eval from treating
        # backslashes in C:\Users\... as escapes.
        $scriptForShell = $dfuTools.Script.Replace('\', '/')
        $residentForShell = $resident.Replace('\', '/')
        $dfuArguments = @(
            'sh',
            $scriptForShell,
            "--interface=$Protocol",
            "--file=$residentForShell",
            "--offset=$FlashOffset",
            "--vid=$Vid",
            "--pid=$UsbPid",
            "--address=$Address",
            "--start=$Start"
        )
        & $dfuTools.Busybox @dfuArguments
        if ($LASTEXITCODE -ne 0) {
            Stop-Mk61Upload "STM32 DFU failed with exit code $LASTEXITCODE"
        }
        $residentUploaded = $true
    }
    if ([string]::IsNullOrEmpty($TestMockDevice)) {
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
        '--install-system', $system, '--expect-profile', $Profile,
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
            "Recovery without reflashing: tools\mkc.cmd --install-system `"$system`" --expect-profile $Profile$residentUsbDisk --wait-ready 45 --port COMx")
    } elseif (-not [string]::IsNullOrEmpty($system) -and
        [IO.Directory]::Exists($system)) {
        [Console]::Error.WriteLine(
            'Resident firmware was not uploaded; correct the DFU setup and retry Upload.')
    }
    exit 1
}
