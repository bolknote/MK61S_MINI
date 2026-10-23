#requires -Version 5.1
# Native PowerShell implementation of BASIC TEXT/1. No external modules.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try { [Text.Encoding]::RegisterProvider([Text.CodePagesEncodingProvider]::Instance) } catch {}
$script:BbsCp1251 = [Text.Encoding]::GetEncoding(1251,
    [Text.EncoderFallback]::ExceptionFallback, [Text.DecoderFallback]::ExceptionFallback)
$script:BbsUtf8 = [Text.UTF8Encoding]::new($false, $true)
$script:BbsSpecial = [int[]](0x2190, 0x2192, 0x2191, 0x2193, 0x03C0, 0x221A,
    0x21BB, 0x2260, 0x2264, 0x2265, 0x00D7, 0x00F7, 0x00B2, 0x02B8, 0x02E3,
    0x22BB, 0x207B, 0x21B5)

function Test-BbsM8Byte([int]$Value) {
    return $Value -in 9, 10, 13 -or ($Value -ge 14 -and $Value -le 126) -or
        ($Value -ge 128 -and $Value -ne 152)
}

function ConvertTo-BbsM8([string]$Text) {
    $result = [Collections.Generic.List[byte]]::new()
    foreach ($character in $Text.ToCharArray()) {
        $special = [Array]::IndexOf($script:BbsSpecial, [int]$character)
        if ($special -ge 0) { $result.Add([byte](14 + $special)); continue }
        $encoded = $script:BbsCp1251.GetBytes([string]$character)
        if ($encoded.Length -ne 1 -or -not (Test-BbsM8Byte $encoded[0])) {
            throw [Text.EncoderFallbackException]::new('Character has no M8 assignment')
        }
        $result.Add($encoded[0])
    }
    return ,$result.ToArray()
}

function ConvertFrom-BbsM8([byte[]]$Bytes) {
    $result = [Text.StringBuilder]::new()
    foreach ($value in $Bytes) {
        if ($value -ge 14 -and $value -le 31) {
            [void]$result.Append([char]$script:BbsSpecial[$value - 14])
        } elseif (Test-BbsM8Byte $value) {
            [void]$result.Append($script:BbsCp1251.GetString([byte[]]@($value)))
        } else { throw [Text.DecoderFallbackException]::new('Byte has no M8 assignment') }
    }
    return $result.ToString()
}

function Get-BbsCrc([byte[]]$Bytes, [int]$Count = -1) {
    if ($Count -lt 0) { $Count = $Bytes.Length }
    $crc = 65535
    for ($i = 0; $i -lt $Count; $i++) {
        $crc = $crc -bxor ([int]$Bytes[$i] -shl 8)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if ($crc -band 32768) { $crc = ($crc -shl 1) -bxor 0x1021 }
            else { $crc = $crc -shl 1 }
            $crc = $crc -band 65535
        }
    }
    return $crc
}

function New-BbsFrame([int]$Kind, [uint32]$Session, [uint16]$Sequence,
                      [uint16]$Offset = 0, [byte[]]$Data = @()) {
    if ($Data.Length -gt 32) { throw 'Frame payload exceeds 32 bytes' }
    $raw = [Collections.Generic.List[byte]]::new()
    $raw.AddRange([byte[]](66, 84, 1, $Kind))
    foreach ($shift in 0, 8, 16, 24) { $raw.Add([byte](($Session -shr $shift) -band 255)) }
    foreach ($value in $Sequence, $Offset) {
        $raw.Add([byte]($value -band 255)); $raw.Add([byte]($value -shr 8))
    }
    $raw.AddRange($Data)
    $crc = Get-BbsCrc $raw.ToArray()
    $raw.Add([byte]($crc -band 255)); $raw.Add([byte]($crc -shr 8))
    $encoded = [Collections.Generic.List[byte]]::new()
    $encoded.Add(0); $encoded.Add(0)
    $code = 1; $run = 1
    foreach ($value in $raw) {
        if ($value) { $encoded.Add($value); $run++ }
        else { $encoded[$code] = [byte]$run; $code = $encoded.Count; $run = 1; $encoded.Add(0) }
    }
    $encoded[$code] = [byte]$run
    $encoded.Add(0)
    return ,$encoded.ToArray()
}

