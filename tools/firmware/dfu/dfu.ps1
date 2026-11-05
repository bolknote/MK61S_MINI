# Standalone DFU transport shared by Arduino IDE and the native frontend.
# STM32CubeProgrammer is installed independently; no Arduino Core/tools apply.
function Get-Mk61Programmer {
    param([string]$Requested)
    $selected = $Requested
    if ([string]::IsNullOrWhiteSpace($selected)) { $selected = $env:MK61_STM32_PROGRAMMER }
    $candidates = New-Object 'Collections.Generic.List[string]'
    if (-not [string]::IsNullOrWhiteSpace($selected)) {
        $candidates.Add($selected)
    } else {
        $candidates.Add('STM32_Programmer_CLI.exe')
        $candidates.Add('STM32_Programmer_CLI')
        foreach ($variable in @('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)')) {
            $directory = [Environment]::GetEnvironmentVariable($variable)
            if (-not [string]::IsNullOrWhiteSpace($directory)) {
                $candidates.Add((Join-Path $directory 'STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe'))
            }
        }
    }
    foreach ($candidate in $candidates) {
        if ([IO.File]::Exists($candidate)) { return [IO.Path]::GetFullPath($candidate) }
        $command = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command) { return $command.Source }
    }
    throw ('STM32CubeProgrammer CLI not found. Install STM32CubeProgrammer with its DFU driver; ' +
        'put STM32_Programmer_CLI.exe on PATH or set MK61_STM32_PROGRAMMER to its full path.')
}

function Invoke-Mk61ResidentDfu {
    param(
        [Parameter(Mandatory = $true)][string]$InputFile,
        [string]$Programmer,
        [string]$Vid = '0x0483',
        [string]$UsbPid = '0xdf11',
        [string]$Address = '0x8000000',
        [string]$Start = '0x8000000'
    )
    if (-not [IO.File]::Exists($InputFile)) { throw "resident image not found: $InputFile" }
    $executable = Get-Mk61Programmer $Programmer
    Write-Host "Uploading resident via STM32CubeProgrammer: $InputFile"
    & $executable '--connect' 'port=usb1' "VID=$Vid" "PID=$UsbPid" `
        '--download' ([IO.Path]::GetFullPath($InputFile).Replace('\', '/')) $Address `
        '--verify' '--start' $Start
    if ($LASTEXITCODE -ne 0) { throw "STM32 DFU failed with exit code $LASTEXITCODE" }
}
