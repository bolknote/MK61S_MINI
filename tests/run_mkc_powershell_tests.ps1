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
[void](New-Item -ItemType Directory -Path (Join-Path $tempRoot 'chip8-limits'))
[void](New-Item -ItemType Directory -Path (Join-Path $tempRoot 'binary-limits'))
[void](New-Item -ItemType Directory -Path (Join-Path $local 'CalculatorProgram'))
[void](New-Item -ItemType Directory -Path (Join-Path $tempRoot 'editor'))
$navigation = Join-Path $tempRoot 'navigation'
[void](New-Item -ItemType Directory -Path (Join-Path $navigation '.mkc') -Force)
[IO.File]::WriteAllText((Join-Path $local 'demo.foc'), "2+2`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'manual.md'), "# Demo`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'Игра.m61'), "Привет → ≤ ↵`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'emoji.txt'), "Ошибка 😀`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'blocked.dat'), 'raw', [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $local 'CalculatorProgram/program.bin'), [byte[]](0,1,127,128,255,13,10))
[IO.File]::WriteAllText((Join-Path $local 'CalculatorProgram/autoexec.m61'), "load 0000 program.bin`nrun`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'binary-limits/MAX.BIN'), [byte[]]::new(4096))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'binary-limits/HUGE.BIN'), [byte[]]::new(4097))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'binary-limits/SHORT.BIN'), [byte[]](1,2,3,4))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'editor/printable.bin'), [byte[]](65,66,67,68,69))
[IO.File]::WriteAllText((Join-Path $local 'Good/program.m61'), "001`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllBytes((Join-Path $local 'Good/._program.m61'), [byte[]](0,5,22,7))
[IO.File]::WriteAllText((Join-Path $local 'Good/.DS_Store'), 'metadata')
[void](New-Item -ItemType Directory -Path (Join-Path $local 'Good/System Volume Information'))
[IO.File]::WriteAllText((Join-Path $local 'Good/System Volume Information/index.txt'), 'metadata')
[IO.File]::WriteAllBytes((Join-Path $local 'preview.wbmp'), [byte[]](0,0,8,2,15,240))
[IO.File]::WriteAllBytes((Join-Path $local 'FOCAL.APP'), [byte[]]::new(64))
[IO.File]::WriteAllBytes((Join-Path $local 'DEMO.APP'), [byte[]]::new(64))
[IO.File]::WriteAllBytes((Join-Path $local 'game.ch8'), [byte[]](0,0xE0,0xA0,0))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'app-limits/HUGE.APP'), [byte[]]::new(20545))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'app-limits/SMALL.APP'), [byte[]]::new(63))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'chip8-limits/EMPTY.CH8'), [byte[]]::new(0))
[IO.File]::WriteAllBytes((Join-Path $tempRoot 'chip8-limits/HUGE.CH8'), [byte[]]::new(3585))
[IO.File]::WriteAllText((Join-Path $local 'large.tbi'), ('x' * 1537), [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'huge.tbi'), ('x' * 65535), [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $local 'huge.foc'), ('x' * 65535), [Text.UTF8Encoding]::new($false))
foreach ($extension in @('foc','tbi')) {
    [IO.File]::WriteAllText((Join-Path $local "maximum.$extension"), ('x' * 65534), [Text.UTF8Encoding]::new($false))
}
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
    $markdown = Invoke-MkcTool @('--classify', (Join-Path $local 'manual.md'))
    Assert-True ($markdown.ExitCode -eq 0 -and ($markdown.Output -join '') -eq 'supported') 'PowerShell classifier rejected .md'
    $systemApp = Invoke-MkcTool @('--classify', (Join-Path $local 'FOCAL.APP'))
    Assert-True ($systemApp.ExitCode -eq 0 -and ($systemApp.Output -join '') -eq 'supported') 'PowerShell classifier rejected FOCAL.APP'
    foreach ($extension in @('foc','tbi')) {
        $maximum = Invoke-MkcTool @('--classify', (Join-Path $local "maximum.$extension"))
        Assert-True ($maximum.ExitCode -eq 0 -and ($maximum.Output -join '') -eq 'supported') 'PowerShell classifier rejected a maximum-sized language source'
    }
    $hugeFocal = Invoke-MkcTool @('--classify', (Join-Path $local 'huge.foc'))
    Assert-True (($hugeFocal.Output -join '') -like 'unsupported: слишком большой:*') 'PowerShell classifier accepted oversized FOCAL'
    $systemBundle = Join-Path $tempRoot 'system-bundle'
    [void](New-Item -ItemType Directory -Path $systemBundle)
    [IO.File]::WriteAllBytes((Join-Path $systemBundle 'USBDISK.APP'), [byte[]]::new(64))
    [void](New-Item -ItemType Directory -Path (Join-Path $systemBundle 'VMCache'))
    [IO.File]::WriteAllBytes((Join-Path $systemBundle 'VMCache/VMSTORE.APP'), [byte[]]::new(64))
    [IO.File]::WriteAllText((Join-Path $systemBundle 'HELP0.TXT'), "Помощь`n", [Text.UTF8Encoding]::new($false))
    [void](New-Item -ItemType Directory -Path (Join-Path $device 'System'))
    [IO.File]::WriteAllBytes((Join-Path $device 'System/CHIP8.APP'), [byte[]]::new(64))
    [IO.File]::WriteAllBytes((Join-Path $device 'System/CUSTOM.APP'), [byte[]]::new(64))
    $bootstrap = Invoke-MkcTool @('--mock', $device, '--install-system', $systemBundle)
    Assert-True ($bootstrap.ExitCode -eq 0 -and
        ($bootstrap.Output -join ' ') -match 'System installation through CDC: OK') `
        'unattended System bootstrap failed'
    Assert-True ([IO.File]::Exists((Join-Path $device 'System/USBDISK.APP'))) `
        'System bootstrap did not install USBDISK.APP'
    Assert-True ([IO.File]::Exists((Join-Path $device 'System/VMCache/VMSTORE.APP'))) `
        'System bootstrap did not install the nested cache helper'
    [IO.File]::WriteAllBytes((Join-Path $device 'System/VMCache/VMC-0042.APP'), [byte[]](1,2,3))
    Assert-True (-not [IO.File]::Exists((Join-Path $device 'System/CHIP8.APP'))) `
        'System bootstrap did not remove a disabled canonical APP'
    Assert-True ([IO.File]::Exists((Join-Path $device 'System/CUSTOM.APP'))) `
        'System bootstrap removed a user APP'
    Assert-True ([IO.File]::ReadAllBytes((Join-Path $device 'System/HELP0.TXT')).Length -eq
        "Помощь`n".Length) `
        'System bootstrap did not convert HELP0.TXT to M8'
    $bootstrapText = $bootstrap.Output -join "`n"
    $preflight = Invoke-MkcTool @('--check-system', $systemBundle)
    Assert-True ($preflight.ExitCode -eq 0) 'System preflight required a device'
    $badSystem = Join-Path $tempRoot 'bad-system'
    [void](New-Item -ItemType Directory -Path $badSystem)
    [IO.File]::WriteAllBytes((Join-Path $badSystem 'USBDISK.APP'), [byte[]]::new(64))
    [IO.File]::WriteAllBytes((Join-Path $badSystem 'BASIC.APP'), [byte[]](1))
    [IO.File]::WriteAllBytes((Join-Path $device 'System/CHIP8.APP'), [byte[]]::new(64))
    $badInstall = Invoke-MkcTool @('--mock', $device, '--install-system', $badSystem)
    Assert-True ($badInstall.ExitCode -ne 0 -and
        [IO.File]::Exists((Join-Path $device 'System/CHIP8.APP'))) `
        'System installation changed files before validating all source APPs'
    Remove-Item -LiteralPath (Join-Path $device 'System/CHIP8.APP')
    Assert-True ($bootstrapText.IndexOf('Removed disabled /System/CHIP8.APP') -lt
        $bootstrapText.IndexOf('Installed and verified /System/USBDISK.APP')) `
        'System bootstrap did not free stale APP space before USBDISK.APP'

    $residentSystemBundle = Join-Path $tempRoot 'resident-system-bundle'
    [void](New-Item -ItemType Directory -Path $residentSystemBundle)
    [IO.File]::WriteAllText((Join-Path $residentSystemBundle 'HELP1.TXT'),
        "Resident help`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllBytes((Join-Path $device 'System/USBDISK.APP'),
        [byte[]]::new(64))
    [IO.File]::WriteAllBytes((Join-Path $device 'System/EXPLORER.APP'),
        [byte[]]::new(64))
    $residentBootstrap = Invoke-MkcTool @('--mock', $device,
        '--install-system', $residentSystemBundle, '--resident-usbdisk')
    Assert-True ($residentBootstrap.ExitCode -eq 0 -and
        ($residentBootstrap.Output -join ' ') -match
            'System installation through CDC: OK') `
        ('resident USB-disk System bootstrap failed: ' + ($residentBootstrap.Output -join ' '))
    Assert-True (-not [IO.File]::Exists(
        (Join-Path $device 'System/USBDISK.APP'))) `
        'resident USB-disk bootstrap kept stale USBDISK.APP'
    Assert-True (-not [IO.File]::Exists(
        (Join-Path $device 'System/EXPLORER.APP'))) `
        'System bootstrap kept stale EXPLORER.APP'
    Assert-True ([IO.File]::Exists((Join-Path $device 'System/HELP1.TXT'))) `
        'resident USB-disk bootstrap did not install help'
    Assert-True (-not [IO.File]::Exists((Join-Path $device 'System/VMCache/VMSTORE.APP'))) `
        'disabled cache helper survived System synchronisation'
    Assert-True ([IO.File]::ReadAllBytes((Join-Path $device 'System/VMCache/VMC-0042.APP')).Length -eq 3) `
        'System synchronisation removed retained bytecode data'
    $app = Invoke-MkcTool @('--classify', (Join-Path $local 'DEMO.APP'))
    Assert-True ($app.ExitCode -eq 0 -and ($app.Output -join '') -eq 'supported') 'PowerShell classifier rejected APP'
    $chip8 = Invoke-MkcTool @('--classify', (Join-Path $local 'game.ch8'))
    Assert-True ($chip8.ExitCode -eq 0 -and ($chip8.Output -join '') -eq 'supported') 'PowerShell classifier rejected CHIP-8 ROM'
    $russian = Invoke-MkcTool @('--classify', (Join-Path $local 'Игра.m61'))
    Assert-True ($russian.ExitCode -eq 0 -and ($russian.Output -join '') -eq 'supported') 'PowerShell classifier rejected M8 text/name'
    $emoji = Invoke-MkcTool @('--classify', (Join-Path $local 'emoji.txt'))
    Assert-True ($emoji.ExitCode -eq 1 -and ($emoji.Output -join '') -match 'unsupported: текст содержит символ вне M8') 'PowerShell classifier accepted unsupported Unicode'
    $binaryProgram = Invoke-MkcTool @('--classify', (Join-Path $local 'CalculatorProgram/program.bin'))
    Assert-True ($binaryProgram.ExitCode -eq 0 -and ($binaryProgram.Output -join '') -eq 'supported') 'PowerShell classifier rejected calculator BIN'
    $maxBinary = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'binary-limits/MAX.BIN'))
    Assert-True ($maxBinary.ExitCode -eq 0 -and ($maxBinary.Output -join '') -eq 'supported') 'PowerShell classifier rejected a 4096-byte BIN'
    $shortBinary = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'binary-limits/SHORT.BIN'))
    Assert-True ($shortBinary.ExitCode -eq 1 -and ($shortBinary.Output -join '') -match '^unsupported: слишком маленький:.*минимум 5$') 'PowerShell classifier accepted a BIN without CRC and stream'
    $hugeBinary = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'binary-limits/HUGE.BIN'))
    Assert-True ($hugeBinary.ExitCode -eq 1 -and ($hugeBinary.Output -join '') -match '^unsupported: слишком большой:.*максимум 4096$') 'PowerShell classifier accepted oversized BIN'
    $unsupported = Invoke-MkcTool @('--classify', (Join-Path $local 'blocked.dat'))
    Assert-True ($unsupported.ExitCode -eq 1 -and ($unsupported.Output -join '') -eq 'unsupported: формат не поддерживается') 'PowerShell classifier accepted an unknown extension'
    $smallApp = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'app-limits/SMALL.APP'))
    Assert-True ($smallApp.ExitCode -eq 1 -and ($smallApp.Output -join '') -match '^unsupported: слишком маленький:') 'PowerShell classifier accepted undersized APP'
    $largeApp = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'app-limits/HUGE.APP'))
    Assert-True ($largeApp.ExitCode -eq 1 -and ($largeApp.Output -join '') -match '^unsupported: слишком большой:') 'PowerShell classifier accepted oversized APP'
    $largeTinyBasic = Invoke-MkcTool @('--classify', (Join-Path $local 'large.tbi'))
    Assert-True ($largeTinyBasic.ExitCode -eq 0 -and ($largeTinyBasic.Output -join '') -eq 'supported') 'PowerShell classifier rejected expanded TinyBASIC source'
    $hugeTinyBasic = Invoke-MkcTool @('--classify', (Join-Path $local 'huge.tbi'))
    Assert-True ($hugeTinyBasic.ExitCode -eq 1 -and ($hugeTinyBasic.Output -join '') -match '^unsupported: слишком большой:') 'PowerShell classifier accepted oversized TinyBASIC source'
    $emptyChip8 = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'chip8-limits/EMPTY.CH8'))
    Assert-True ($emptyChip8.ExitCode -eq 1 -and ($emptyChip8.Output -join '') -match '^unsupported: слишком маленький:') 'PowerShell classifier accepted empty CHIP-8 ROM'
    $largeChip8 = Invoke-MkcTool @('--classify', (Join-Path $tempRoot 'chip8-limits/HUGE.CH8'))
    Assert-True ($largeChip8.ExitCode -eq 1 -and ($largeChip8.Output -join '') -match '^unsupported: слишком большой:') 'PowerShell classifier accepted oversized CHIP-8 ROM'

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
    $candidates = @(Get-DirectSerialCandidates 'COM12' @('COM16','com12','COM17'))
    Assert-True (($candidates -join ',') -eq 'COM12,COM16,COM17') 'direct COM candidates are not ordered or deduplicated'
    Assert-True (Test-Mk61IdentityLine 'MK61s-Classic-V3 ver. Aug 02 2026(12:34:56)') 'Classic V3 identity was rejected'
    Assert-True (Test-Mk61IdentityLine 'MK61s-40th ver. Aug 02 2026(12:34:56)') '40th identity was rejected'
    Assert-True (Test-Mk61IdentityLine 'MK61s mini ver. Jan 01 2024(00:00:00)') 'legacy MK61s identity was rejected'
    Assert-True (-not (Test-Mk61IdentityLine 'STM32F401 test firmware ver. 1')) 'unrelated STM32 identity was accepted'
    $identityLine = 'MK61 ID v=1 public=0123456789ABCDEF short=89ABCDEF usb=112233445566 volume=A1B2C3D4 build=12345678 profile=mini-v3-a00'
    $parsedIdentity = ConvertFrom-Mk61IdentityLine $identityLine
    Assert-True ($null -ne $parsedIdentity -and $parsedIdentity.Kind -eq 'identity') 'new identity handshake was rejected'
    Assert-True ($parsedIdentity.PublicId -eq '0123456789ABCDEF' -and
        $parsedIdentity.ShortId -eq '89ABCDEF' -and
        $parsedIdentity.UsbSerial -eq '112233445566') 'new identity fields were parsed incorrectly'
    Assert-True (Test-Mk61IdentitySelector $parsedIdentity '89abcdef') 'short device selector is not case-insensitive'
    Assert-True (Test-Mk61IdentitySelector $parsedIdentity '112233445566') 'USB serial selector was rejected'
    Assert-True (-not (Test-Mk61IdentitySelector $parsedIdentity 'DEADBEEF')) 'wrong device selector was accepted'
    Assert-True ($null -eq (ConvertFrom-Mk61IdentityLine `
        'MK61 ID v=1 public=bad short=bad usb=bad volume=bad build=bad profile=x')) 'malformed identity handshake was accepted'
    Assert-True ($null -eq (ConvertFrom-Mk61IdentityLine `
        'MK61 ID v=1 public=0123456789ABCDEF short=DEADBEEF usb=112233445566 volume=A1B2C3D4 build=12345678 profile=mini-v3-a00')) 'inconsistent short identity was accepted'

    $probeSerial = [pscustomobject]@{
        ReadTimeout = 777
        NextLine = 'noise'
        Lines = [Collections.Generic.Queue[string]]::new()
        Writes = [Collections.Generic.List[string]]::new()
    }
    $probeSerial | Add-Member -MemberType ScriptMethod -Name Write -Value {
        param([string]$Text)
        $this.Writes.Add($Text)
    }
    $probeSerial | Add-Member -MemberType ScriptMethod -Name ReadLine -Value {
        if ($this.Lines.Count -ne 0) { return $this.Lines.Dequeue() }
        return $this.NextLine
    }
    $probeSerial.Lines.Enqueue("ver`r")
    $probeSerial.Lines.Enqueue('sizeof Serial 216')
    $probeSerial.Lines.Enqueue('MK61s-Classic-V2 ver. Aug 02 2026(12:34:56)')
    Assert-True (Test-DirectSerialMk61Identity $probeSerial 200 8) 'MK61s serial probe failed'
    Assert-True (($probeSerial.Writes -join '') -eq "identity`rver`r") 'MK61s serial probe did not send identity/ver'
    Assert-True ($probeSerial.ReadTimeout -eq 777) 'MK61s serial probe did not restore timeout'
    $probeSerial.Lines.Clear()
    $probeSerial.Writes.Clear()
    $probeSerial.NextLine = 'another STM32 firmware'
    Assert-True (-not (Test-DirectSerialMk61Identity $probeSerial 200 4)) 'unrelated serial firmware passed the probe'

    $delayedProbe = [pscustomobject]@{
        ReadTimeout = 777
        Identity = $identityLine
        Writes = [Collections.Generic.List[string]]::new()
    }
    $delayedProbe | Add-Member -MemberType ScriptMethod -Name Write -Value {
        param([string]$Text)
        $this.Writes.Add($Text)
    }
    $delayedProbe | Add-Member -MemberType ScriptMethod -Name ReadLine -Value {
        if ($this.Writes.Count -lt 2) {
            [Threading.Thread]::Sleep(30)
            return 'booting'
        }
        return $this.Identity
    }
    $delayedIdentity = Get-DirectSerialMk61Identity $delayedProbe 500 24 40
    Assert-True ($null -ne $delayedIdentity) `
        'MK61s serial probe did not survive delayed firmware readiness'
    Assert-True ($delayedProbe.Writes.Count -ge 2) `
        'MK61s serial probe did not repeat identity while waiting'
    Assert-True ($delayedProbe.ReadTimeout -eq 777) `
        'delayed MK61s serial probe did not restore timeout'

    & {
        function Get-CdcPorts { return @('COM12','COM16') }
        function Start-Sleep { param([int]$Milliseconds) }
        $script:selectionTestIdentity = 'MK61s-Classic-V3 ver. Aug 02 2026(12:34:56)'
        function New-ConfiguredSerialPort {
            param([string]$PortName)
            $identity = if ($PortName -eq 'COM16') {
                $script:selectionTestIdentity
            } else {
                'unrelated STM32 firmware'
            }
            $serial = [pscustomobject]@{
                PortName = $PortName
                IsOpen = $false
                ReadTimeout = 777
                Identity = $identity
                Disposed = $false
                Writes = [Collections.Generic.List[string]]::new()
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Open -Value {
                $this.IsOpen = $true
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Close -Value {
                $this.IsOpen = $false
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Dispose -Value {
                $this.Disposed = $true
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Write -Value {
                param([string]$Text)
                $this.Writes.Add($Text)
            }
            $serial | Add-Member -MemberType ScriptMethod -Name ReadLine -Value {
                return $this.Identity
            }
            return $serial
        }

        $oldPort = $script:Port
        $oldPortExplicit = $script:PortExplicit
        $oldDirectSerial = $script:DirectSerial
        $oldStatusText = $script:StatusText
        $oldDeviceSelector = $script:DeviceSelector
        $oldDeviceExplicit = $script:DeviceSelectorExplicit
        $oldConfigFile = $script:ConfigFile
        try {
            $script:Port = 'COM12'
            $script:PortExplicit = $false
            $script:DirectSerial = $null
            Assert-True (Start-DirectSerial) 'automatic COM probing did not find MK61s'
            Assert-True ($script:Port -eq 'COM16') 'automatic COM probing stayed on unrelated COM12'
            Assert-True ($script:DirectSerial.PortName -eq 'COM16') 'automatic COM probing retained the wrong serial object'
            $script:DeviceSelector = 'DEADBEEF'
            $script:DeviceSelectorExplicit = $false
            Assert-True (Start-DirectSerial) 'stale preference rejected the sole legacy MK61s'
            Assert-True ([string]::IsNullOrEmpty($script:DeviceSelector)) 'legacy fallback retained the stale ID'
            $script:selectionTestIdentity = $identityLine
            $script:DeviceSelector = 'DEADBEEF'
            Assert-True (Start-DirectSerial) 'stale preference rejected the sole modern MK61s'
            Assert-True ($script:DetectedDeviceId -eq '0123456789ABCDEF' -and
                $script:DeviceSelector -eq '0123456789ABCDEF') 'fallback did not retain the chosen ID'
            $script:ConfigFile = Join-Path $tempRoot 'device-selection.conf'
            Save-Config
            Assert-True ([IO.File]::ReadAllText($script:ConfigFile) -match
                'DEVICE_ID=0123456789ABCDEF') 'fallback did not save the new ID'
            $script:DeviceSelector = 'DEADBEEF'
            $script:DeviceSelectorExplicit = $true
            Assert-True (-not (Start-DirectSerial)) 'explicit missing ID selected another calculator'
            Assert-True ($script:StatusText -match 'выбрал 0 устройств') 'explicit ID failure lost its diagnostic'
        } finally {
            Close-DirectSerialPort $script:DirectSerial
            $script:Port = $oldPort
            $script:PortExplicit = $oldPortExplicit
            $script:DirectSerial = $oldDirectSerial
            $script:StatusText = $oldStatusText
            $script:DeviceSelector = $oldDeviceSelector
            $script:DeviceSelectorExplicit = $oldDeviceExplicit
            $script:ConfigFile = $oldConfigFile
            Remove-Variable -Scope Script -Name selectionTestIdentity -ErrorAction SilentlyContinue
        }
    }

    & {
        $devices = @(
            [pscustomobject]@{ Port = 'COM1'; Identity = (ConvertFrom-Mk61IdentityLine `
                'MK61 ID v=1 public=1111111111111111 short=11111111 usb=AAAAAAAAAAAA volume=A1B2C3D4 build=12345678 profile=classic-v3-uc1609') },
            [pscustomobject]@{ Port = 'COM2'; Identity = (ConvertFrom-Mk61IdentityLine `
                'MK61 ID v=1 public=2222222222222222 short=22222222 usb=BBBBBBBBBBBB volume=A1B2C3D4 build=12345678 profile=mini-v3-a00') }
        )
        $saved = @{
            DeviceSelector = $script:DeviceSelector
            DeviceSelectorExplicit = $script:DeviceSelectorExplicit
            AllowDevicePrompt = $script:AllowDevicePrompt
            InstallSystemDir = $script:InstallSystemDir
            StatusText = $script:StatusText
        }
        $script:selectionInputs = [Collections.Generic.Queue[string]]::new()
        function Read-Host {
            param([string]$Prompt)
            if ($script:selectionInputs.Count -eq 0) { return $null }
            return $script:selectionInputs.Dequeue()
        }
        try {
            $script:DeviceSelectorExplicit = $false
            $script:AllowDevicePrompt = $true
            $script:InstallSystemDir = ''
            $script:DeviceSelector = '11111111'
            $chosen = Select-Mk61Device $devices
            Assert-True ($chosen.Port -eq 'COM1') 'present saved preference did not select its device'

            $script:DeviceSelector = 'DEADBEEF'
            foreach ($answer in @('invalid','99','999999999999999999999999999999','02')) {
                $script:selectionInputs.Enqueue($answer)
            }
            $chosen = Select-Mk61Device $devices
            Assert-True ($chosen.Port -eq 'COM2') 'multiple devices did not honor the numbered choice'
            Assert-True ($script:selectionInputs.Count -eq 0) 'invalid choices were not retried'

            $script:DeviceSelector = ''
            $script:selectionInputs.Enqueue('1')
            $chosen = Select-Mk61Device $devices
            Assert-True ($chosen.Port -eq 'COM1') 'first run with multiple devices did not offer a choice'

            $script:DeviceSelector = 'DEADBEEF'
            $script:DeviceSelectorExplicit = $true
            $script:selectionInputs.Enqueue('2')
            Assert-True ($null -eq (Select-Mk61Device $devices)) 'explicit missing selector offered fallback'
            Assert-True ($script:selectionInputs.Count -eq 1) 'explicit missing selector consumed input'
            $script:selectionInputs.Clear()
            $script:DeviceSelectorExplicit = $false

            $script:selectionInputs.Enqueue('0')
            Assert-True ($null -eq (Select-Mk61Device $devices)) 'cancel selected a device'
            Assert-True ($script:StatusText -eq 'выбор калькулятора отменён') 'cancel diagnostic missing'
            Assert-True ($null -eq (Select-Mk61Device $devices)) 'EOF selected a device'
            Assert-True ($script:StatusText -eq 'выбор калькулятора отменён') 'EOF diagnostic missing'

            $script:AllowDevicePrompt = $false
            Assert-True ($null -eq (Select-Mk61Device $devices)) 'noninteractive selection chose an arbitrary device'
            Assert-True ($script:StatusText -match 'несколько MK61s') 'ambiguity diagnostic missing'
            $script:AllowDevicePrompt = $true
            $script:InstallSystemDir = $local
            $script:selectionInputs.Enqueue('2')
            Assert-True ($null -eq (Select-Mk61Device $devices)) 'batch install offered a numbered choice'
            Assert-True ($script:selectionInputs.Count -eq 1) 'batch install consumed input'
        } finally {
            foreach ($name in $saved.Keys) { Set-Variable -Scope Script -Name $name -Value $saved[$name] }
            Remove-Variable -Scope Script -Name selectionInputs -ErrorAction SilentlyContinue
        }
    }

    & {
        function Get-CdcPorts { return @() }
        function Start-Sleep { param([int]$Milliseconds) }
        $script:readyProbeCreated = 0
        function New-ConfiguredSerialPort {
            param([string]$PortName)
            $script:readyProbeCreated++
            $identity = if ($script:readyProbeCreated -ge 2) {
                'MK61s-Classic-V2 ver. Aug 02 2026(12:34:56)'
            } else { 'booting' }
            $serial = [pscustomobject]@{
                PortName = $PortName
                IsOpen = $false
                ReadTimeout = 777
                Identity = $identity
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Open -Value {
                $this.IsOpen = $true
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Close -Value {
                $this.IsOpen = $false
            }
            $serial | Add-Member -MemberType ScriptMethod -Name Dispose -Value {}
            $serial | Add-Member -MemberType ScriptMethod -Name Write -Value {
                param([string]$Text)
            }
            $serial | Add-Member -MemberType ScriptMethod -Name ReadLine -Value {
                return $this.Identity
            }
            return $serial
        }

        $oldPort = $script:Port
        $oldPortExplicit = $script:PortExplicit
        $oldReadyWaitSeconds = $script:ReadyWaitSeconds
        $oldDirectSerial = $script:DirectSerial
        $oldStatusText = $script:StatusText
        try {
            $script:Port = 'COM5'
            $script:PortExplicit = $true
            $script:ReadyWaitSeconds = 1
            $script:DirectSerial = $null
            Assert-True (Start-DirectSerial) `
                'readiness wait did not retry a booting explicit COM port'
            Assert-True ($script:readyProbeCreated -ge 3) `
                'readiness wait did not reopen COM after a failed identity probe'
            Assert-True ($script:DirectSerial.PortName -eq 'COM5') `
                'readiness wait retained the wrong COM port'
        } finally {
            Close-DirectSerialPort $script:DirectSerial
            $script:Port = $oldPort
            $script:PortExplicit = $oldPortExplicit
            $script:ReadyWaitSeconds = $oldReadyWaitSeconds
            $script:DirectSerial = $oldDirectSerial
            $script:StatusText = $oldStatusText
            Remove-Variable -Scope Script -Name readyProbeCreated `
                -ErrorAction SilentlyContinue
        }
    }

    $oldPort = $script:Port
    $oldPortExplicit = $script:PortExplicit
    $oldReadyWaitSeconds = $script:ReadyWaitSeconds
    try {
        $script:Port = 'COM12'
        $script:PortExplicit = $false
        Assert-True (Parse-Arguments @('--port','COM99')) '--port parsing failed'
        Assert-True ($script:Port -eq 'COM99' -and $script:PortExplicit) '--port was not marked explicit'
        Assert-True (Parse-Arguments @('--device','89ABCDEF')) '--device parsing failed'
        Assert-True ($script:DeviceSelector -eq '89ABCDEF' -and
            $script:DeviceSelectorExplicit) '--device was not marked explicit'
        Assert-True (Parse-Arguments @('--wait-ready','45')) `
            '--wait-ready parsing failed'
        Assert-True ($script:ReadyWaitSeconds -eq 45) `
            '--wait-ready value was not retained'
        $invalidReadyWait = $false
        try { [void](Parse-Arguments @('--wait-ready','121')) }
        catch { $invalidReadyWait = $true }
        Assert-True $invalidReadyWait '--wait-ready accepted an unsafe timeout'
    } finally {
        $script:Port = $oldPort
        $script:PortExplicit = $oldPortExplicit
        $script:ReadyWaitSeconds = $oldReadyWaitSeconds
    }
    $crc = Get-PosixChecksumBytes ([Text.Encoding]::ASCII.GetBytes('123456789'))
    Assert-True ($crc -eq 930766865) 'POSIX cksum implementation differs'
    $busyText = Get-SerialOpenFailureText ([UnauthorizedAccessException]::new('denied'))
    Assert-True ($busyText -match 'все программы' -and
        $busyText -notmatch 'TeraTerm|Serial Monitor') 'busy COM message names individual programs'

    $script:MockRoot = $device
    $script:SessionDir = $session
    $script:LocalPath = $local

    # Windows cloud-sync clients mark placeholders as ReparsePoint without
    # making them links.  They must stay navigable; true links remain blocked.
    $cloudDirectory = [pscustomobject]@{
        Attributes = ([IO.FileAttributes]::Directory -bor
            [IO.FileAttributes]::ReparsePoint)
        PSIsContainer = $true
        LinkType = $null
    }
    Assert-True ((Get-LocalItemKind $cloudDirectory) -eq 'd') `
        'PowerShell panel treated a cloud placeholder directory as a link'
    $linkedDirectory = [pscustomobject]@{
        Attributes = ([IO.FileAttributes]::Directory -bor
            [IO.FileAttributes]::ReparsePoint)
        PSIsContainer = $true
        LinkType = 'SymbolicLink'
    }
    Assert-True ((Get-LocalItemKind $linkedDirectory) -eq 'l') `
        'PowerShell panel accepted a symbolic-link directory as ordinary'

    # Enter on `..` and Backspace both restore the directory being left.
    # A hidden directory matches the original Windows regression.
    & {
        function Save-Config {}
        function Draw-Screen {}
        $script:LocalPath = $navigation
        $script:ActivePanel = 'L'
        $script:Panels.L.Entries = @()
        $script:Panels.L.Selected = 0
        Load-LocalPanel
        $navigationIndex = -1
        for ($index = 0; $index -lt $script:Panels.L.Entries.Count; $index++) {
            if ($script:Panels.L.Entries[$index].Name -eq '.mkc') {
                $navigationIndex = $index
                break
            }
        }
        Assert-True ($navigationIndex -ge 0) 'PowerShell panel omitted a hidden directory'
        $script:Panels.L.Selected = $navigationIndex
        Open-SelectedEntry
        Assert-True ($script:LocalPath -eq (Join-Path $navigation '.mkc')) 'PowerShell panel did not enter .mkc'
        Assert-True ((Get-SelectedEntry 'L').Name -eq '..') 'PowerShell child panel did not start on ..'
        Open-SelectedEntry
        Assert-True ($script:LocalPath -eq $navigation) 'PowerShell panel did not return to the parent'
        Assert-True ((Get-SelectedEntry 'L').Name -eq '.mkc') 'PowerShell panel did not restore .mkc after Enter on ..'
        Open-SelectedEntry
        Open-ParentDirectory
        Assert-True ($script:LocalPath -eq $navigation) 'PowerShell Backspace did not return to the parent'
        Assert-True ((Get-SelectedEntry 'L').Name -eq '.mkc') 'PowerShell panel did not restore .mkc after Backspace'
    }
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
    $script:EditorLines = [Collections.Generic.List[string]]::new()
    $script:EditorLines.Add(('x' * 2000))
    $script:EditorName = 'edit.tbi'
    $script:EditorRemoteTarget = '/edit.tbi'
    Assert-True (Save-Editor) 'PowerShell editor rejected expanded TinyBASIC source'
    Assert-True ((Get-Item (Join-Path $device 'edit.tbi')).Length -gt 1536) 'PowerShell editor truncated expanded TinyBASIC source'
    $script:EditorLines = [Collections.Generic.List[string]]::new()
    $script:EditorLines.Add(('x' * 65535))
    Assert-True (-not (Save-Editor)) 'PowerShell editor uploaded more than 65534 TinyBASIC bytes'
    Assert-True ($script:EditorError -match 'максимум MK61s — 65534') 'PowerShell TinyBASIC editor size error is unclear'
    Assert-True (-not (Initialize-EditorFromFile (Join-Path $tempRoot 'editor/control.txt') 'control.txt')) 'PowerShell editor accepted terminal control bytes'
    Assert-True (-not (Initialize-EditorFromFile (Join-Path $tempRoot 'editor/printable.bin') 'printable.bin')) 'PowerShell editor accepted a BIN with printable bytes'
    Assert-True ($script:EditorError -eq 'Двоичные файлы доступны только для просмотра') 'PowerShell BIN editor error differs'

    Assert-True (Send-RemoteFile (Join-Path $local 'demo.foc') '/demo.foc') 'mock upload failed'
    Assert-True (Receive-RemoteFile '/demo.foc' (Join-Path $tempRoot 'download.foc')) 'mock download failed'
    Assert-True ([IO.File]::ReadAllText((Join-Path $tempRoot 'download.foc')) -eq "2+2`n") 'mock transfer changed bytes'
    Assert-True (Send-RemoteFile (Join-Path $local 'Игра.m61') '/Игра.m61') 'M8 mock upload failed'
    $m8Hex = Convert-BytesToHex ([IO.File]::ReadAllBytes((Join-Path $device 'Игра.m61')))
    Assert-True ($m8Hex -eq 'CFF0E8E2E5F2200F2016201F0A') 'PowerShell MKC did not encode UTF-8 text as M8'
    Assert-True (Receive-RemoteFile '/Игра.m61' (Join-Path $tempRoot 'download-russian.m61')) 'M8 mock download failed'
    Assert-True ([IO.File]::ReadAllText((Join-Path $tempRoot 'download-russian.m61')) -eq "Привет → ≤ ↵`n") 'PowerShell MKC did not decode M8 as UTF-8'
    Assert-True (New-RemoteDirectory '/System') 'mock System mkdir failed'
    Assert-True (Send-RemoteFile (Join-Path $local 'FOCAL.APP') '/System/FOCAL.APP') 'mock system APP upload failed'
    Assert-True (Receive-RemoteFile '/System/FOCAL.APP' (Join-Path $tempRoot 'download.app')) 'mock system APP download failed'
    Assert-True ([IO.File]::ReadAllBytes((Join-Path $tempRoot 'download.app')).Length -eq 64) 'mock APP transfer changed bytes'
    Assert-True (Send-RemoteFile (Join-Path $local 'CalculatorProgram/program.bin') '/program.bin') 'mock BIN upload failed'
    Assert-True ((Convert-BytesToHex ([IO.File]::ReadAllBytes((Join-Path $device 'program.bin')))) -eq '00017F80FF0D0A') 'BIN upload applied text conversion'
    Assert-True (Receive-RemoteFile '/program.bin' (Join-Path $tempRoot 'download.bin')) 'mock BIN download failed'
    Assert-True ((Convert-BytesToHex ([IO.File]::ReadAllBytes((Join-Path $tempRoot 'download.bin')))) -eq '00017F80FF0D0A') 'BIN round-trip changed bytes'
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
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'CalculatorProgram') '/CalculatorProgram') 'calculator BIN package failed recursive preflight'
    Assert-True ($script:CopyPlan.Count -eq 3 -and $script:CopyTotal -eq 33) 'calculator BIN copy plan differs'
    Reset-CopyPlan
    Assert-True (-not (Add-LocalTreeToPlan $local '/Imported')) 'unsupported subtree passed preflight'
    Assert-True (-not [string]::IsNullOrEmpty($script:PlanError)) 'preflight did not report the bad file'
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'FOCAL.APP') '/System/FOCAL.APP') 'system APP upload was rejected'
    $manualSystem = Join-Path $local 'System'
    [void](New-Item -ItemType Directory -Path $manualSystem)
    [IO.File]::WriteAllBytes((Join-Path $manualSystem 'BASIC.APP'), [byte[]]::new(64))
    [IO.File]::WriteAllBytes((Join-Path $manualSystem 'USBDISK.APP'), [byte[]]::new(64))
    [IO.File]::WriteAllBytes((Join-Path $manualSystem 'SRCEDIT.APP'), [byte[]]::new(64))
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan $manualSystem '/System') 'complete System directory was rejected'
    Assert-True ($script:CopyPlan.Count -eq 4 -and
        $script:CopyPlan[1].Destination -eq '/System/USBDISK.APP') `
        'manual System copy does not install USBDISK.APP first'
    Remove-Item -LiteralPath (Join-Path $manualSystem 'USBDISK.APP')
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan $manualSystem '/System') `
        'resident-USB F411 System directory was rejected'
    Assert-True ($script:CopyPlan.Count -eq 3 -and
        $script:CopyPlan[1].Destination -eq '/System/BASIC.APP') `
        'resident-USB F411 System copy plan differs'
    Assert-True ([string]::IsNullOrEmpty($script:PlanError)) `
        'resident-USB F411 System copy reported a false error'
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'DEMO.APP') '/Applications/DEMO.APP') 'APP upload outside root was rejected'
    Reset-CopyPlan
    Assert-True (Add-LocalTreeToPlan (Join-Path $local 'game.ch8') '/Games/game.ch8') 'CHIP-8 upload was rejected'
    Assert-True ($script:CopyPlan.Count -eq 1 -and $script:CopyTotal -eq 4) 'CHIP-8 copy plan differs'

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
            $fakeSerial.Lines.Enqueue('/> ls "/"' + "`r")
            $fakeSerial.Lines.Enqueue("f`t4 B`tsecond.m61`r")
            $fakeSerial.Lines.Enqueue("2 entries.`r")
            $fakeSerial.Lines.Enqueue('/> ls "/"' + "`r")
            $fakeSerial.Lines.Enqueue("f`t3 B`tfirst.m61`r")
            $fakeSerial.Lines.Enqueue("f`t4 B`tsecond.m61`r")
            $fakeSerial.Lines.Enqueue("2 entries.`r")
            $script:MockRoot = ''
            $retriedEntries = @(Get-RemoteEntries '/')
            Assert-True ($retriedEntries.Count -eq 2) 'incomplete COM listing was accepted'
            Assert-True ($retriedEntries[0].Name -eq 'first.m61') 'listing retry still lost its first entry'
            Assert-True (@($fakeSerial.Writes | Where-Object { $_ -eq "ls `"/`"`r" }).Count -eq 2) 'incomplete COM listing was not retried'

            $fakeSerial.Writes.Clear()
            $fakeSerial.Lines.Enqueue('/> ls "/"' + "`r")
            $fakeSerial.Lines.Enqueue("d`tlibrary/`r")
            $fakeSerial.Lines.Enqueue("d`tgames/`r")
            $fakeSerial.Lines.Enqueue("2 entries.`r")
            $fakeSerial.Lines.Enqueue('/games> ls "/games"' + "`r")
            $fakeSerial.Lines.Enqueue("d`tELITE/`r")
            $fakeSerial.Lines.Enqueue("d`tWumpus/`r")
            $fakeSerial.Lines.Enqueue("2 entries.`r")
            $sharedEntries = @(Get-RemoteEntries '/games')
            Assert-True ($sharedEntries.Count -eq 2) 'foreign COM listing replaced our directory'
            Assert-True ($sharedEntries[0].Name -eq 'ELITE' -and $sharedEntries[1].Name -eq 'Wumpus') `
                'foreign COM listing was mixed into our directory'
            Assert-True (@($fakeSerial.Writes | Where-Object { $_ -eq "ls `"/games`"`r" }).Count -eq 1) `
                'shared-stream listing issued an unexpected retry'

            $fakeSerial.Writes.Clear()
            $fakeSerial.Lines.Enqueue('/> help' + "`r")
            $fakeSerial.Lines.Enqueue("Foreign terminal output`r")
            $fakeSerial.Lines.Enqueue('/> ' + "`r")
            $fakeSerial.Lines.Enqueue('/games> df' + "`r")
            $fakeSerial.Lines.Enqueue("Flash: 16777216 bytes`r")
            $fakeSerial.Lines.Enqueue("Nodes: 9 used`r")
            $fakeSerial.Lines.Enqueue('/games> ' + "`r")
            $script:RemotePath = '/games'
            $capture = Invoke-RemoteCaptureCommand 'df'
            Assert-True ($capture.Success) 'shared-stream terminal command failed'
            Assert-True (($capture.Lines -join "`n") -eq "Flash: 16777216 bytes`nNodes: 9 used") `
                'foreign terminal output leaked into our command result'
            Assert-True ($script:RemoteCapturePath -eq '/games') 'foreign prompt changed the captured path'

            $fakeSerial.Writes.Clear()
            $fakeSerial.Lines.Enqueue('/> ls "/"' + "`r")
            $fakeSerial.Lines.Enqueue("d`tlibrary/`r")
            $fakeSerial.Lines.Enqueue("1 entry.`r")
            $fakeSerial.Lines.Enqueue('/> mkdir -p "/Denied"' + "`r")
            $fakeSerial.Lines.Enqueue("mkdir: denied`r")
            $fakeSerial.Lines.Enqueue('/> ls "/"' + "`r")
            $fakeSerial.Lines.Enqueue("d`tlibrary/`r")
            $fakeSerial.Lines.Enqueue("1 entry.`r")
            Assert-True (-not (Invoke-RemoteSimple 'mkdir -p "/Denied"')) `
                'stale foreign ls falsely confirmed a failed mutation'
            Assert-True ($script:StatusText -eq 'mkdir: denied') 'mutation error was replaced or lost'
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
