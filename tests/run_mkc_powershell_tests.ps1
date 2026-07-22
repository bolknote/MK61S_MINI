#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tool = Join-Path $root 'tools/.mkc/mkc.ps1'
$shellTool = Join-Path $root 'tools/.mkc/mkc.sh'
$launcher = Join-Path $root 'tools/mkc.cmd'
$pwsh = (Get-Process -Id $PID).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Invoke-MkcTool {
    param([string[]]$Arguments)
    $output = & $pwsh -NoLogo -NoProfile -File $tool @Arguments 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

Assert-True (Test-Path -LiteralPath $tool -PathType Leaf) 'PowerShell MKC port is missing'
Assert-True (Test-Path -LiteralPath $shellTool -PathType Leaf) 'shell MKC port is missing'
Assert-True (Test-Path -LiteralPath $launcher -PathType Leaf) 'common MKC launcher is missing'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $root 'tools/mkc.sh'))) 'legacy shell entry point is exposed'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $root 'tools/mkc.ps1'))) 'legacy PowerShell entry point is exposed'
$launcherText = [IO.File]::ReadAllText($launcher)
Assert-True ($launcherText -match '\A:; exec "\$\(dirname "\$0"\)/\.mkc/mkc\.sh" "\$@"') 'launcher is not a shell/batch polyglot'
Assert-True ($launcherText -match '(?i)pwsh\.exe -NoLogo -NoProfile -ExecutionPolicy Bypass') 'launcher does not use pwsh safely'
Assert-True ($launcherText -match '%~dp0\.mkc\\mkc\.ps1') 'launcher does not locate the hidden PowerShell port'