function New-BbsDecoder([scriptblock]$Receive) {
    return @{ Receive = $Receive; Packet = [Collections.Generic.List[byte]]::new()
        Active = $false; Bad = $false }
}

function Complete-BbsPacket($Decoder) {
    $raw = [Collections.Generic.List[byte]]::new()
    $packet = $Decoder.Packet
    $at = 0
    while ($at -lt $packet.Count) {
        $code = [int]$packet[$at]; $at++
        if (-not $code -or $at + $code - 1 -gt $packet.Count) { return }
        for ($i = 1; $i -lt $code; $i++) { $raw.Add($packet[$at]); $at++ }
        if ($code -ne 255 -and $at -lt $packet.Count) { $raw.Add(0) }
    }
    if ($raw.Count -lt 14 -or $raw.Count -gt 46 -or
        $raw[0] -ne 66 -or $raw[1] -ne 84 -or $raw[2] -ne 1) { return }
    $bytes = $raw.ToArray()
    $crc = [int]$bytes[$bytes.Length - 2] -bor ([int]$bytes[$bytes.Length - 1] -shl 8)
    if ((Get-BbsCrc $bytes ($bytes.Length - 2)) -ne $crc) { return }
    # Explicit little endian, independent of the host architecture.
    [uint32]$session = 0
    for ($i = 0; $i -lt 4; $i++) { $session = $session -bor ([uint32]$bytes[4 + $i] -shl (8 * $i)) }
    $sequence = [int]$bytes[8] -bor ([int]$bytes[9] -shl 8)
    $offset = [int]$bytes[10] -bor ([int]$bytes[11] -shl 8)
    $data = [byte[]]::new($bytes.Length - 14)
    [Array]::Copy($bytes, 12, $data, 0, $data.Length)
    & $Decoder.Receive ([int]$bytes[3]) $session $sequence $offset $data
}

function Add-BbsSerialBytes($Decoder, [byte[]]$Bytes) {
    foreach ($value in $Bytes) {
        if ($value -eq 0) {
            if ($Decoder.Active -and -not $Decoder.Bad) { Complete-BbsPacket $Decoder }
            $Decoder.Packet.Clear(); $Decoder.Active = $true; $Decoder.Bad = $false
        } elseif ($Decoder.Active) {
            if ($Decoder.Packet.Count -lt 48) { $Decoder.Packet.Add($value) }
            else { $Decoder.Bad = $true }
        }
    }
}

function New-BbsVisitor([scriptblock]$Control) {
    return @{ Control = $Control; Lines = [Collections.Generic.Queue[object]]::new()
        Partial = ''; Error = 0; Telnet = 0; Command = 0; Cr = $false; Discard = $false
        CancelDone = $null; Utf8 = [Collections.Generic.List[byte]]::new(); Needed = 0 }
}

