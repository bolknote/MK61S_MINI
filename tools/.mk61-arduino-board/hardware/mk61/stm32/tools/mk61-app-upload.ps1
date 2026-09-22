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

function Stop-Mk61Upload {
    param([string]$Message)
    throw "MK61s F401 + APP upload: $Message"
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
            $deadline = [DateTime]::UtcNow.AddSeconds(45)
            while ([DateTime]::UtcNow -lt $deadline) {
                if (@([IO.Ports.SerialPort]::GetPortNames()) -contains $Port) {
                    break
                }
                Start-Sleep -Milliseconds 500
            }
            if (@([IO.Ports.SerialPort]::GetPortNames()) -notcontains $Port) {
                Stop-Mk61Upload "CDC port $Port did not return after DFU"
            }
            Start-Sleep -Seconds 2
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
