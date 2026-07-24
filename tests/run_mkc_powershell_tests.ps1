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
[void](New-Item -ItemType Directory -Path (Join-Path $tempRoot 'app-limits'))
[void](New-Item -ItemType Directory -Path (Join-Path $tempRoot 'editor'))
[IO.File]::WriteAllText((Join-Path $local 'demo.foc'), "2+2`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'blocked.bin'), 'raw', [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'Good/program.m61'), "001`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $local 'preview.wbmp'), [byte[]](0,0,8,2,15,240))
[IO.File]::WriteAllBytes((Join-Path $local 'FOCAL.APP'), [byte[]]::new(64))
[IO.File]::WriteAllBytes((Join-Path $local 'DEMO.APP'), [byte[]]::new(64))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'app-limits/HUGE.APP'), [byte[]]::new(20545))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'app-limits/SMALL.APP'), [byte[]]::new(63))
[IO.File]::WriteAllText((Join-Path $tempRoot 'editor/local.txt'), "alpha`r`nbeta`r`n",
    [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'editor/bom.txt'),
    [byte[]](0xEF,0xBB,0xBF,0x62,0x6F,0x6D,0x0D,0x0A))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'editor/bare-cr.txt'),
    [byte[]](0x62,0x61,0x72,0x65,0x0D))
[IO.File]::WriteAllText((Join-Path $device 'edit.txt'), "remote`n",
    [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'editor/control.txt'),
    [byte[]](27,117,110,115,97,102,101,10))