function Add-BbsVisitorBytes($Visitor, [byte[]]$Bytes) {
    foreach ($value in $Bytes) {
        if ($Visitor.Telnet -eq 1) {
            if ($value -in 251, 252, 253, 254) { $Visitor.Command = $value; $Visitor.Telnet = 2 }
            elseif ($value -eq 250) { $Visitor.Telnet = 3 }
            else { $Visitor.Telnet = 0 }
            continue
        }
        if ($Visitor.Telnet -eq 2) {
            if ($Visitor.Command -in 251, 253) {
                $reply = if ($Visitor.Command -eq 251) { 254 } else { 252 }
                & $Visitor.Control ([byte[]](255, $reply, $value))
            }
            $Visitor.Telnet = 0; continue
        }
        if ($Visitor.Telnet -in 3, 4) {
            $Visitor.Telnet = if ($value -eq 255) { 4 }
                elseif ($Visitor.Telnet -eq 4 -and $value -eq 240) { 0 } else { 3 }
            continue
        }
        if ($value -eq 255) { $Visitor.Telnet = 1; continue }
        if ($value -in 10, 13) {
            if ($value -eq 10 -and $Visitor.Cr) { $Visitor.Cr = $false; continue }
            $Visitor.Cr = $value -eq 13
            if ($Visitor.Utf8.Count) { $Visitor.Error = 9 }
            if ($Visitor.Discard) {
                $Visitor.Discard = $false
                $done = $Visitor.CancelDone; $Visitor.CancelDone = $null
                if ($null -ne $done) { & $done }
            } else {
                if ($Visitor.Lines.Count -ge 4) { throw [InvalidOperationException]::new('Visitor input queue full') }
                $Visitor.Lines.Enqueue(@{ Status = $Visitor.Error; Text = $Visitor.Partial })
            }
            $Visitor.Partial = ''; $Visitor.Error = 0; $Visitor.Utf8.Clear(); $Visitor.Needed = 0
            continue
        }
        $Visitor.Cr = $false
        if ($Visitor.Discard) { continue }
        if ($value -in 8, 127) {
            if ($Visitor.Partial.Length) { $Visitor.Partial = $Visitor.Partial.Substring(0, $Visitor.Partial.Length - 1) }
            $Visitor.Utf8.Clear(); $Visitor.Needed = 0; continue
        }
        if ($Visitor.Error) { continue }
        if (-not $Visitor.Utf8.Count) {
            $Visitor.Needed = if ($value -lt 128) { 1 }
                elseif ($value -ge 194 -and $value -le 223) { 2 }
                elseif ($value -ge 224 -and $value -le 239) { 3 }
                elseif ($value -ge 240 -and $value -le 244) { 4 } else { 0 }
            if (-not $Visitor.Needed) { $Visitor.Error = 9; continue }
        } elseif ($value -lt 128 -or $value -gt 191) { $Visitor.Error = 9; continue }
        $Visitor.Utf8.Add($value)
        if ($Visitor.Utf8.Count -eq $Visitor.Needed) {
            try {
                $character = $script:BbsUtf8.GetString($Visitor.Utf8.ToArray())
                $null = ConvertTo-BbsM8 $character
                $Visitor.Partial += $character
                if ($Visitor.Partial.Length -gt 255) { $Visitor.Error = 5; $Visitor.Partial = '' }
            } catch [Text.DecoderFallbackException] { $Visitor.Error = 9 }
              catch [Text.EncoderFallbackException] { $Visitor.Error = 9 }
            $Visitor.Utf8.Clear(); $Visitor.Needed = 0
        }
    }
}

function Cancel-BbsVisitor($Visitor, [scriptblock]$Done) {
    $Visitor.Lines.Clear()
    $partial = $Visitor.Partial.Length -gt 0 -or $Visitor.Error -ne 0 -or $Visitor.Utf8.Count -gt 0
    $Visitor.Partial = ''; $Visitor.Error = 0; $Visitor.Utf8.Clear(); $Visitor.Needed = 0
    $Visitor.Discard = $partial
    if ($partial) { $Visitor.CancelDone = $Done } else { & $Done }
}

function New-BbsBridge([scriptblock]$Serial, [scriptblock]$Network, [scriptblock]$Disconnect,
                       [scriptblock]$Clock = { [Diagnostics.Stopwatch]::GetTimestamp() / [double][Diagnostics.Stopwatch]::Frequency },
                       [scriptblock]$Drained = { $true }) {
    return @{ Serial = $Serial; Network = $Network; Disconnect = $Disconnect; Clock = $Clock
        Drained = $Drained; Closing = $null; Visitor = $null; Session = [uint32]0; Offer = $null
        Pending = $null; Answer = $null; PrintSequence = $null; LastPrint = $null; LastCancel = $null
        PrintData = [Collections.Generic.List[byte]]::new(); LastSeen = (& $Clock); LastPing = (& $Clock) }
}

