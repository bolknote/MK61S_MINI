#requires -Version 5.1
param([string]$ReportPath, [switch]$RequireWindowsPowerShell51)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$windows51 = $env:OS -eq 'Windows_NT' -and $PSVersionTable.PSEdition -eq 'Desktop' -and
    $PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1
if ($RequireWindowsPowerShell51 -and -not $windows51) {
    throw 'This qualification requires actual Windows PowerShell 5.1 on Windows'
}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'tools/.bbs/bridge.ps1')

function Assert-Bbs([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Hex([byte[]]$Bytes) { return [BitConverter]::ToString($Bytes).Replace('-', '').ToLowerInvariant() }
function Decode([byte[]]$Bytes) {
    $packets = [Collections.Generic.List[object]]::new()
    $receive = { param($kind, $session, $sequence, $offset, $data)
        $packets.Add(@{ Kind = $kind; Session = $session; Sequence = $sequence; Offset = $offset; Data = $data })
    }.GetNewClosure()
    $decoder = New-BbsDecoder $receive
    Add-BbsSerialBytes $decoder $Bytes
    return ,$packets
}
Assert-Bbs ((Hex (New-BbsFrame 1 1 1)) -ceq '0006425401010101010201010103fdaa00') 'Golden OPEN frame differs'
for ($n = 0; $n -le 32; $n++) {
    $payload = [byte[]]::new($n)
    for ($i = 0; $i -lt $n; $i++) { $payload[$i] = $i }
    $wire = New-BbsFrame 133 ([uint32]::MaxValue) 65535 251 $payload
    $packet = (Decode $wire)[0]
    Assert-Bbs ($packet.Kind -eq 133 -and $packet.Session -eq [uint32]::MaxValue -and
        $packet.Sequence -eq 65535 -and $packet.Offset -eq 251 -and
        (Hex $packet.Data) -ceq (Hex $payload)) 'Frame round trip failed'
    $wire[$wire.Length - 3] = $wire[$wire.Length - 3] -bxor 1
    Assert-Bbs ((Decode $wire).Count -eq 0) 'Bad CRC accepted'
}
$wire = New-BbsFrame 5 1 2 0 ([Text.Encoding]::ASCII.GetBytes("open NEVER.app`n"))
for ($cut = 1; $cut -lt $wire.Length - 3; $cut++) {
    $packets = Decode ([byte[]]($wire[0..($cut - 1)] + $wire))
    Assert-Bbs ($packets.Count -eq 1 -and $packets[0].Sequence -eq 2) 'Truncated frame recovery failed'
}
for ($value = 0; $value -lt 256; $value++) {
    $valid = Test-BbsM8Byte $value
    try { $text = ConvertFrom-BbsM8 ([byte[]]@($value)); Assert-Bbs $valid 'Invalid M8 accepted' }
    catch [Text.DecoderFallbackException] { Assert-Bbs (-not $valid) 'Valid M8 rejected'; continue }
    $encoded = ConvertTo-BbsM8 $text
    Assert-Bbs ($encoded.Length -eq 1 -and $encoded[0] -eq $value) 'M8 round trip differs'
}
$controls = [Collections.Generic.List[byte[]]]::new()
$editor = New-BbsVisitor { param([byte[]]$data) $controls.Add($data) }
Add-BbsVisitorBytes $editor ([byte[]](255,251,1,255,253,3,255,252,1,255,254,3))
Assert-Bbs ($controls.Count -eq 2 -and (Hex $controls[0]) -ceq 'fffe01' -and
    (Hex $controls[1]) -ceq 'fffc03') 'Telnet negotiation differs'
# Build Unicode from codepoints, so the suite also runs in Windows PowerShell 5.1 without a BOM.
$cyrillic = -join ([char[]](0x041E, 0x0442, 0x0432, 0x0435, 0x0442))
$utf8 = $script:BbsUtf8.GetBytes($cyrillic + "`r`n")
foreach ($value in $utf8) { Add-BbsVisitorBytes $editor ([byte[]]@($value)) }
Assert-Bbs ($editor.Lines.Dequeue().Text -ceq $cyrillic -and $editor.Lines.Count -eq 0) 'Fragmented UTF-8/CRLF failed'
Add-BbsVisitorBytes $editor ([byte[]](65,66,8,67,127,68,10))
Assert-Bbs ($editor.Lines.Dequeue().Text -ceq 'AD') 'Backspace failed'
foreach ($bad in @([byte[]](0xF0,0x9F,0x92,0xA3), [byte[]](0xC0,0xAF),
                   [byte[]](0xE0,0x80,0x80), [byte[]](0xD0), [byte[]](0x01))) {
    Add-BbsVisitorBytes $editor ([byte[]]($bad + 10))
    Assert-Bbs ($editor.Lines.Dequeue().Status -eq 9) 'Invalid UTF-8/M8 accepted'
}
Add-BbsVisitorBytes $editor ($script:BbsUtf8.GetBytes(('x' * 256) + "`n"))
Assert-Bbs ($editor.Lines.Dequeue().Status -eq 5) 'Line limit not enforced'
Add-BbsVisitorBytes $editor ([byte[]](255,250,1,2,255,240,65,10))
Assert-Bbs ($editor.Lines.Dequeue().Text -ceq 'A') 'Telnet subnegotiation leaked'

$state = @{ Serial = [Collections.Generic.List[byte[]]]::new(); Network = [Collections.Generic.List[byte[]]]::new()
    Drops = 0; Now = 0; Drained = $true }
$bridge = New-BbsBridge -Serial { param([byte[]]$data) $state.Serial.Add($data) } `
    -Network { param([byte[]]$data) $state.Network.Add($data) } `
    -Disconnect { $state.Drops++ } -Clock { $state.Now } -Drained { $state.Drained }
Receive-BbsFrame $bridge 1 123 1 0 ([byte[]]@())
Assert-Bbs ($state.Serial.Count -eq 0) 'OPEN acknowledged before visitor'
Connect-BbsVisitor $bridge
Assert-Bbs ((Decode $state.Serial[0])[0].Data[0] -eq 0) 'Pair failed'
$message = ConvertTo-BbsM8 ('Hello, ' + $cyrillic + '!')
Receive-BbsFrame $bridge 131 123 2 32768 ([byte[]]$message[0..3])
Assert-Bbs ($state.Network.Count -eq 0) 'Partial PRINT emitted'
Receive-BbsFrame $bridge 3 123 2 32772 ([byte[]]$message[4..($message.Length - 1)])
Receive-BbsFrame $bridge 3 123 2 32772 ([byte[]]$message[4..($message.Length - 1)])
Assert-Bbs ($state.Network.Count -eq 1 -and $script:BbsUtf8.GetString($state.Network[0]) -ceq
    ('Hello, ' + $cyrillic + "!`r`n")) 'PRINT assembly/dedup failed'
Add-BbsNetworkBytes $bridge ($script:BbsUtf8.GetBytes($cyrillic + "`r`nnext`n"))
Receive-BbsFrame $bridge 4 123 3 0 ([byte[]]@(80))
$answer = $state.Serial[$state.Serial.Count - 1]
Receive-BbsFrame $bridge 4 123 3 0 ([byte[]]@(80))
Assert-Bbs ((Hex $answer) -ceq (Hex $state.Serial[$state.Serial.Count - 1])) 'INPUT retry cache lost'
Assert-Bbs ((Hex (Decode $answer)[0].Data) -ceq (Hex (ConvertTo-BbsM8 $cyrillic))) 'INPUT data differs'
Receive-BbsFrame $bridge 9 123 999 0 ([byte[]]@())
Assert-Bbs ($null -ne $bridge.Pending) 'Wrong INPUT_ACK consumed answer'
Receive-BbsFrame $bridge 9 123 3 0 ([byte[]]@())
Receive-BbsFrame $bridge 4 123 4 0 ([byte[]]@(2))
Assert-Bbs ((Decode $state.Serial[$state.Serial.Count - 1])[0].Data[0] -eq 5) 'Capacity not enforced'
Receive-BbsFrame $bridge 9 123 4 0 ([byte[]]@())
Add-BbsNetworkBytes $bridge ($script:BbsUtf8.GetBytes("queued`npartial"))
$count = $state.Serial.Count
Receive-BbsFrame $bridge 6 123 5 0 ([byte[]]@())
Assert-Bbs ($state.Serial.Count -eq $count) 'CANCEL acknowledged before boundary'
Add-BbsNetworkBytes $bridge ($script:BbsUtf8.GetBytes(" stale suffix`nFresh`n"))
Assert-Bbs ((Decode $state.Serial[$state.Serial.Count - 1])[0].Sequence -eq 5) 'CANCEL boundary not acknowledged'
Receive-BbsFrame $bridge 4 123 6 0 ([byte[]]@(80))
Assert-Bbs ($script:BbsUtf8.GetString((Decode $state.Serial[$state.Serial.Count - 1])[0].Data) -ceq 'Fresh') 'CANCEL left stale input'
Receive-BbsFrame $bridge 9 123 6 0 ([byte[]]@())
Add-BbsNetworkBytes $bridge ($script:BbsUtf8.GetBytes(('z' * 80) + "`n"))
$count = $state.Serial.Count
Receive-BbsFrame $bridge 4 123 7 0 ([byte[]]@(80))
Assert-Bbs ($state.Serial.Count -eq $count + 3 -and (Decode $state.Serial[$count])[0].Kind -eq 133 -and
    (Decode $state.Serial[$count + 2])[0].Offset -eq 64) 'DATA fragmentation differs'
Receive-BbsFrame $bridge 7 999 8 0 ([byte[]]@())
Assert-Bbs ($bridge.Session -eq 123) 'Wrong session closed visitor'
$state.Drained = $false
Receive-BbsFrame $bridge 7 123 8 0 ([byte[]]@())
Assert-Bbs ($bridge.Session -eq 123) 'CLOSE discarded queued output'
$state.Drained = $true
Update-BbsBridge $bridge
Assert-Bbs ($bridge.Session -eq 0 -and $state.Drops -eq 1) 'Drained CLOSE failed'
Receive-BbsFrame $bridge 1 456 1 0 ([byte[]]@())
Receive-BbsFrame $bridge 8 456 0 0 ([byte[]]@())
Assert-Bbs ($null -eq $bridge.Offer) 'Unpaired ABORT failed'
Receive-BbsFrame $bridge 1 789 1 0 ([byte[]]@())
Connect-BbsVisitor $bridge
$state.Now = 3; Update-BbsBridge $bridge
Assert-Bbs ((Decode $state.Serial[$state.Serial.Count - 1])[0].Kind -eq 10) 'PING missing'
Receive-BbsFrame $bridge 11 789 0 0 ([byte[]]@())
$state.Now = 17; Update-BbsBridge $bridge
Assert-Bbs ($bridge.Session -eq 789) 'PONG did not renew lease'
$state.Now = 19; Update-BbsBridge $bridge
Assert-Bbs ($bridge.Session -eq 0) 'Expired lease retained visitor'
Connect-BbsVisitor $bridge
Add-BbsNetworkBytes $bridge ($script:BbsUtf8.GetBytes("a`nb`nc`nd`ne`n"))
Assert-Bbs ($null -eq $bridge.Visitor) 'Input queue overflow not bounded'

# Exercise the CLI under the actual current engine, including Windows PS 5.1.
# Separately check the public launcher's normal and Windows 5.1 fallback paths.
$launcher = Join-Path $root 'tools/bbs.cmd'
$launcherText = [IO.File]::ReadAllText($launcher)
Assert-Bbs ($launcherText.StartsWith(':; exec python3 "$(dirname "$0")/.bbs/bbs.py" "$@"')) 'Common launcher lost POSIX dispatch'
Assert-Bbs ($launcherText.Contains('%~dp0.bbs\bbs.ps1') -and $launcherText.Contains('powershell.exe')) 'Windows dispatch missing'
Assert-Bbs (-not [IO.File]::Exists((Join-Path $root 'tools/bbs_bridge.py')) -and
    -not [IO.File]::Exists((Join-Path $root 'tools/build_bbs_package.py'))) 'Extra public Python entry points remain'
$powershell = (Get-Process -Id $PID).Path
function Invoke-BbsTool([string[]]$Arguments) {
    & $powershell -NoLogo -NoProfile -File (Join-Path $root 'tools/.bbs/bbs.ps1') @Arguments
}
$fallbackTested = $false
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('bbs-tests-' + [guid]::NewGuid().ToString('N'))
try {
    $null = Invoke-BbsTool @('--help')
    Assert-Bbs ($LASTEXITCODE -eq 0) 'Help failed'
    $destination = Join-Path $temporary 'directory with spaces/bbs.zip'
    Invoke-BbsTool @('package', '--output', $destination)
    Assert-Bbs ($LASTEXITCODE -eq 0) 'Package failed'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($destination)
    try {
        Assert-Bbs ($zip.Entries.Count -eq 16) 'Package file count differs'
        foreach ($name in 'host/bbs.cmd', 'host/.bbs/bbs.py', 'host/.bbs/bbs.ps1', 'host/.bbs/bridge.ps1',
            'host/.bbs/m8_codec.py', 'C6/network/BBS/autoexec.m61', 'BBS.md', 'BASIC-TEXT.md') {
            Assert-Bbs ($null -ne $zip.GetEntry($name)) "Package missing $name"
        }
    } finally { $zip.Dispose() }
    $expanded = Join-Path $temporary 'expanded'
    [IO.Compression.ZipFile]::ExtractToDirectory($destination, $expanded)
    & $powershell -NoLogo -NoProfile -File (Join-Path $expanded 'host/.bbs/bbs.ps1') package --output (Join-Path $temporary 'again.zip')
    Assert-Bbs ($LASTEXITCODE -eq 0) 'Extracted package cannot repack itself'
    if ($env:OS -eq 'Windows_NT') {
        & $launcher package --output (Join-Path $temporary 'launcher.zip')
        Assert-Bbs ($LASTEXITCODE -eq 0) 'Public launcher failed'
        $originalPath = $env:PATH
        try {
            # Force the real batch fallback without Python or PowerShell 7 on PATH.
            $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
            & (Join-Path $expanded 'host/bbs.cmd') package --output (Join-Path $temporary 'fallback.zip')
            Assert-Bbs ($LASTEXITCODE -eq 0) 'Windows PowerShell 5.1 launcher fallback failed'
            $fallbackTested = $true
        } finally { $env:PATH = $originalPath }
    }
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
if ($ReportPath) {
    $hashes = [ordered]@{}
    foreach ($name in 'tools/bbs.cmd', 'tools/.bbs/bbs.ps1', 'tools/.bbs/bridge.ps1',
        'tools/.bbs/bbs.py', 'tools/m8_codec.py', 'tests/run_bbs_powershell_tests.ps1') {
        $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $root $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $receipt = [ordered]@{ schema = 1; status = 'PASS'; powershell = $powershell
        version = $PSVersionTable.PSVersion.ToString(); edition = $PSVersionTable.PSEdition
        platform = [Environment]::OSVersion.ToString(); windows_powershell_51 = $windows51
        native_cli_tested = $true; windows_launcher_fallback_tested = $fallbackTested
        serial_device_opened = $false; source_sha256 = $hashes
        github_run_id = $env:GITHUB_RUN_ID; github_sha = $env:GITHUB_SHA }
    $destination = [IO.Path]::GetFullPath($ReportPath)
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
    [IO.File]::WriteAllText($destination, ($receipt | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
}
Write-Output 'BBS PowerShell: protocol/M8/Telnet, retry, CANCEL, close/lease, launcher/package PASS'