try {
    $supported = Invoke-MkcTool @('--classify', (Join-Path $local 'demo.foc'))
    Assert-True ($supported.ExitCode -eq 0 -and ($supported.Output -join '') -eq 'supported') 'PowerShell classifier rejected .foc'
    $systemApp = Invoke-MkcTool @('--classify', (Join-Path $local 'FOCAL.APP'))
    Assert-True ($systemApp.ExitCode -eq 0 -and ($systemApp.Output -join '') -eq 'supported') 'PowerShell classifier rejected FOCAL.APP'
    $app = Invoke-MkcTool @('--classify', (Join-Path $local 'DEMO.APP'))
    Assert-True ($app.ExitCode -eq 0 -and ($app.Output -join '') -eq 'supported') 'PowerShell classifier rejected APP'
    $unsupported = Invoke-MkcTool @('--classify', (Join-Path $local 'blocked.bin'))
    Assert-True ($unsupported.ExitCode -eq 1 -and ($unsupported.Output -join '') -eq 'unsupported: формат не поддерживается') 'PowerShell classifier accepted .bin'
    $smallApp = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'app-limits/SMALL.APP'))
    Assert-True ($smallApp.ExitCode -eq 1 -and ($smallApp.Output -join '') -match '^unsupported: слишком маленький:') 'PowerShell classifier accepted undersized APP'
    $largeApp = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'app-limits/HUGE.APP'))
    Assert-True ($largeApp.ExitCode -eq 1 -and ($largeApp.Output -join '') -match '^unsupported: слишком большой:') 'PowerShell classifier accepted oversized APP'

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

    $editorLocal = Join-Path $tempRoot 'editor/local.txt'
    Assert-True (Initialize-EditorFromFile $editorLocal 'local.txt') 'PowerShell editor rejected CRLF text'
    Assert-True ($script:EditorLines.Count -eq 3) 'PowerShell editor lost the trailing logical line'
    Assert-True ($script:EditorLines[0] -eq 'alpha' -and $script:EditorLines[1] -eq 'beta') 'PowerShell editor split lines incorrectly'
    Assert-True ($script:EditorEol -eq "`r`n") 'PowerShell editor did not preserve CRLF'
    $script:EditorCursorLine = 0
    $script:EditorCursorColumn = 5
    Insert-EditorText '!'
    Split-EditorLine
    Insert-EditorText 'middle'
    Assert-True ($script:EditorLines.Count -eq 4) 'PowerShell editor did not split a line'
    Assert-True ($script:EditorLines[0] -eq 'alpha!' -and $script:EditorLines[1] -eq 'middle') 'PowerShell editor mutations differ'
    Build-EditorVisualMap 3
    Assert-True ($script:EditorVisualLines[0] -eq 0 -and $script:EditorVisualStarts[0] -eq 0) 'PowerShell wrap first row differs'
    Assert-True ($script:EditorVisualLines[1] -eq 0 -and $script:EditorVisualStarts[1] -eq 3) 'PowerShell wrap continuation differs'
    Assert-True ($script:EditorVisualLines[2] -eq 1 -and $script:EditorVisualStarts[2] -eq 0) 'PowerShell wrap added a phantom row'
    $script:EditorCursorLine = 3
    $script:EditorCursorColumn = 0
    Build-EditorVisualMap 3
    Show-EditorCursor 2
    Assert-True ($script:EditorTop -eq $script:EditorCursorVisual - 1) 'PowerShell editor did not scroll to the cursor'
    $script:EditorPanel = 'L'
    $script:EditorSource = $editorLocal
    $script:EditorName = 'local.txt'
    Assert-True (Save-Editor) 'PowerShell local editor save failed'
    Assert-True ([IO.File]::ReadAllText($editorLocal) -eq "alpha!`r`nmiddle`r`nbeta`r`n") 'PowerShell editor changed CRLF bytes'

    $editorBom = Join-Path $tempRoot 'editor/bom.txt'
    [byte[]]$expectedBom = [IO.File]::ReadAllBytes($editorBom)
    Assert-True (Initialize-EditorFromFile $editorBom 'bom.txt') 'PowerShell editor rejected UTF-8 BOM'
    Assert-True ($script:EditorBom -and $script:EditorLines[0] -eq 'bom') 'PowerShell editor exposed BOM as text'
    $bomRoundtrip = Join-Path $tempRoot 'editor/bom.roundtrip'
    Assert-True (Write-EditorFile $bomRoundtrip) 'PowerShell editor could not write BOM text'
    Assert-True (([IO.File]::ReadAllBytes($bomRoundtrip) -join ',') -eq ($expectedBom -join ',')) 'PowerShell editor changed BOM bytes'

    $bareCr = Join-Path $tempRoot 'editor/bare-cr.txt'
    Assert-True (Initialize-EditorFromFile $bareCr 'bare-cr.txt') 'PowerShell editor rejected a bare CR'
    $bareCrRoundtrip = Join-Path $tempRoot 'editor/bare-cr.roundtrip'
    Assert-True (Write-EditorFile $bareCrRoundtrip) 'PowerShell editor could not write a bare CR'
    Assert-True (([IO.File]::ReadAllBytes($bareCrRoundtrip) -join ',') -eq '98,97,114,101,13') 'PowerShell editor lost a bare CR'

    Assert-True (Initialize-EditorFromFile $editorLocal 'local.txt') 'PowerShell editor could not reload its saved text'
    $script:EditorCursorLine = 1
    $script:EditorCursorColumn = 0
    Remove-EditorCharacterBack
    Assert-True ($script:EditorLines[0] -eq 'alpha!middle' -and $script:EditorLines.Count -eq 3) 'PowerShell Backspace did not join lines'
    $script:EditorCursorColumn = $script:EditorLines[0].Length
    Remove-EditorCharacter
    Assert-True ($script:EditorLines[0] -eq 'alpha!middlebeta' -and $script:EditorLines.Count -eq 2) 'PowerShell Delete did not join lines'

    $editorRemote = Join-Path $tempRoot 'editor/remote.txt'
    Assert-True (Receive-RemoteFile '/edit.txt' $editorRemote) 'PowerShell editor mock download failed'
    Assert-True (Initialize-EditorFromFile $editorRemote 'edit.txt') 'PowerShell editor rejected remote text'
    $script:EditorCursorColumn = 6
    Insert-EditorText 'changed'
    $script:EditorPanel = 'R'
    $script:EditorName = 'edit.txt'
    $script:EditorRemoteTarget = '/edit.txt'
    Assert-True (Save-Editor) 'PowerShell remote editor save failed'
    Assert-True ([IO.File]::ReadAllText((Join-Path $device 'edit.txt')) -eq "remotechanged`n") 'PowerShell remote editor changed bytes'
    $script:EditorLines = [Collections.Generic.List[string]]::new()
    $script:EditorLines.Add(('x' * 1537))
    Assert-True (-not (Save-Editor)) 'PowerShell editor uploaded more than 1536 text bytes'
    Assert-True ($script:EditorError -match 'максимум MK61s — 1536') 'PowerShell editor size error is unclear'
    Assert-True ([IO.File]::ReadAllText((Join-Path $device 'edit.txt')) -eq "remotechanged`n") 'Rejected PowerShell editor save changed the device file'
    Assert-True (-not (Initialize-EditorFromFile (Join-Path $tempRoot 'editor/control.txt') 'control.txt')) 'PowerShell editor accepted terminal control bytes'

    Assert-True (Send-RemoteFile (Join-Path $local 'demo.foc') '/demo.foc') 'mock upload failed'
    Assert-True (Receive-RemoteFile '/demo.foc' (Join-Path $tempRoot 'download.foc')) 'mock download failed'
    Assert-True ([IO.File]::ReadAllText((Join-Path $tempRoot 'download.foc')) -eq "2+2`n") 'mock transfer changed bytes'
    Assert-True (New-RemoteDirectory '/System') 'mock System mkdir failed'
    Assert-True (Send-RemoteFile (Join-Path $local 'FOCAL.APP') '/System/FOCAL.APP') 'mock system APP upload failed'
    Assert-True (Receive-RemoteFile '/System/FOCAL.APP' (Join-Path $tempRoot 'download.app')) 'mock system APP download failed'
    Assert-True ([IO.File]::ReadAllBytes((Join-Path $tempRoot 'download.app')).Length -eq 64) 'mock APP transfer changed bytes'
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
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'FOCAL.APP') '/System/FOCAL.APP') 'system APP upload was rejected'
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'DEMO.APP') '/Applications/DEMO.APP') 'APP upload outside root was rejected'

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
            IsOpen = $true
            ReadTimeout = 0
            LastWrite = ''
            NextLine = "f`t4 B`tdemo.foc`r"
            Lines = [Collections.Generic.Queue[string]]::new()
            Writes = [Collections.Generic.List[string]]::new()
        }
        $fakeSerial | Add-Member -MemberType ScriptMethod -Name Write -Value {
            param([string]$Text)
            $this.LastWrite = $Text
            $this.Writes.Add($Text)
        }
        $fakeSerial | Add-Member -MemberType ScriptMethod -Name ReadLine -Value {
            if ($this.Lines.Count -ne 0) { return $this.Lines.Dequeue() }
            return $this.NextLine
        }
        $oldDirectSerial = $script:DirectSerial
        $oldMockRoot = $script:MockRoot
        try {
            $script:DirectSerial = $fakeSerial
            Assert-True (Send-RemoteLine 'ls "/"') 'direct COM write failed'
            Assert-True ($fakeSerial.LastWrite -eq "ls `"/`"`r") 'direct COM write does not use terminal CR'
            Assert-True (Read-SerialLine 250) 'direct COM read failed'
            Assert-True ($script:SerialLine -eq "f`t4 B`tdemo.foc") 'direct COM read did not trim CR'

            $fakeSerial.Writes.Clear()
            $fakeSerial.Lines.Enqueue("f`t4 B`tsecond.m61`r")
            $fakeSerial.Lines.Enqueue("2 entries.`r")
            $fakeSerial.Lines.Enqueue("f`t3 B`tfirst.m61`r")
            $fakeSerial.Lines.Enqueue("f`t4 B`tsecond.m61`r")
            $fakeSerial.Lines.Enqueue("2 entries.`r")
            $script:MockRoot = ''
            $retriedEntries = @(Get-RemoteEntries '/')
            Assert-True ($retriedEntries.Count -eq 2) 'incomplete COM listing was accepted'
            Assert-True ($retriedEntries[0].Name -eq 'first.m61') 'listing retry still lost its first entry'
            Assert-True (@($fakeSerial.Writes | Where-Object { $_ -eq "ls `"/`"`r" }).Count -eq 2) 'incomplete COM listing was not retried'
        } finally {
            $script:DirectSerial = $oldDirectSerial
            $script:MockRoot = $oldMockRoot
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