function Send-BbsFrame($Bridge, [int]$Kind, [int]$Sequence, [int]$Offset = 0, [byte[]]$Data = @()) {
    & $Bridge.Serial (New-BbsFrame $Kind $Bridge.Session $Sequence $Offset $Data)
}
function Send-BbsAck($Bridge, [int]$Sequence, [int]$Status = 0) {
    Send-BbsFrame $Bridge 2 $Sequence 0 ([byte[]]@($Status))
}
function Connect-BbsPair($Bridge) {
    if ($null -ne $Bridge.Visitor -and $null -ne $Bridge.Offer) {
        $Bridge.Session = $Bridge.Offer.Session; $sequence = $Bridge.Offer.Sequence; $Bridge.Offer = $null
        $Bridge.LastSeen = & $Bridge.Clock
        Send-BbsAck $Bridge $sequence
    }
}
function Connect-BbsVisitor($Bridge) {
    $Bridge.Visitor = New-BbsVisitor $Bridge.Network
    Connect-BbsPair $Bridge
}
function Reset-BbsBridge($Bridge) {
    $Bridge.Session = [uint32]0; $Bridge.Offer = $null; $Bridge.Pending = $null; $Bridge.Answer = $null
    $Bridge.PrintSequence = $null; $Bridge.LastPrint = $null; $Bridge.LastCancel = $null
    $Bridge.PrintData.Clear(); $Bridge.Closing = $null; $Bridge.Visitor = $null
    & $Bridge.Disconnect
}
function Disconnect-BbsBridge($Bridge) {
    if ($Bridge.Session) { Send-BbsFrame $Bridge 8 0 }
    Reset-BbsBridge $Bridge
}
function Send-BbsAnswer($Bridge) {
    if ($null -eq $Bridge.Pending -or $null -eq $Bridge.Visitor) { return }
    $sequence = $Bridge.Pending.Sequence
    if ($null -eq $Bridge.Answer) {
        if (-not $Bridge.Visitor.Lines.Count) { return }
        $line = $Bridge.Visitor.Lines.Dequeue()
        [byte[]]$payload = @()
        $status = $line.Status
        if (-not $status) { $payload = ConvertTo-BbsM8 $line.Text }
        if ($payload.Length -gt $Bridge.Pending.Capacity) { $status = 5; $payload = [byte[]]@() }
        $Bridge.Answer = @{ Status = $status; Payload = $payload }
    }
    if ($Bridge.Answer.Status) { Send-BbsAck $Bridge $sequence $Bridge.Answer.Status; return }
    $payload = $Bridge.Answer.Payload
    for ($at = 0; $at -lt [Math]::Max(1, $payload.Length); $at += 32) {
        $chunk = [byte[]]::new([Math]::Min(32, $payload.Length - $at))
        [Array]::Copy($payload, $at, $chunk, 0, $chunk.Length)
        $kind = if ($at + $chunk.Length -lt $payload.Length) { 133 } else { 5 }
        Send-BbsFrame $Bridge $kind $sequence $at $chunk
    }
}
function Add-BbsNetworkBytes($Bridge, [byte[]]$Bytes) {
    if ($null -eq $Bridge.Visitor) { return }
    try { Add-BbsVisitorBytes $Bridge.Visitor $Bytes; Send-BbsAnswer $Bridge }
    catch [InvalidOperationException] { Disconnect-BbsBridge $Bridge }
}
function Complete-BbsClose($Bridge) {
    if ($null -ne $Bridge.Closing -and (& $Bridge.Drained)) {
        Send-BbsAck $Bridge $Bridge.Closing
        Reset-BbsBridge $Bridge
    }
}
function Receive-BbsFrame($Bridge, [int]$Kind, [uint32]$Session, [int]$Sequence,
                         [int]$Offset, [byte[]]$Data) {
    if ($Kind -eq 1) {
        if ($Bridge.Session -eq $Session) { Send-BbsAck $Bridge $Sequence }
        elseif (-not $Bridge.Session) {
            $Bridge.Offer = @{ Session = $Session; Sequence = $Sequence }; Connect-BbsPair $Bridge
        }
        return
    }
    if ($Session -ne $Bridge.Session -or -not $Bridge.Session) {
        if ($Kind -eq 8 -and $null -ne $Bridge.Offer -and $Bridge.Offer.Session -eq $Session) {
            $Bridge.Offer = $null
        }
        return
    }
    $Bridge.LastSeen = & $Bridge.Clock
    if ($Kind -eq 11) { return }
    if ($Kind -eq 8) { Reset-BbsBridge $Bridge; return }
    if ($Kind -eq 7) { $Bridge.Closing = $Sequence; Complete-BbsClose $Bridge; return }
    if ($Kind -eq 9) {
        if ($null -ne $Bridge.Pending -and $Sequence -eq $Bridge.Pending.Sequence) {
            $Bridge.Pending = $null; $Bridge.Answer = $null
        }
        return
    }
    if ($Kind -eq 4 -and $Data.Length -eq 1) {
        $Bridge.LastPrint = $null; $Bridge.LastCancel = $null
        if ($null -eq $Bridge.Pending -or $Bridge.Pending.Sequence -ne $Sequence) {
            $Bridge.Pending = @{ Sequence = $Sequence; Capacity = $Data[0] }; $Bridge.Answer = $null
        }
        Send-BbsAnswer $Bridge; return
    }
    if ($Kind -eq 6) {
        $Bridge.LastPrint = $null
        if ($null -ne $Bridge.LastCancel -and $Sequence -eq $Bridge.LastCancel) {
            Send-BbsAck $Bridge $Sequence; return
        }
        $Bridge.Pending = $null; $Bridge.Answer = $null
        $done = { $Bridge.LastCancel = $Sequence; Send-BbsAck $Bridge $Sequence }.GetNewClosure()
        Cancel-BbsVisitor $Bridge.Visitor $done
        return
    }
    if (($Kind -band 127) -ne 3) { return }
    $Bridge.LastCancel = $null
    if ($null -ne $Bridge.LastPrint -and $Sequence -eq $Bridge.LastPrint) {
        if (-not ($Kind -band 128)) { Send-BbsAck $Bridge $Sequence }
        return
    }
    $newline = ($Offset -band 32768) -ne 0; $at = $Offset -band 32767
    if ($at -eq 0) { $Bridge.PrintSequence = $Sequence; $Bridge.PrintData.Clear() }
    if ($null -eq $Bridge.PrintSequence -or $Sequence -ne $Bridge.PrintSequence -or
        $at -ne $Bridge.PrintData.Count) { return }
    if ($Bridge.PrintData.Count + $Data.Length -gt 255) { Send-BbsAck $Bridge $Sequence 5; return }
    $Bridge.PrintData.AddRange($Data)
    if (-not ($Kind -band 128)) {
        try { $text = ConvertFrom-BbsM8 $Bridge.PrintData.ToArray() }
        catch [Text.DecoderFallbackException] { Send-BbsAck $Bridge $Sequence 9; return }
        if ($newline) { $text += "`n" }
        # Valid UTF-8 never contains FF, so Telnet IAC escaping is unnecessary.
        & $Bridge.Network ($script:BbsUtf8.GetBytes($text.Replace("`n", "`r`n")))
        $Bridge.LastPrint = $Sequence
        Send-BbsAck $Bridge $Sequence
    }
}
function Update-BbsBridge($Bridge) {
    Complete-BbsClose $Bridge
    $now = & $Bridge.Clock
    if ($Bridge.Session) {
        if ($now - $Bridge.LastSeen -gt 15) { Reset-BbsBridge $Bridge }
        elseif ($now - $Bridge.LastPing -gt 2) { $Bridge.LastPing = $now; Send-BbsFrame $Bridge 10 0 }
    }
}