$tokens = $null
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile($tool, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) {
    throw ('PowerShell parser errors: ' + (@($parseErrors | ForEach-Object { $_.Message }) -join '; '))
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('mkc-powershell-tests-' + [guid]::NewGuid().ToString('N'))
$local = Join-Path $tempRoot 'local'
$device = Join-Path $tempRoot 'device'
$session = Join-Path $tempRoot 'session'
[void](New-Item -ItemType Directory -Path $local, $device, $session)
[void](New-Item -ItemType Directory -Path (Join-Path $local 'Good'))
[void](New-Item -ItemType Directory -Path (Join-Path $tempRoot 'module-limits'))
[IO.File]::WriteAllText((Join-Path $local 'demo.foc'), "2+2`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'blocked.bin'), 'raw', [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'Good/program.m61'), "001`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $local 'preview.wbmp'), [byte[]](0,0,8,2,15,240))
[IO.File]::WriteAllBytes((Join-Path $local 'FOCAL.MOD'), [byte[]]::new(64))
[IO.File]::WriteAllBytes((Join-Path $local 'OTHER.MOD'), [byte[]]::new(64))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'module-limits/WBMP.MOD'), [byte[]]::new(4097))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'module-limits/BASIC.MOD'), [byte[]]::new(63))

try {
    $supported = Invoke-MkcTool @('--classify', (Join-Path $local 'demo.foc'))
    Assert-True ($supported.ExitCode -eq 0 -and ($supported.Output -join '') -eq 'supported') 'PowerShell classifier rejected .foc'
    $module = Invoke-MkcTool @('--classify', (Join-Path $local 'FOCAL.MOD'))
    Assert-True ($module.ExitCode -eq 0 -and ($module.Output -join '') -eq 'supported') 'PowerShell classifier rejected FOCAL.MOD'
    $unsupported = Invoke-MkcTool @('--classify', (Join-Path $local 'blocked.bin'))
    Assert-True ($unsupported.ExitCode -eq 1 -and ($unsupported.Output -join '') -eq 'unsupported: формат не поддерживается') 'PowerShell classifier accepted .bin'
    $unknownModule = Invoke-MkcTool @('--classify', (Join-Path $local 'OTHER.MOD'))
    Assert-True ($unknownModule.ExitCode -eq 1 -and ($unknownModule.Output -join '') -eq 'unsupported: допустимы только FOCAL.MOD, BASIC.MOD и WBMP.MOD') 'PowerShell classifier accepted an unknown module name'
    $largeModule = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'module-limits/WBMP.MOD'))
    Assert-True ($largeModule.ExitCode -eq 1 -and ($largeModule.Output -join '') -match '^unsupported: слишком большой:') 'PowerShell classifier accepted oversized WBMP.MOD'
    $smallModule = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'module-limits/BASIC.MOD'))
    Assert-True ($smallModule.ExitCode -eq 1 -and ($smallModule.Output -join '') -match '^unsupported: слишком маленький:') 'PowerShell classifier accepted undersized BASIC.MOD'

    $oldImportOnly = $env:MKC_POWERSHELL_IMPORT_ONLY
    $env:MKC_POWERSHELL_IMPORT_ONLY = '1'
    . $tool
    $env:MKC_POWERSHELL_IMPORT_ONLY = $oldImportOnly

    Assert-True ((Normalize-RemotePath '/Programs' '../Games/./demo.m61') -eq '/Games/demo.m61') 'remote path normalization differs'
    Assert-True (Test-CdcHardwareId 'USB\VID_0483&PID_5740\3688388E3233') 'Windows CDC VID/PID was not recognized'
    Assert-True (-not (Test-CdcHardwareId 'USB\VID_0483&PID_DF11\3688388E3233')) 'DFU was mistaken for CDC'
    $pnpDevice = [pscustomobject]@{
        InstanceId = 'USB\VID_0483&PID_5740\3688388E3233'
        FriendlyName = 'USB Serial Device (COM16)'
    }
    Assert-True ((Get-CdcPortFromPnpDevice $pnpDevice) -eq 'COM16') 'Windows PnP COM-port extraction failed'
    $json = '{"detected_ports":[{"port":{"address":"COM7","properties":{"vid":"0x0483","pid":"5740"}}},{"port":{"address":"COM8","properties":{"vid":"2341","pid":"0043"}}}]}'
    Assert-True ((@(Get-CdcPortsFromJson $json) -join ',') -eq 'COM7') 'arduino-cli JSON port detection failed'
    $crc = Get-PosixChecksumBytes ([Text.Encoding]::ASCII.GetBytes('123456789'))
    Assert-True ($crc -eq 930766865) 'POSIX cksum implementation differs'

    $script:MockRoot = $device
    $script:SessionDir = $session
    $script:LocalPath = $local
    Assert-True (Send-RemoteFile (Join-Path $local 'demo.foc') '/demo.foc') 'mock upload failed'
    Assert-True (Receive-RemoteFile '/demo.foc' (Join-Path $tempRoot 'download.foc')) 'mock download failed'
    Assert-True ([IO.File]::ReadAllText((Join-Path $tempRoot 'download.foc')) -eq "2+2`n") 'mock transfer changed bytes'
    Assert-True (Send-RemoteFile (Join-Path $local 'FOCAL.MOD') '/FOCAL.MOD') 'mock module upload failed'
    Assert-True (Receive-RemoteFile '/FOCAL.MOD' (Join-Path $tempRoot 'download.mod')) 'mock module download failed'
    Assert-True ([IO.File]::ReadAllBytes((Join-Path $tempRoot 'download.mod')).Length -eq 64) 'mock module transfer changed bytes'
    Assert-True (New-RemoteDirectory '/Programs') 'mock mkdir failed'
    Assert-True (Move-RemoteItem '/demo.foc' '/Programs/moved.foc') 'mock move failed'
    $remoteEntries = @(Get-RemoteEntries '/Programs')
    Assert-True ($remoteEntries.Count -eq 1 -and $remoteEntries[0].Name -eq 'moved.foc') 'mock listing failed'
    Assert-True (Remove-RemoteItem '/Programs/moved.foc') 'mock delete failed'

    $braille = @(Convert-WbmpToBrailleLines (Join-Path $local 'preview.wbmp') 20 10)
    Assert-True ($braille[0] -eq '8×2 · Braille preview') 'WBMP dimensions were not decoded'
    Assert-True ($braille[2] -eq '⠉⠉⠒⠒') 'WBMP Braille fallback differs from shell port'

    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'Good') '/Good') 'supported directory preflight failed'
    Assert-True ($script:CopyPlan.Count -eq 2 -and $script:CopyTotal -eq 4) 'copy plan differs'
    Reset-CopyPlan
    Assert-True (-not (Add-LocalTreeToPlan $local '/Imported')) 'unsupported subtree passed preflight'
    Assert-True (-not [string]::IsNullOrEmpty($script:PlanError)) 'preflight did not report the bad file'
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'FOCAL.MOD') '/FOCAL.MOD') 'root module upload was rejected'
    Reset-CopyPlan
    Assert-True (-not (Add-LocalTreeToPlan (Join-Path $local 'FOCAL.MOD') '/Modules/FOCAL.MOD')) 'module upload outside root passed preflight'
    Assert-True ($script:PlanError -match 'только в корне под своим фиксированным именем') 'module destination error is unclear'

    $space = [ConsoleKeyInfo]::new(' ', [ConsoleKey]::Spacebar, $false, $false, $false)
    $f5 = [ConsoleKeyInfo]::new([char]0, [ConsoleKey]::F5, $false, $false, $false)
    Assert-True ((Get-UiKeyName $space) -eq 'space') 'Space is not mapped to marking'
    Assert-True ((Get-UiKeyName $f5) -eq 'f5') 'F5 is not mapped to the copy dialog'
    $oldWindowsHost = $script:IsWindowsHost
    try {
        $script:IsWindowsHost = $true
        Assert-True (Test-UseDirectSerialTransport) 'Windows still selects arduino-cli transport'
        $serial = New-ConfiguredSerialPort 'COM16'
        Assert-True ($serial.PortName -eq 'COM16' -and $serial.BaudRate -eq 115200) 'direct COM settings differ'
        Assert-True ($serial.DataBits -eq 8 -and $serial.Parity -eq 'None' -and $serial.StopBits -eq 'One') 'direct COM framing differs'
        Assert-True ($serial.DtrEnable -and -not $serial.RtsEnable) 'direct COM control lines differ'
        $serial.Dispose()
        $fakeSerial = [pscustomobject]@{
            IsOpen = $true; ReadTimeout = 0; LastWrite = ''; NextLine = "f`t4 B`tdemo.foc`r"
        }
        $fakeSerial | Add-Member -MemberType ScriptMethod -Name Write -Value {
            param([string]$Text)
            $this.LastWrite = $Text
        }
        $fakeSerial | Add-Member -MemberType ScriptMethod -Name ReadLine -Value { return $this.NextLine }
        $oldDirectSerial = $script:DirectSerial
        try {
            $script:DirectSerial = $fakeSerial
            Assert-True (Send-RemoteLine 'ls "/"') 'direct COM write failed'
            Assert-True ($fakeSerial.LastWrite -eq "ls `"/`"`r") 'direct COM write does not use terminal CR'
            Assert-True (Read-SerialLine 250) 'direct COM read failed'
            Assert-True ($script:SerialLine -eq "f`t4 B`tdemo.foc") 'direct COM read did not trim CR'
        } finally {
            $script:DirectSerial = $oldDirectSerial
        }
    } finally {
        $script:IsWindowsHost = $oldWindowsHost
    }
    $script:RemotePath = '/'
    $mockCommand = Invoke-RemoteCaptureCommand 'help'
    Assert-True ($mockCommand.Success -and ($mockCommand.Lines -join "`n") -match 'Mock MK61s terminal') 'right-panel command capture failed'
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

[Console]::WriteLine('mkc_powershell_tests: ok')