function Add-BbsOutput($Queue, [byte[]]$Bytes) {
    if ($Queue.Count + $Bytes.Length -gt 4096) { throw [IO.IOException]::new('BBS output queue full') }
    $Queue.AddRange($Bytes)
}

function Start-BbsServer([string]$Port, [string]$BindHost, [int]$ListenPort, [bool]$DtrEnable = $true) {
    $addresses = @([Net.Dns]::GetHostAddresses($BindHost) | Where-Object {
        $_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork })
    if (-not $addresses.Count) { throw 'No IPv4 address for --host' }
    $listener = [Net.Sockets.TcpListener]::new($addresses[0], $ListenPort)
    $serial = [IO.Ports.SerialPort]::new($Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.DtrEnable = $DtrEnable; $serial.RtsEnable = $false
    $serial.ReadTimeout = 100; $serial.WriteTimeout = 200
    $transport = @{ Visitor = $null; Serial = [Collections.Generic.List[byte]]::new()
        Network = [Collections.Generic.List[byte]]::new() }
    $disconnect = {
        if ($null -ne $transport.Visitor) { $transport.Visitor.Dispose(); $transport.Visitor = $null }
        $transport.Network.Clear()
    }.GetNewClosure()
    $sendSerial = { param([byte[]]$Bytes) Add-BbsOutput $transport.Serial $Bytes }.GetNewClosure()
    $sendNetwork = { param([byte[]]$Bytes) Add-BbsOutput $transport.Network $Bytes }.GetNewClosure()
    $drained = { $transport.Network.Count -eq 0 }.GetNewClosure()
    $bridge = New-BbsBridge -Serial $sendSerial -Network $sendNetwork -Disconnect $disconnect -Drained $drained
    $receive = { param($kind, $session, $sequence, $offset, $data)
        Receive-BbsFrame $bridge $kind $session $sequence $offset $data }.GetNewClosure()
    $decoder = New-BbsDecoder $receive
    $buffer = [byte[]]::new(1024)
    try {
        # Bind first, so a busy TCP port never changes the CDC device.
        $listener.Start(1)
        $serial.Open()
        [Console]::Error.WriteLine('BBS bridge: {0} -> {1}:{2}', $Port, $BindHost, $listener.LocalEndpoint.Port)
        while ($true) {
            if ($listener.Pending()) {
                $client = $listener.AcceptSocket()
                if ($null -ne $transport.Visitor) {
                    try { $client.SendTimeout = 100; [void]$client.Send([Text.Encoding]::ASCII.GetBytes("BBS busy`r`n")) }
                    finally { $client.Dispose() }
                } else {
                    $client.Blocking = $false; $client.NoDelay = $true
                    $transport.Visitor = $client
                    Connect-BbsVisitor $bridge
                }
            }
            # Service visitor bytes before acknowledging a USB CANCEL.
            if ($null -ne $transport.Visitor) {
                try {
                    $client = $transport.Visitor
                    if ($transport.Network.Count -and $client.Poll(0, [Net.Sockets.SelectMode]::SelectWrite)) {
                        $sent = $client.Send($transport.Network.ToArray())
                        $transport.Network.RemoveRange(0, $sent)
                    }
                    if ($client.Poll(0, [Net.Sockets.SelectMode]::SelectRead)) {
                        $count = $client.Receive($buffer)
                        if ($count) {
                            $bytes = [byte[]]::new($count); [Array]::Copy($buffer, $bytes, $count)
                            Add-BbsNetworkBytes $bridge $bytes
                        } else { Disconnect-BbsBridge $bridge }
                    }
                } catch [Net.Sockets.SocketException] {
                    if ($_.Exception.SocketErrorCode -ne [Net.Sockets.SocketError]::WouldBlock) {
                        Disconnect-BbsBridge $bridge
                    }
                }
            }
            if ($transport.Serial.Count) {
                $bytes = $transport.Serial.ToArray()
                $serial.Write($bytes, 0, $bytes.Length)
                $transport.Serial.Clear()
            }
            $available = $serial.BytesToRead
            if ($available) {
                $count = $serial.Read($buffer, 0, [Math]::Min($available, $buffer.Length))
                $bytes = [byte[]]::new($count); [Array]::Copy($buffer, $bytes, $count)
                Add-BbsSerialBytes $decoder $bytes
            }
            Update-BbsBridge $bridge
            Start-Sleep -Milliseconds 10
        }
    } finally {
        try {
            Disconnect-BbsBridge $bridge
            if ($serial.IsOpen -and $transport.Serial.Count) {
                $bytes = $transport.Serial.ToArray(); $serial.Write($bytes, 0, $bytes.Length)
            }
        } catch {} finally {
            & $disconnect
            $serial.Dispose()
            $listener.Stop()
        }
    }
}
