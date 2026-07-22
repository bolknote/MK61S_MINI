#requires -Version 5.1

<#
  MKC — two-panel Norton Commander-style file manager for MK61s.
  Windows port. Uses System.Console and System.IO.Ports; no modules or
  arduino-cli are required on Windows.
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:Escape = [char]27
try {
    [Console]::InputEncoding = [Text.Encoding]::UTF8
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    $OutputEncoding = [Text.Encoding]::UTF8
} catch {}

function Get-EnvironmentOrDefault {
    param([string]$Name, [string]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

$script:ScriptDir = $PSScriptRoot
$script:ProjectRoot = (Resolve-Path (Join-Path $script:ScriptDir '../..')).Path
$script:ArduinoCli = Get-EnvironmentOrDefault 'MKC_ARDUINO_CLI' (
    Get-EnvironmentOrDefault 'MK61_ARDUINO_CLI' 'arduino-cli')
$script:ConfigFile = Get-EnvironmentOrDefault 'MKC_CONFIG_FILE' (Join-Path $script:ProjectRoot '.mkc.conf')
$script:IsWindowsHost = $env:OS -eq 'Windows_NT'
try {
    $script:IsWindowsHost = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [Runtime.InteropServices.OSPlatform]::Windows)
} catch {}

$script:Port = ''
$script:LocalPath = (Get-Location).Path
$script:RemotePath = '/'
$script:MockRoot = ''
$script:ClassifyOnly = ''
$script:ListPortsOnly = $false
$script:StatusText = ''
$script:SessionDir = ''
$script:Monitor = $null
$script:MonitorReadTask = $null
$script:MonitorErrorTask = $null
$script:DirectSerial = $null
$script:MarkerLine = ''
$script:SerialLine = ''
$script:FsPutChunkBytes = 48
$script:LastRemoteOutput = @()
$script:LastRemoteTitle = 'Терминал MK61s'
$script:RemoteCapturePath = '/'

$script:Panels = @{
    L = [pscustomobject]@{ Entries = @(); Selected = 0; Page = 0 }
    R = [pscustomobject]@{ Entries = @(); Selected = 0; Page = 0 }
}
$script:ActivePanel = 'L'
$script:CommandText = ''
$script:CommandCursor = 0
$script:CommandHistory = @()
$script:CommandHistoryIndex = -1
$script:CommandHistoryDraft = ''
$script:CopyPlan = @()
$script:CopyTotal = [long]0
$script:PlanError = ''

function Show-Usage {
    @'
MKC — Norton Commander for MK61s files

Usage:
  tools\mkc.cmd [--port COMx] [--local DIRECTORY]
  tools\mkc.cmd --mock DIRECTORY [--local DIRECTORY]
  tools\mkc.cmd --classify FILE

Keys:
  Tab       switch panel        Enter     open directory
  Space     mark item           F1        help
  F3        view                F5        copy
  F6        rename/move         F7        mkdir
  F8        delete              F9        device info
  F10       quit                Ctrl-R    refresh
  Ctrl-O    last MK61s output

The left command line runs through cmd.exe; the right one is sent to MK61s.
Loadable modules in the device root: FOCAL.MOD, BASIC.MOD, WBMP.MOD.
'@
}

function Parse-Arguments {
    param([object[]]$Arguments)
    for ($i = 0; $i -lt $Arguments.Count; $i++) {
        $arg = [string]$Arguments[$i]
        switch ($arg) {
            '--port' {
                if (++$i -ge $Arguments.Count) { throw '--port requires a value' }
                $script:Port = [string]$Arguments[$i]
            }
            '--local' {
                if (++$i -ge $Arguments.Count) { throw '--local requires a value' }
                $script:LocalPath = [string]$Arguments[$i]
            }
            '--mock' {
                if (++$i -ge $Arguments.Count) { throw '--mock requires a value' }
                $script:MockRoot = [string]$Arguments[$i]
            }
            '--classify' {
                if (++$i -ge $Arguments.Count) { throw '--classify requires a value' }
                $script:ClassifyOnly = [string]$Arguments[$i]
            }
            '--list-ports' { $script:ListPortsOnly = $true }
            { $_ -in @('-h','--help','/?') } { Show-Usage | Write-Host; return $false }
            default { throw "Unknown argument: $arg" }
        }
    }
    return $true
}

function Resolve-Executable {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($Command)) { return '' }
    if (Test-Path -LiteralPath $Command -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Command).Path
    }
    $found = Get-Command $Command -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $found) { return '' }
    return $found.Source
}

function Invoke-NativeCapture {
    param([string]$Executable, [string[]]$Arguments = @())
    $resolved = Resolve-Executable $Executable
    if ([string]::IsNullOrEmpty($resolved)) {
        return [pscustomobject]@{ ExitCode = 127; Output = "Executable not found: $Executable" }
    }
    try {
        $output = & $resolved @Arguments 2>&1 | Out-String
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = if ($?) { 0 } else { 1 } }
        return [pscustomobject]@{ ExitCode = [int]$code; Output = [string]$output }
    } catch {
        return [pscustomobject]@{ ExitCode = 1; Output = $_.Exception.Message }
    }
}

function Load-Config {
    if (-not (Test-Path -LiteralPath $script:ConfigFile -PathType Leaf)) { return }
    $savedLocal = ''
    foreach ($line in [IO.File]::ReadAllLines($script:ConfigFile)) {
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { continue }
        switch ($parts[0]) {
            'LOCAL_PATH' { $savedLocal = $parts[1] }
            'PORT' { if ([string]::IsNullOrEmpty($script:Port)) { $script:Port = $parts[1] } }
            'ARDUINO_CLI' {
                if ($script:ArduinoCli -eq 'arduino-cli' -and -not [string]::IsNullOrEmpty($parts[1])) {
                    $script:ArduinoCli = $parts[1]
                }
            }
        }
    }
    if ($script:LocalPath -eq (Get-Location).Path -and
        -not [string]::IsNullOrEmpty($savedLocal) -and
        (Test-Path -LiteralPath $savedLocal -PathType Container)) {
        $script:LocalPath = (Resolve-Path -LiteralPath $savedLocal).Path
    }
}

function Save-Config {
    if ($script:ConfigFile -eq '/dev/null') { return }
    $parent = Split-Path -Parent $script:ConfigFile
    if (-not [string]::IsNullOrEmpty($parent)) {
        [void](New-Item -ItemType Directory -Force -Path $parent)
    }
    $text = "# Создано tools/mkc.cmd.`nLOCAL_PATH=$($script:LocalPath)`nPORT=$($script:Port)`nARDUINO_CLI=$($script:ArduinoCli)`n"
    [IO.File]::WriteAllText($script:ConfigFile, $text, $script:Utf8NoBom)
}

function Normalize-UsbId {
    param([object]$Value)
    if ($null -eq $Value) { return '' }
    return ([string]$Value).Trim().ToLowerInvariant() -replace '^0x', ''
}

function Get-ObjectPropertyValue {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Get-CdcPortsFromJson {
    param([string]$Json)
    if ([string]::IsNullOrWhiteSpace($Json)) { return @() }
    try { $parsed = $Json | ConvertFrom-Json } catch { return @() }
    $ports = New-Object 'System.Collections.Generic.List[string]'
    foreach ($detected in @(Get-ObjectPropertyValue $parsed 'detected_ports')) {
        $port = Get-ObjectPropertyValue $detected 'port'
        if ($null -eq $port) { continue }
        $properties = Get-ObjectPropertyValue $port 'properties'
        if ((Normalize-UsbId (Get-ObjectPropertyValue $properties 'vid')) -eq '0483' -and
            (Normalize-UsbId (Get-ObjectPropertyValue $properties 'pid')) -eq '5740') {
            $address = [string](Get-ObjectPropertyValue $port 'address')
            if (-not [string]::IsNullOrWhiteSpace($address)) { $ports.Add($address) }
        }
    }
    return @($ports.ToArray() | Select-Object -Unique)
}

function Test-CdcHardwareId {
    param([string]$HardwareId)
    return $HardwareId -match '(?i)VID_0483&PID_5740'
}

function Get-CdcPortFromPnpDevice {
    param([object]$Device)
    $hardwareId = [string](Get-ObjectPropertyValue $Device 'InstanceId')
    if ([string]::IsNullOrEmpty($hardwareId)) {
        $hardwareId = [string](Get-ObjectPropertyValue $Device 'PNPDeviceID')
    }
    if (-not (Test-CdcHardwareId $hardwareId)) { return '' }
    $name = [string](Get-ObjectPropertyValue $Device 'FriendlyName')
    if ([string]::IsNullOrEmpty($name)) { $name = [string](Get-ObjectPropertyValue $Device 'Name') }
    $match = [regex]::Match($name, '\((COM\d+)\)')
    if ($match.Success) { return $match.Groups[1].Value }
    return ''
}

function Get-CdcPorts {
    $ports = New-Object 'System.Collections.Generic.List[string]'
    $cliPath = Resolve-Executable $script:ArduinoCli
    if (-not [string]::IsNullOrEmpty($cliPath)) {
        $cli = Invoke-NativeCapture $cliPath @('board','list','--format','json')
        if ($cli.ExitCode -eq 0) {
            foreach ($port in @(Get-CdcPortsFromJson $cli.Output)) { $ports.Add($port) }
        }
    }
    if ($script:IsWindowsHost) {
        $devices = @()
        if ($null -ne (Get-Command Get-PnpDevice -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
            try { $devices = @(Get-PnpDevice -PresentOnly -ErrorAction Stop) } catch {}
        }
        if ($devices.Count -eq 0 -and
            $null -ne (Get-Command Get-CimInstance -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
            try { $devices = @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop) } catch {}
        }
        if ($devices.Count -eq 0 -and
            $null -ne (Get-Command Get-WmiObject -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
            try { $devices = @(Get-WmiObject -Class Win32_PnPEntity -ErrorAction Stop) } catch {}
        }
        foreach ($item in $devices) {
            $port = Get-CdcPortFromPnpDevice $item
            if (-not [string]::IsNullOrEmpty($port)) { $ports.Add($port) }
        }
    }
    return @($ports.ToArray() | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique)
}

function Quote-NativeArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Test-UseDirectSerialTransport {
    return $script:IsWindowsHost
}

function New-ConfiguredSerialPort {
    param([string]$PortName)
    $serial = New-Object System.IO.Ports.SerialPort
    $serial.PortName = $PortName
    $serial.BaudRate = 115200
    $serial.DataBits = 8
    $serial.Parity = [IO.Ports.Parity]::None
    $serial.StopBits = [IO.Ports.StopBits]::One
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.DtrEnable = $true
    $serial.RtsEnable = $false
    $serial.NewLine = "`n"
    $serial.Encoding = $script:Utf8NoBom
    $serial.ReadTimeout = 8000
    $serial.WriteTimeout = 2000
    return $serial
}

function Start-DirectSerial {
    try {
        $script:DirectSerial = New-ConfiguredSerialPort $script:Port
        $script:DirectSerial.Open()
        Start-Sleep -Milliseconds 300
        try { $script:DirectSerial.DiscardInBuffer() } catch {}
        return $true
    } catch {
        $message = $_.Exception.Message
        if ($_.Exception -is [UnauthorizedAccessException]) {
            $message = "порт $($script:Port) занят — закройте TeraTerm или Serial Monitor"
        }
        $script:StatusText = "не удалось открыть $($script:Port): $message"
        if ($null -ne $script:DirectSerial) {
            try { $script:DirectSerial.Dispose() } catch {}
            $script:DirectSerial = $null
        }
        return $false
    }
}

function Start-Monitor {
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) { return $true }
    if (Test-UseDirectSerialTransport) { return Start-DirectSerial }
    $executable = Resolve-Executable $script:ArduinoCli
    if ([string]::IsNullOrEmpty($executable)) {
        $script:StatusText = 'arduino-cli не найден (задайте MKC_ARDUINO_CLI)'
        return $false
    }
    if ([string]::IsNullOrEmpty($script:Port)) {
        $found = @(Get-CdcPorts)
        if ($found.Count -gt 0) { $script:Port = $found[0] }
    }
    if ([string]::IsNullOrEmpty($script:Port)) { return $false }

    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $executable
    $info.Arguments = (@('monitor','--quiet','--port',$script:Port,'--config','baudrate=115200') |
        ForEach-Object { Quote-NativeArgument ([string]$_) }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    try {
        $info.StandardOutputEncoding = [Text.Encoding]::UTF8
        $info.StandardErrorEncoding = [Text.Encoding]::UTF8
    } catch {}
    $script:Monitor = New-Object Diagnostics.Process
    $script:Monitor.StartInfo = $info
    try {
        if (-not $script:Monitor.Start()) { return $false }
        $script:Monitor.StandardInput.AutoFlush = $true
        $script:MonitorErrorTask = $script:Monitor.StandardError.ReadToEndAsync()
        Start-Sleep -Milliseconds 350
        if ($script:Monitor.HasExited) {
            $script:StatusText = 'arduino-cli monitor завершился при запуске'
            return $false
        }
        return $true
    } catch {
        $script:StatusText = $_.Exception.Message
        return $false
    }
}

function Stop-Monitor {
    if ($null -ne $script:DirectSerial) {
        try { if ($script:DirectSerial.IsOpen) { $script:DirectSerial.Close() } } catch {}
        try { $script:DirectSerial.Dispose() } catch {}
        $script:DirectSerial = $null
    }
    if ($null -eq $script:Monitor) { return }
    try { $script:Monitor.StandardInput.Close() } catch {}
    try {
        if (-not $script:Monitor.HasExited) { $script:Monitor.Kill() }
        $script:Monitor.WaitForExit(1000) | Out-Null
    } catch {}
    try { $script:Monitor.Dispose() } catch {}
    $script:Monitor = $null
    $script:MonitorReadTask = $null
}

function Send-RemoteLine {
    param([string]$Command)
    if ($null -ne $script:DirectSerial) {
        if (-not $script:DirectSerial.IsOpen) { return $false }
        try {
            $script:DirectSerial.Write($Command + "`r")
            return $true
        } catch {
            $script:StatusText = 'Не удалось отправить команду калькулятору: ' + $_.Exception.Message
            return $false
        }
    }
    if ($null -eq $script:Monitor -or $script:Monitor.HasExited) { return $false }
    try {
        $script:Monitor.StandardInput.Write($Command + "`r")
        $script:Monitor.StandardInput.Flush()
        return $true
    } catch {
        $script:StatusText = 'Не удалось отправить команду калькулятору'
        return $false
    }
}

function Read-SerialLine {
    param([int]$TimeoutMilliseconds = 5000)
    $script:SerialLine = ''
    if ($null -ne $script:DirectSerial) {
        if (-not $script:DirectSerial.IsOpen) { return $false }
        try {
            $script:DirectSerial.ReadTimeout = $TimeoutMilliseconds
            $line = $script:DirectSerial.ReadLine()
            $script:SerialLine = ([string]$line).TrimEnd("`r")
            return $true
        } catch [TimeoutException] {
            return $false
        } catch {
            $script:StatusText = 'Ошибка чтения порта: ' + $_.Exception.Message
            return $false
        }
    }
    if ($null -eq $script:Monitor -or $script:Monitor.HasExited) { return $false }
    try {
        if ($null -eq $script:MonitorReadTask) {
            $script:MonitorReadTask = $script:Monitor.StandardOutput.ReadLineAsync()
        }
        if (-not $script:MonitorReadTask.Wait($TimeoutMilliseconds)) { return $false }
        $line = $script:MonitorReadTask.Result
        $script:MonitorReadTask = $null
        if ($null -eq $line) { return $false }
        $script:SerialLine = ([string]$line).TrimEnd("`r")
        return $true
    } catch {
        $script:MonitorReadTask = $null
        return $false
    }
}

function Wait-RemoteMarker {
    param([string]$Prefix, [int]$TimeoutMilliseconds = 5000)
    $script:MarkerLine = ''
    for ($attempt = 0; $attempt -lt 200; $attempt++) {
        if (-not (Read-SerialLine $TimeoutMilliseconds)) {
            $script:StatusText = 'Таймаут ответа калькулятора'
            return $false
        }
        $line = $script:SerialLine
        if ($line.StartsWith('@MKC:ERROR')) {
            $script:StatusText = 'Калькулятор: ' + $line.Substring(10).Trim()
            return $false
        }
        if ($line -match '^Unknown command: fs(get|put)') {
            $script:StatusText = 'Прошивка не поддерживает F3/F5; загрузите свежую сборку'
            return $false
        }
        if ($line.StartsWith($Prefix)) { $script:MarkerLine = $line; return $true }
    }
    $script:StatusText = 'Слишком длинный ответ калькулятора'
    return $false
}

function Join-RemotePath {
    param([string]$Parent, [string]$Name)
    if ($Parent -eq '/') { return '/' + $Name.TrimStart('/') }
    return $Parent.TrimEnd('/') + '/' + $Name.TrimStart('/')
}

function Get-RemoteParent {
    param([string]$Path)
    $normalized = Normalize-RemotePath '/' $Path
    if ($normalized -eq '/') { return '/' }
    $index = $normalized.LastIndexOf('/')
    if ($index -le 0) { return '/' }
    return $normalized.Substring(0, $index)
}

function Normalize-RemotePath {
    param([string]$Base, [string]$InputPath)
    $combined = if ($InputPath.StartsWith('/')) { $InputPath } else { Join-RemotePath $Base $InputPath }
    $parts = New-Object 'System.Collections.Generic.List[string]'
    foreach ($part in $combined.Split('/')) {
        if ([string]::IsNullOrEmpty($part) -or $part -eq '.') { continue }
        if ($part -eq '..') {
            if ($parts.Count -gt 0) { $parts.RemoveAt($parts.Count - 1) }
        } else { $parts.Add($part) }
    }
    if ($parts.Count -eq 0) { return '/' }
    return '/' + ($parts.ToArray() -join '/')
}

function Get-MockPath {
    param([string]$Remote)
    $normalized = Normalize-RemotePath '/' $Remote
    if ($normalized -eq '/') { return $script:MockRoot }
    $relative = $normalized.TrimStart('/') -replace '/', [IO.Path]::DirectorySeparatorChar
    return Join-Path $script:MockRoot $relative
}

function Get-PosixChecksumBytes {
    param([byte[]]$Bytes)
    [uint64]$crc = 0
    foreach ($byte in $Bytes) {
        $crc = $crc -bxor ([uint64]$byte -shl 24)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band [uint64]2147483648) -ne 0) {
                $crc = (($crc -shl 1) -bxor [uint64]79764919) -band [uint64]4294967295
            } else { $crc = ($crc -shl 1) -band [uint64]4294967295 }
        }
    }
    [uint64]$length = $Bytes.LongLength
    while ($length -ne 0) {
        $byte = [byte]($length -band 0xFF)
        $crc = $crc -bxor ([uint64]$byte -shl 24)
        for ($bit = 0; $bit -lt 8; $bit++) {
            if (($crc -band [uint64]2147483648) -ne 0) {
                $crc = (($crc -shl 1) -bxor [uint64]79764919) -band [uint64]4294967295
            } else { $crc = ($crc -shl 1) -band [uint64]4294967295 }
        }
        $length = $length -shr 8
    }
    return [uint32]($crc -bxor [uint64]4294967295)
}

function Get-PosixChecksum {
    param([string]$Path)
    return Get-PosixChecksumBytes ([IO.File]::ReadAllBytes($Path))
}

function Get-UnsupportedReason {
    param([string]$Path, [string]$Kind = '')
    $name = Split-Path -Leaf $Path
    if ([string]::IsNullOrEmpty($Kind)) {
        if (-not (Test-Path -LiteralPath $Path)) { $Kind = 'o' }
        else {
            $item = Get-Item -LiteralPath $Path -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { $Kind = 'l' }
            elseif ($item.PSIsContainer) { $Kind = 'd' }
            else { $Kind = 'f' }
        }
    }
    if ($Kind -eq 'l') { return 'символическая ссылка' }
    if ([string]::IsNullOrEmpty($name) -or $name -in @('.','..')) { return 'недопустимое имя' }
    if ($name.IndexOfAny([char[]]"<>:`"/\|?*") -ge 0 -or $name -match '[\x00-\x1f]') {
        return 'недопустимый символ в имени'
    }
    if ($name.EndsWith(' ') -or $name.EndsWith('.')) { return 'имя оканчивается пробелом или точкой' }
    if ($Kind -notin @('f','d')) { return 'не обычный файл или каталог' }

    $base = $name
    [long]$limit = 1536
    [long]$minimum = 0
    if ($Kind -eq 'f') {
        $lower = $name.ToLowerInvariant()
        if ($lower -in @('focal.mod','basic.mod')) {
            $base = $name.Substring(0, $name.Length - 4); $limit = 16384; $minimum = 64
        }
        elseif ($lower -eq 'wbmp.mod') {
            $base = $name.Substring(0, $name.Length - 4); $limit = 4096; $minimum = 64
        }
        elseif ($lower.EndsWith('.mod')) { return 'допустимы только FOCAL.MOD, BASIC.MOD и WBMP.MOD' }
        elseif ($lower.EndsWith('.state.txt')) { $base = $name.Substring(0, $name.Length - 10) }
        elseif ($lower -match '\.(m61|foc|tbi|txt|fmk)$') { $base = $name.Substring(0, $name.Length - 4) }
        elseif ($lower.EndsWith('.wbmp')) { $base = $name.Substring(0, $name.Length - 5); $limit = 1600 }
        elseif ($lower -match '\.(t1|m2)$') { $base = $name.Substring(0, $name.Length - 3) }
        elseif ($lower.EndsWith('.wbm')) { $base = $name.Substring(0, $name.Length - 4); $limit = 1600 }
        else { return 'формат не поддерживается' }
    }
    $bytes = [Text.Encoding]::UTF8.GetByteCount($base)
    if ($bytes -lt 1 -or $bytes -gt 31) { return 'basename должен занимать 1–31 байт UTF-8' }
    if ($base.ToUpperInvariant() -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
        return 'зарезервированное имя DOS'
    }
    if ($Kind -eq 'f') {
        try { $size = (Get-Item -LiteralPath $Path -Force).Length } catch { return 'не удалось прочитать размер' }
        if ($size -lt $minimum) { return "слишком маленький: $size байт, минимум $minimum" }
        if ($size -gt $limit) { return "слишком большой: $size байт, максимум $limit" }
    }
    return ''
}

function New-PanelEntry {
    param([string]$Name, [string]$Kind, [long]$Size = 0, [string]$Reason = '')
    return [pscustomobject]@{ Name = $Name; Kind = $Kind; Size = $Size; Reason = $Reason; Marked = $false }
}

function Format-RemoteQuotedPath {
    param([string]$Path)
    return '"' + $Path.Replace('"', '\"') + '"'
}

function Get-RemoteEntries {
    param([string]$Path)
    $entries = New-Object 'System.Collections.Generic.List[object]'
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        $physical = Get-MockPath $Path
        if (-not (Test-Path -LiteralPath $physical -PathType Container)) {
            $script:StatusText = "Нет каталога $Path"
            throw $script:StatusText
        }
        foreach ($item in @(Get-ChildItem -LiteralPath $physical -Force -ErrorAction Stop)) {
            $kind = if ($item.PSIsContainer) { 'd' } else { 'f' }
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
            if ($kind -eq 'f' -and -not ($item -is [IO.FileInfo])) { continue }
            $size = if ($kind -eq 'f') { [long]$item.Length } else { [long]0 }
            $remoteItem = Join-RemotePath $Path $item.Name
            $reason = Get-UnsupportedReason (Get-MockPath $remoteItem) $kind
            $entries.Add((New-PanelEntry $item.Name $kind $size $reason))
        }
        return @($entries.ToArray())
    }

    if (-not (Send-RemoteLine ('ls ' + (Format-RemoteQuotedPath $Path)))) {
        throw $script:StatusText
    }
    for ($count = 0; $count -lt 10000; $count++) {
        if (-not (Read-SerialLine 8000)) {
            $script:StatusText = "Нет ответа на ls $Path"
            throw $script:StatusText
        }
        $line = $script:SerialLine
        if ($line -match '^d\t(.*)/$') {
            $entries.Add((New-PanelEntry $Matches[1] 'd'))
            continue
        }
        if ($line -match '^f\t([0-9]+) B\t(.*)$') {
            $entries.Add((New-PanelEntry $Matches[2] 'f' ([long]$Matches[1])))
            continue
        }
        if ($line -match ' entr(y|ies)\.$') { return @($entries.ToArray()) }
        if ($line -match '^(ls:|Unknown command:)') {
            $script:StatusText = $line
            throw $line
        }
    }
    $script:StatusText = 'Каталог устройства слишком велик'
    throw $script:StatusText
}

function Invoke-RemoteSimple {
    param([string]$Command)
    if (-not (Send-RemoteLine $Command) -or -not (Send-RemoteLine 'ls "/"')) { return $false }
    $failed = $false
    for ($count = 0; $count -lt 10000; $count++) {
        if (-not (Read-SerialLine 12000)) {
            $script:StatusText = 'Нет ответа калькулятора'
            return $false
        }
        $line = $script:SerialLine
        if ($line -match '^(mkdir:|mv:|rm:|rmdir:|Unknown command:)') {
            $script:StatusText = $line
            $failed = $true
        }
        if ($line -match ' entr(y|ies)\.$') { return -not $failed }
    }
    $script:StatusText = 'Операция не завершилась'
    return $false
}

function New-RemoteDirectory {
    param([string]$Path)
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        try {
            [void](New-Item -ItemType Directory -Force -Path (Get-MockPath $Path))
            return $true
        } catch {
            $script:StatusText = "Не удалось создать $Path"
            return $false
        }
    }
    return Invoke-RemoteSimple ('mkdir -p ' + (Format-RemoteQuotedPath $Path))
}

function Move-RemoteItem {
    param([string]$Source, [string]$Destination)
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        try {
            Move-Item -LiteralPath (Get-MockPath $Source) -Destination (Get-MockPath $Destination) -Force
            return $true
        } catch {
            $script:StatusText = 'Переименование не удалось'
            return $false
        }
    }
    return Invoke-RemoteSimple ('mv ' + (Format-RemoteQuotedPath $Source) + ' ' +
        (Format-RemoteQuotedPath $Destination))
}

function Remove-RemoteItem {
    param([string]$Path)
    if ($Path -eq '/') {
        $script:StatusText = 'Нельзя удалить корневой каталог'
        return $false
    }
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        try {
            Remove-Item -LiteralPath (Get-MockPath $Path) -Recurse -Force
            return $true
        } catch {
            $script:StatusText = 'Удаление не удалось'
            return $false
        }
    }
    return Invoke-RemoteSimple ('rm -r ' + (Format-RemoteQuotedPath $Path))
}

function Convert-BytesToHex {
    param([byte[]]$Bytes, [int]$Offset = 0, [int]$Count = -1)
    if ($Count -lt 0) { $Count = $Bytes.Length - $Offset }
    $builder = New-Object Text.StringBuilder ($Count * 2)
    for ($index = $Offset; $index -lt $Offset + $Count; $index++) {
        [void]$builder.Append($Bytes[$index].ToString('X2'))
    }
    return $builder.ToString()
}

function Send-RemoteFile {
    param([string]$Source, [string]$Destination)
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        try {
            Copy-Item -LiteralPath $Source -Destination (Get-MockPath $Destination) -Force
            return $true
        } catch {
            $script:StatusText = "Не удалось записать $Destination"
            return $false
        }
    }
    try { [byte[]]$bytes = [IO.File]::ReadAllBytes($Source) }
    catch { $script:StatusText = "Не удалось прочитать $Source"; return $false }
    $size = $bytes.Length
    $crc = Get-PosixChecksumBytes $bytes
    $begin = 'fsput begin {0} {1} {2}' -f (Format-RemoteQuotedPath $Destination), $size, $crc
    if (-not (Send-RemoteLine $begin) -or -not (Wait-RemoteMarker '@MKC:READY ')) { return $false }
    if ($script:MarkerLine.Substring(11).Trim() -ne [string]$size) {
        $script:StatusText = 'Неверный ответ fsput begin'
        return $false
    }
    for ($offset = 0; $offset -lt $size; $offset += $count) {
        $count = [Math]::Min($script:FsPutChunkBytes, $size - $offset)
        $hex = Convert-BytesToHex $bytes $offset $count
        if (-not (Send-RemoteLine ("fsput data $offset $hex")) -or
            -not (Wait-RemoteMarker '@MKC:ACK ')) { return $false }
        $expected = $offset + $count
        if ($script:MarkerLine.Substring(9).Trim() -ne [string]$expected) {
            $script:StatusText = 'Неверное смещение ACK'
            return $false
        }
    }
    if (-not (Send-RemoteLine 'fsput end') -or -not (Wait-RemoteMarker '@MKC:DONE ')) { return $false }
    if ($script:MarkerLine -ne "@MKC:DONE $size $crc") {
        $script:StatusText = 'Контрольная сумма загрузки не совпала'
        return $false
    }
    return $true
}

function Receive-RemoteFile {
    param([string]$Source, [string]$Destination)
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        try {
            Copy-Item -LiteralPath (Get-MockPath $Source) -Destination $Destination -Force
            return $true
        } catch {
            $script:StatusText = "Не удалось прочитать $Source"
            return $false
        }
    }
    if (-not (Send-RemoteLine ('fsget ' + (Format-RemoteQuotedPath $Source))) -or
        -not (Wait-RemoteMarker '@MKC:GET ')) { return $false }
    $header = $script:MarkerLine.Substring(9).Trim() -split ' ', 2
    [long]$headerSize = 0
    [uint32]$headerCrc = 0
    if ($header.Count -ne 2 -or
        -not [long]::TryParse($header[0], [ref]$headerSize) -or
        -not [uint32]::TryParse($header[1], [ref]$headerCrc)) {
        $script:StatusText = 'Повреждён заголовок fsget'
        return $false
    }
    $bytes = New-Object 'System.Collections.Generic.List[byte]'
    [long]$endSize = -1
    [uint32]$endCrc = 0
    while ($true) {
        if (-not (Read-SerialLine 8000)) { $script:StatusText = 'Таймаут fsget'; return $false }
        $line = $script:SerialLine
        if ($line -match '^@MKC:DATA ([0-9]+) ([0-9A-Fa-f]+)$') {
            if ([long]$Matches[1] -ne $bytes.Count -or ($Matches[2].Length % 2) -ne 0) {
                $script:StatusText = 'Нарушен порядок или формат блоков fsget'
                return $false
            }
            for ($index = 0; $index -lt $Matches[2].Length; $index += 2) {
                $bytes.Add([Convert]::ToByte($Matches[2].Substring($index, 2), 16))
            }
            continue
        }
        if ($line -match '^@MKC:END ([0-9]+) ([0-9]+)$') {
            $endSize = [long]$Matches[1]
            $endCrc = [uint32]$Matches[2]
            break
        }
        if ($line.StartsWith('@MKC:ERROR')) {
            $script:StatusText = 'Калькулятор: ' + $line.Substring(10).Trim()
            return $false
        }
    }
    if ($bytes.Count -ne $headerSize -or $endSize -ne $headerSize -or $endCrc -ne $headerCrc) {
        $script:StatusText = 'Размер fsget не совпал'
        return $false
    }
    [byte[]]$result = $bytes.ToArray()
    if ((Get-PosixChecksumBytes $result) -ne $headerCrc) {
        $script:StatusText = 'Ошибка контрольной суммы fsget'
        return $false
    }
    try { [IO.File]::WriteAllBytes($Destination, $result) }
    catch { $script:StatusText = "Не удалось записать $Destination"; return $false }
    return $true
}

function Get-LocalParent {
    param([string]$Path)
    try {
        $parent = (Get-Item -LiteralPath $Path -Force).Parent
        if ($null -eq $parent) { return '' }
        return $parent.FullName
    } catch { return '' }
}

function Set-PanelEntries {
    param([string]$Panel, [object[]]$Entries, [string]$OldName = '')
    $state = $script:Panels[$Panel]
    $state.Entries = @($Entries)
    if ($state.Entries.Count -eq 0) { $state.Entries = @((New-PanelEntry '..' 'd')) }
    if (-not [string]::IsNullOrEmpty($OldName)) {
        for ($index = 0; $index -lt $state.Entries.Count; $index++) {
            if ($state.Entries[$index].Name -eq $OldName) { $state.Selected = $index; break }
        }
    }
    $state.Selected = [Math]::Max(0, [Math]::Min($state.Selected, $state.Entries.Count - 1))
}

function Load-LocalPanel {
    $state = $script:Panels.L
    $oldName = if ($state.Entries.Count -gt 0 -and $state.Selected -lt $state.Entries.Count) {
        $state.Entries[$state.Selected].Name
    } else { '' }
    $entries = New-Object 'System.Collections.Generic.List[object]'
    if (-not [string]::IsNullOrEmpty((Get-LocalParent $script:LocalPath))) {
        $entries.Add((New-PanelEntry '..' 'd'))
    }
    try {
        $items = @(Get-ChildItem -LiteralPath $script:LocalPath -Force -ErrorAction Stop)
        foreach ($item in @($items | Sort-Object @{Expression={ -not $_.PSIsContainer }}, Name)) {
            $kind = if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { 'l' }
                elseif ($item.PSIsContainer) { 'd' }
                elseif ($item -is [IO.FileInfo]) { 'f' }
                else { 'o' }
            $size = if ($kind -eq 'f') { [long]$item.Length } else { [long]0 }
            $reason = Get-UnsupportedReason $item.FullName $kind
            $entries.Add((New-PanelEntry $item.Name $kind $size $reason))
        }
    } catch { $script:StatusText = $_.Exception.Message }
    Set-PanelEntries 'L' $entries.ToArray() $oldName
}

function Load-RemotePanel {
    $state = $script:Panels.R
    $oldName = if ($state.Entries.Count -gt 0 -and $state.Selected -lt $state.Entries.Count) {
        $state.Entries[$state.Selected].Name
    } else { '' }
    try { $items = @(Get-RemoteEntries $script:RemotePath) }
    catch { return $false }
    $entries = New-Object 'System.Collections.Generic.List[object]'
    if ($script:RemotePath -ne '/') { $entries.Add((New-PanelEntry '..' 'd')) }
    foreach ($item in @($items | Sort-Object @{Expression={ $_.Kind -ne 'd' }}, Name)) { $entries.Add($item) }
    Set-PanelEntries 'R' $entries.ToArray() $oldName
    return $true
}

function Refresh-Panels {
    Load-LocalPanel
    if (-not (Load-RemotePanel)) {
        Set-PanelEntries 'R' @((New-PanelEntry '<нет связи>' 'f' 0 'устройство недоступно'))
    }
    $script:Panels.L.Page = 0
    $script:Panels.R.Page = 0
}

function Get-SelectedEntry {
    param([string]$Panel = $script:ActivePanel)
    $state = $script:Panels[$Panel]
    if ($state.Entries.Count -eq 0) { return $null }
    return $state.Entries[$state.Selected]
}

function Get-ChosenIndices {
    param([string]$Panel = $script:ActivePanel)
    $state = $script:Panels[$Panel]
    $chosen = New-Object 'System.Collections.Generic.List[int]'
    for ($index = 0; $index -lt $state.Entries.Count; $index++) {
        if ($state.Entries[$index].Marked -and $state.Entries[$index].Name -ne '..') { $chosen.Add($index) }
    }
    if ($chosen.Count -eq 0 -and $state.Entries.Count -gt 0 -and
        $state.Entries[$state.Selected].Name -ne '..') { $chosen.Add($state.Selected) }
    return @($chosen.ToArray())
}

function Clear-PanelMarks {
    param([string]$Panel)
    foreach ($entry in $script:Panels[$Panel].Entries) { $entry.Marked = $false }
}

function Reset-CopyPlan {
    $script:CopyPlan = @()
    $script:CopyTotal = [long]0
    $script:PlanError = ''
}

function Add-CopyPlanItem {
    param([string]$Kind, [string]$Source, [string]$Destination, [long]$Size = 0)
    $script:CopyPlan += [pscustomobject]@{
        Kind = $Kind; Source = $Source; Destination = $Destination; Size = $Size
    }
    if ($Kind -eq 'f') { $script:CopyTotal += $Size }
}

function Add-LocalTreeToPlan {
    param([string]$Source, [string]$Destination)
    try { $item = Get-Item -LiteralPath $Source -Force }
    catch { $script:PlanError = "$(Split-Path -Leaf $Source): не читается"; return $false }
    $kind = if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { 'l' }
        elseif ($item.PSIsContainer) { 'd' } else { 'f' }
    $reason = Get-UnsupportedReason $Source $kind
    if (-not [string]::IsNullOrEmpty($reason)) {
        $script:PlanError = "$(Split-Path -Leaf $Source): $reason"
        return $false
    }
    if ($kind -eq 'f') {
        $sourceLower = $item.Name.ToLowerInvariant()
        if ($sourceLower -in @('focal.mod','basic.mod','wbmp.mod')) {
            $destinationLeaf = $Destination.TrimStart('/')
            if ($destinationLeaf.Contains('/') -or
                $destinationLeaf.ToLowerInvariant() -ne $sourceLower) {
                $script:PlanError = "$($item.Name): модуль сохраняется только в корне под своим фиксированным именем"
                return $false
            }
        }
        Add-CopyPlanItem 'f' $Source $Destination ([long]$item.Length)
        return $true
    }
    Add-CopyPlanItem 'd' $Source $Destination
    foreach ($child in @(Get-ChildItem -LiteralPath $Source -Force | Sort-Object Name)) {
        if (-not (Add-LocalTreeToPlan $child.FullName (Join-RemotePath $Destination $child.Name))) {
            return $false
        }
    }
    return $true
}

function Add-RemoteTreeToPlan {
    param([string]$Source, [string]$Destination, [string]$Kind, [long]$Size = 0)
    if ($Kind -eq 'f') {
        Add-CopyPlanItem 'f' $Source $Destination $Size
        return $true
    }
    Add-CopyPlanItem 'd' $Source $Destination
    try { $children = @(Get-RemoteEntries $Source) }
    catch { $script:PlanError = $script:StatusText; return $false }
    foreach ($child in $children) {
        $added = Add-RemoteTreeToPlan (Join-RemotePath $Source $child.Name) `
            (Join-Path $Destination $child.Name) $child.Kind $child.Size
        if (-not $added) { return $false }
    }
    return $true
}

$script:Styles = @{
    Outside          = "$($script:Escape)[0m"
    Panel            = "$($script:Escape)[38;2;192;192;192;48;2;0;0;170m"
    Border           = "$($script:Escape)[1;38;2;85;255;255;48;2;0;0;170m"
    InactiveBorder   = "$($script:Escape)[38;2;0;170;170;48;2;0;0;170m"
    Title            = "$($script:Escape)[1;38;2;255;255;255;48;2;0;0;170m"
    File             = "$($script:Escape)[1;38;2;85;255;255;48;2;0;0;170m"
    Marked           = "$($script:Escape)[1;38;2;255;255;85;48;2;0;0;170m"
    Disabled         = "$($script:Escape)[38;2;128;128;128;48;2;0;0;170m"
    Selected         = "$($script:Escape)[38;2;0;0;0;48;2;0;170;170m"
    SelectedDisabled = "$($script:Escape)[38;2;0;0;0;48;2;160;160;160m"
    Menu             = "$($script:Escape)[38;2;0;0;0;48;2;0;170;170m"
    Status           = "$($script:Escape)[1;38;2;255;255;85;48;2;0;0;170m"
    Error            = "$($script:Escape)[1;38;2;255;85;85;48;2;0;0;170m"
    Command          = "$($script:Escape)[38;2;192;192;192;48;2;0;0;0m"
    FunctionNumber   = "$($script:Escape)[38;2;192;192;192;48;2;0;0;0m"
    FunctionLabel    = "$($script:Escape)[38;2;0;0;0;48;2;0;170;170m"
    Dialog           = "$($script:Escape)[38;2;0;0;0;48;2;170;170;170m"
    DialogBorder     = "$($script:Escape)[1;38;2;255;255;255;48;2;170;170;170m"
    DialogTitle      = "$($script:Escape)[38;2;85;85;85;48;2;255;255;255m"
    DialogInput      = "$($script:Escape)[38;2;0;0;0;48;2;255;255;255m"
    DialogButton     = "$($script:Escape)[38;2;0;0;0;48;2;255;255;255m"
    DialogButtonHot  = "$($script:Escape)[38;2;0;0;0;48;2;255;255;85m"
    Shadow           = "$($script:Escape)[38;2;0;0;0;48;2;0;0;0m"
}
$script:Layout = $null
$script:Dialog = $null
$script:ScreenActive = $false
$script:OriginalCursorVisible = $true
$script:KeyChar = [char]0

function Set-UiStyle {
    param([string]$Name)
    [Console]::Write($script:Styles[$Name])
}

function Set-UiPosition {
    param([int]$X, [int]$Y)
    try { [Console]::SetCursorPosition([Math]::Max(0, $X), [Math]::Max(0, $Y)) } catch {}
}

function Set-UiCursorVisible {
    param([bool]$Visible)
    try { [Console]::CursorVisible = $Visible } catch {}
    if ($Visible) { [Console]::Write("$($script:Escape)[?25h") }
    else { [Console]::Write("$($script:Escape)[?25l") }
}

function Write-Ui {
    param([int]$X, [int]$Y, [string]$Text, [string]$Style = 'Panel')
    Set-UiPosition $X $Y
    Set-UiStyle $Style
    [Console]::Write($Text)
}

function Get-ClippedText {
    param([string]$Text, [int]$Width)
    if ($null -eq $Text -or $Width -le 0) { return '' }
    $value = $Text.Replace("`r", '?').Replace("`n", '?').Replace("`t", '→')
    if ($value.Length -le $Width) { return $value }
    if ($Width -le 1) { return '' }
    return $value.Substring(0, $Width - 1) + '…'
}

function Get-FittedText {
    param([string]$Text, [int]$Width)
    $shown = Get-ClippedText $Text $Width
    return $shown + (' ' * [Math]::Max(0, $Width - $shown.Length))
}

function Get-CenteredText {
    param([string]$Text, [int]$Width)
    $shown = Get-ClippedText $Text $Width
    $left = [Math]::Max(0, [int][Math]::Floor(($Width - $shown.Length) / 2.0))
    return (' ' * $left) + $shown + (' ' * [Math]::Max(0, $Width - $left - $shown.Length))
}

function Update-Layout {
    try { $columns = [Console]::WindowWidth; $rows = [Console]::WindowHeight }
    catch { $columns = 80; $rows = 24 }
    # Некоторые псевдотерминалы сообщают размер 0×0 до первого события изменения.
    # Разумное запасное значение делает запуск детерминированным; настоящая
    # маленькая консоль всё равно отклоняется ниже.
    if ($columns -le 0 -or $rows -le 0) { $columns = 80; $rows = 24 }
    if ($columns -lt 70 -or $rows -lt 18) {
        throw "Терминал слишком мал: нужно не меньше 70×18, сейчас $columns×$rows"
    }
    $width = [Math]::Min(92, $columns - 4)
    $height = [Math]::Min(25, $rows - 2)
    $x = [int][Math]::Floor(($columns - $width) / 2.0)
    $y = [int][Math]::Floor(($rows - $height) / 2.0)
    $leftWidth = [int][Math]::Floor($width / 2.0)
    $panelBottom = $y + $height - 3
    $separator = $panelBottom - 2
    $script:Layout = [pscustomobject]@{
        ConsoleColumns = $columns; ConsoleRows = $rows
        X = $x; Y = $y; Width = $width; Height = $height
        LeftWidth = $leftWidth; RightX = $x + $leftWidth; RightWidth = $width - $leftWidth
        HeaderRow = $y + 1; ListTop = $y + 2; ListBottom = $separator - 1
        ListRows = $separator - ($y + 2); SeparatorRow = $separator
        InfoRow = $panelBottom - 1; PanelBottom = $panelBottom
        CommandRow = $y + $height - 2; FunctionRow = $y + $height - 1
    }
}

function Get-DisplayLocalPath {
    $homePath = [Environment]::GetFolderPath('UserProfile')
    if ($script:LocalPath -eq $homePath) { return '~' }
    if (-not [string]::IsNullOrEmpty($homePath) -and
        $script:LocalPath.StartsWith($homePath + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        return '~' + $script:LocalPath.Substring($homePath.Length)
    }
    return $script:LocalPath
}

function Get-PanelGeometry {
    param([string]$Panel)
    $x = if ($Panel -eq 'L') { $script:Layout.X } else { $script:Layout.RightX }
    $width = if ($Panel -eq 'L') { $script:Layout.LeftWidth } else { $script:Layout.RightWidth }
    $inner = $width - 2
    $columns = [Math]::Max(1, [Math]::Min(4, [int][Math]::Floor($inner / 18.0)))
    $area = $inner - $columns + 1
    $cellWidth = [int][Math]::Floor($area / [double]$columns)
    return [pscustomobject]@{
        X = $x; Width = $width; Inner = $inner; Columns = $columns
        CellWidth = $cellWidth; Remainder = $area % $columns
        Capacity = $script:Layout.ListRows * $columns
    }
}

function Get-PanelColumnGeometry {
    param([object]$Geometry, [int]$Column)
    $x = $Geometry.X + 1
    for ($index = 0; $index -lt $Column; $index++) {
        $width = $Geometry.CellWidth + $(if ($index -lt $Geometry.Remainder) { 1 } else { 0 })
        $x += $width + 1
    }
    $cell = $Geometry.CellWidth + $(if ($Column -lt $Geometry.Remainder) { 1 } else { 0 })
    return [pscustomobject]@{ X = $x; Width = $cell }
}

function Ensure-PanelPage {
    param([string]$Panel)
    $geometry = Get-PanelGeometry $Panel
    $state = $script:Panels[$Panel]
    $state.Page = [int][Math]::Floor($state.Selected / [double]$geometry.Capacity) * $geometry.Capacity
}

function Draw-PanelTop {
    param([string]$Panel)
    $geometry = Get-PanelGeometry $Panel
    $title = if ($Panel -eq 'L') { Get-DisplayLocalPath } else { "MK61s:$($script:RemotePath)" }
    $title = Get-ClippedText $title ($geometry.Width - 8)
    $label = " $title "
    $rest = [Math]::Max(0, $geometry.Inner - $label.Length)
    $left = [int][Math]::Floor($rest / 2.0)
    Write-Ui $geometry.X $script:Layout.Y ('╔' + ('═' * $left)) 'Border'
    [Console]::Write($script:Styles[$(if ($Panel -eq $script:ActivePanel) { 'Menu' } else { 'File' })])
    [Console]::Write($label)
    Set-UiStyle 'Border'
    [Console]::Write(('═' * ($rest - $left)) + '╗')
}

function Draw-PanelFrame {
    param([string]$Panel)
    $geometry = Get-PanelGeometry $Panel
    Draw-PanelTop $Panel
    Write-Ui $geometry.X $script:Layout.HeaderRow '║' 'Border'
    for ($column = 0; $column -lt $geometry.Columns; $column++) {
        $cell = Get-PanelColumnGeometry $geometry $column
        Write-Ui $cell.X $script:Layout.HeaderRow (Get-CenteredText 'Name' $cell.Width) 'Status'
        if ($column -lt $geometry.Columns - 1) { [Console]::Write($script:Styles.Border + '│') }
    }
    [Console]::Write($script:Styles.Border + '║')
    for ($row = $script:Layout.ListTop; $row -le $script:Layout.ListBottom; $row++) {
        Write-Ui $geometry.X $row '║' 'Border'
        for ($column = 0; $column -lt $geometry.Columns; $column++) {
            $cell = Get-PanelColumnGeometry $geometry $column
            Write-Ui $cell.X $row (' ' * $cell.Width) 'Panel'
            if ($column -lt $geometry.Columns - 1) { [Console]::Write($script:Styles.Border + '│') }
        }
        [Console]::Write($script:Styles.Border + '║')
    }
    Write-Ui $geometry.X $script:Layout.SeparatorRow '╠' 'Border'
    for ($column = 0; $column -lt $geometry.Columns; $column++) {
        $cell = Get-PanelColumnGeometry $geometry $column
        [Console]::Write('═' * $cell.Width)
        if ($column -lt $geometry.Columns - 1) { [Console]::Write('╪') }
    }
    [Console]::Write('╣')
    Write-Ui $geometry.X $script:Layout.InfoRow ('║' + (' ' * $geometry.Inner) + '║') 'Border'
    Write-Ui ($geometry.X + 1) $script:Layout.InfoRow (' ' * $geometry.Inner) 'Panel'
    Write-Ui $geometry.X $script:Layout.PanelBottom ('╚' + ('═' * $geometry.Inner) + '╝') 'Border'
}

function Get-EntryStyle {
    param([string]$Panel, [int]$Index)
    $state = $script:Panels[$Panel]
    $entry = $state.Entries[$Index]
    if ($Panel -eq $script:ActivePanel -and $Index -eq $state.Selected) {
        if ([string]::IsNullOrEmpty($entry.Reason)) { return 'Selected' }
        return 'SelectedDisabled'
    }
    if (-not [string]::IsNullOrEmpty($entry.Reason)) { return 'Disabled' }
    if ($entry.Marked) { return 'Marked' }
    return 'File'
}

function Draw-PanelSlot {
    param([string]$Panel, [int]$Slot)
    $geometry = Get-PanelGeometry $Panel
    $state = $script:Panels[$Panel]
    $index = $state.Page + $Slot
    $row = $script:Layout.ListTop + ($Slot % $script:Layout.ListRows)
    $column = [int][Math]::Floor($Slot / [double]$script:Layout.ListRows)
    $cell = Get-PanelColumnGeometry $geometry $column
    if ($index -ge $state.Entries.Count) {
        Write-Ui $cell.X $row (' ' * $cell.Width) 'Panel'
        return
    }
    $name = $state.Entries[$index].Name
    Write-Ui $cell.X $row (Get-FittedText " $name" $cell.Width) (Get-EntryStyle $Panel $index)
}

function Draw-PanelInfo {
    param([string]$Panel)
    $geometry = Get-PanelGeometry $Panel
    $entry = Get-SelectedEntry $Panel
    if ($null -eq $entry) { return }
    if (-not [string]::IsNullOrEmpty($entry.Reason)) {
        $text = "$($entry.Name) · $($entry.Reason)"; $style = 'Disabled'
    } elseif ($entry.Kind -eq 'd') {
        $text = "$($entry.Name)    <SUB-DIR>"; $style = 'File'
    } else {
        $text = "$($entry.Name)    $($entry.Size) B"; $style = 'File'
    }
    Write-Ui ($geometry.X + 1) $script:Layout.InfoRow (Get-CenteredText $text $geometry.Inner) $style
}

function Draw-PanelEntries {
    param([string]$Panel)
    Ensure-PanelPage $Panel
    $geometry = Get-PanelGeometry $Panel
    for ($slot = 0; $slot -lt $geometry.Capacity; $slot++) { Draw-PanelSlot $Panel $slot }
    Draw-PanelInfo $Panel
}

function Draw-CommandLine {
    $path = if ($script:ActivePanel -eq 'L') { Get-DisplayLocalPath } else { "MK61s:$($script:RemotePath)" }
    $maxPrompt = [Math]::Max(8, [int][Math]::Floor($script:Layout.Width / 2.0) - 2)
    if ($path.Length -gt $maxPrompt) { $path = '…' + $path.Substring($path.Length - $maxPrompt + 1) }
    $prompt = "$path> "
    $inputWidth = [Math]::Max(1, $script:Layout.Width - $prompt.Length)
    $offset = if ($script:CommandCursor -ge $inputWidth) {
        $script:CommandCursor - $inputWidth + 1
    } else { 0 }
    $length = [Math]::Min($inputWidth, [Math]::Max(0, $script:CommandText.Length - $offset))
    $shown = if ($length -gt 0) { $script:CommandText.Substring($offset, $length) } else { '' }
    Write-Ui $script:Layout.X $script:Layout.CommandRow ($prompt + (Get-FittedText $shown $inputWidth)) 'Command'
    $cursor = [Math]::Min($inputWidth - 1, $script:CommandCursor - $offset)
    Set-UiPosition ($script:Layout.X + $prompt.Length + $cursor) $script:Layout.CommandRow
    Set-UiCursorVisible $true
}

function Draw-FunctionBar {
    $labels = @('Help','','View','','Copy','RenMov','Mkdir','Delete','Info','Quit')
    $base = [int][Math]::Floor($script:Layout.Width / 10.0)
    $extra = $script:Layout.Width % 10
    $x = $script:Layout.X
    for ($index = 0; $index -lt 10; $index++) {
        $width = $base + $(if ($index -lt $extra) { 1 } else { 0 })
        $number = [string]($index + 1)
        Write-Ui $x $script:Layout.FunctionRow $number 'FunctionNumber'
        [Console]::Write($script:Styles.FunctionLabel +
            (Get-FittedText $labels[$index] ($width - $number.Length)))
        $x += $width
    }
}

function Draw-Screen {
    param([switch]$ClearOutside)
    Update-Layout
    Set-UiCursorVisible $false
    if ($ClearOutside) {
        Set-UiStyle 'Outside'
        try { [Console]::Clear() } catch { [Console]::Write("$($script:Escape)[2J$($script:Escape)[H") }
    }
    [Console]::Write("$($script:Escape)[?2026h")
    for ($row = $script:Layout.Y; $row -lt $script:Layout.Y + $script:Layout.Height; $row++) {
        Write-Ui $script:Layout.X $row (' ' * $script:Layout.Width) 'Panel'
    }
    Draw-PanelFrame 'L'; Draw-PanelFrame 'R'
    Draw-PanelEntries 'L'; Draw-PanelEntries 'R'
    Draw-FunctionBar
    Draw-CommandLine
    [Console]::Write("$($script:Escape)[?2026l")
}

function Draw-SelectionDelta {
    param([string]$Panel, [int]$OldIndex, [int]$OldPage)
    $geometry = Get-PanelGeometry $Panel
    Ensure-PanelPage $Panel
    $state = $script:Panels[$Panel]
    if ($state.Page -ne $OldPage) { Draw-PanelEntries $Panel; return }
    $oldSlot = $OldIndex - $OldPage
    if ($oldSlot -ge 0 -and $oldSlot -lt $geometry.Capacity) { Draw-PanelSlot $Panel $oldSlot }
    $newSlot = $state.Selected - $state.Page
    if ($newSlot -ge 0 -and $newSlot -lt $geometry.Capacity) { Draw-PanelSlot $Panel $newSlot }
    Draw-PanelInfo $Panel
}

function Move-PanelSelection {
    param([string]$Direction)
    $panel = $script:ActivePanel
    $state = $script:Panels[$panel]
    if ($state.Entries.Count -eq 0) { return }
    $geometry = Get-PanelGeometry $panel
    $old = $state.Selected; $oldPage = $state.Page; $selected = $old
    switch ($Direction) {
        'up' { $selected-- }
        'down' { $selected++ }
        'left' { $selected -= $script:Layout.ListRows }
        'right' { $selected += $script:Layout.ListRows }
        'home' { $selected = 0 }
        'end' { $selected = $state.Entries.Count - 1 }
        'pgup' { $selected -= $geometry.Capacity }
        'pgdn' { $selected += $geometry.Capacity }
    }
    $selected = [Math]::Max(0, [Math]::Min($selected, $state.Entries.Count - 1))
    if ($selected -eq $old) { return }
    $state.Selected = $selected
    Draw-SelectionDelta $panel $old $oldPage
}

function Switch-ActivePanel {
    $old = $script:ActivePanel
    $oldState = $script:Panels[$old]
    $script:ActivePanel = if ($old -eq 'L') { 'R' } else { 'L' }
    $newState = $script:Panels[$script:ActivePanel]
    Draw-PanelTop $old; Draw-PanelTop $script:ActivePanel
    Draw-SelectionDelta $old $oldState.Selected $oldState.Page
    Draw-SelectionDelta $script:ActivePanel $newState.Selected $newState.Page
    Draw-CommandLine
}

function Get-UiKeyName {
    param([ConsoleKeyInfo]$Key)
    $script:KeyChar = $Key.KeyChar
    if (($Key.Modifiers -band [ConsoleModifiers]::Control) -ne 0) {
        switch ($Key.Key) {
            'O' { return 'console' }
            'R' { return 'refresh' }
            'P' { return 'history-up' }
            'N' { return 'history-down' }
            'U' { return 'clear-line' }
        }
    }
    switch ($Key.Key) {
        'UpArrow' { return 'up' }; 'DownArrow' { return 'down' }
        'LeftArrow' { return 'left' }; 'RightArrow' { return 'right' }
        'Home' { return 'home' }; 'End' { return 'end' }
        'PageUp' { return 'pgup' }; 'PageDown' { return 'pgdn' }
        'Insert' { return 'insert' }; 'Delete' { return 'delete' }
        'Escape' { return 'esc' }; 'Enter' { return 'enter' }
        'Tab' { return 'tab' }; 'Backspace' { return 'backspace' }
        'Spacebar' { return 'space' }
        'F1' { return 'f1' }; 'F2' { return 'f2' }; 'F3' { return 'f3' }
        'F4' { return 'f4' }; 'F5' { return 'f5' }; 'F6' { return 'f6' }
        'F7' { return 'f7' }; 'F8' { return 'f8' }; 'F9' { return 'f9' }
        'F10' { return 'f10' }
    }
    if (-not [char]::IsControl($Key.KeyChar)) { return 'char' }
    return 'ignore'
}

function Read-UiKey {
    return Get-UiKeyName ([Console]::ReadKey($true))
}

function Get-DialogGeometry {
    param([int]$Width, [int]$Height)
    $width = [Math]::Min($Width, $script:Layout.Width - 6)
    $height = [Math]::Min($Height, $script:Layout.Height - 4)
    return [pscustomobject]@{
        X = $script:Layout.X + [int][Math]::Floor(($script:Layout.Width - $width) / 2.0)
        Y = $script:Layout.Y + [int][Math]::Floor(($script:Layout.Height - $height - 1) / 2.0)
        Width = $width; Height = $height
    }
}

function Draw-DialogFrame {
    param([string]$Title, [int]$Width = 66, [int]$Height = 9)
    Set-UiCursorVisible $false
    $script:Dialog = Get-DialogGeometry $Width $Height
    $d = $script:Dialog
    for ($row = $d.Y + 1; $row -lt $d.Y + $d.Height; $row++) {
        Write-Ui ($d.X + $d.Width) $row '  ' 'Shadow'
    }
    Write-Ui ($d.X + 2) ($d.Y + $d.Height) (' ' * $d.Width) 'Shadow'
    $label = ' ' + (Get-ClippedText $Title ($d.Width - 8)) + ' '
    $rest = [Math]::Max(0, $d.Width - 2 - $label.Length)
    $left = [int][Math]::Floor($rest / 2.0)
    Write-Ui $d.X $d.Y ('╔' + ('═' * $left)) 'DialogBorder'
    [Console]::Write($script:Styles.DialogTitle + $label + $script:Styles.DialogBorder +
        ('═' * ($rest - $left)) + '╗')
    for ($row = $d.Y + 1; $row -lt $d.Y + $d.Height - 1; $row++) {
        Write-Ui $d.X $row ('║' + (' ' * ($d.Width - 2)) + '║') 'DialogBorder'
        Write-Ui ($d.X + 1) $row (' ' * ($d.Width - 2)) 'Dialog'
    }
    Write-Ui $d.X ($d.Y + $d.Height - 1) ('╚' + ('═' * ($d.Width - 2)) + '╝') 'DialogBorder'
}

function Draw-DialogButtons {
    param([string]$OkLabel, [string]$CancelLabel = '', [string]$Focus = 'ok')
    $d = $script:Dialog
    $ok = "[ $OkLabel ]"
    $cancel = if ([string]::IsNullOrEmpty($CancelLabel)) { '' } else { "[ $CancelLabel ]" }
    $total = $ok.Length + $(if ($cancel.Length -gt 0) { $cancel.Length + 4 } else { 0 })
    $x = $d.X + [int][Math]::Floor(($d.Width - $total) / 2.0)
    Write-Ui $x ($d.Y + $d.Height - 3) $ok $(if ($Focus -eq 'ok') { 'DialogButtonHot' } else { 'DialogButton' })
    if ($cancel.Length -gt 0) {
        [Console]::Write($script:Styles.Dialog + '    ' +
            $script:Styles[$(if ($Focus -eq 'cancel') { 'DialogButtonHot' } else { 'DialogButton' })] + $cancel)
    }
}

function Split-WrappedUiText {
    param([string]$Text, [int]$Width)
    $result = New-Object 'System.Collections.Generic.List[string]'
    foreach ($source in @([regex]::Split([string]$Text, "\r?\n"))) {
        $remaining = $source
        if ($remaining.Length -eq 0) { $result.Add(''); continue }
        while ($remaining.Length -gt $Width) {
            $split = $remaining.LastIndexOf(' ', $Width - 1, $Width)
            if ($split -le 0) { $split = $Width }
            $result.Add($remaining.Substring(0, $split).TrimEnd())
            $remaining = $remaining.Substring($split).TrimStart()
        }
        $result.Add($remaining)
    }
    return $result.ToArray()
}

function Show-InputDialog {
    param([string]$Title, [string]$Prompt, [string]$Initial = '', [string]$OkLabel = 'OK')
    $value = $Initial; $cursor = $value.Length
    Draw-DialogFrame $Title 66 9
    $d = $script:Dialog
    $inputX = $d.X + 3; $inputY = $d.Y + 4; $inputWidth = $d.Width - 6
    Write-Ui $inputX ($d.Y + 2) (Get-FittedText $Prompt $inputWidth) 'Dialog'
    Draw-DialogButtons $OkLabel 'Cancel' 'ok'
    while ($true) {
        $offset = if ($cursor -ge $inputWidth) { $cursor - $inputWidth + 1 } else { 0 }
        $length = [Math]::Min($inputWidth, [Math]::Max(0, $value.Length - $offset))
        $shown = if ($length -gt 0) { $value.Substring($offset, $length) } else { '' }
        Write-Ui $inputX $inputY (Get-FittedText $shown $inputWidth) 'DialogInput'
        Set-UiPosition ($inputX + [Math]::Min($inputWidth - 1, $cursor - $offset)) $inputY
        Set-UiCursorVisible $true
        $key = Read-UiKey
        switch ($key) {
            'esc' { Set-UiCursorVisible $false; Draw-Screen; return [pscustomobject]@{ Cancelled=$true; Value='' } }
            'f10' { Set-UiCursorVisible $false; Draw-Screen; return [pscustomobject]@{ Cancelled=$true; Value='' } }
            'enter' { Set-UiCursorVisible $false; Draw-Screen; return [pscustomobject]@{ Cancelled=$false; Value=$value } }
            'left' { if ($cursor -gt 0) { $cursor-- } }
            'right' { if ($cursor -lt $value.Length) { $cursor++ } }
            'home' { $cursor = 0 }
            'end' { $cursor = $value.Length }
            'backspace' {
                if ($cursor -gt 0) { $value = $value.Remove($cursor - 1, 1); $cursor-- }
            }
            'delete' { if ($cursor -lt $value.Length) { $value = $value.Remove($cursor, 1) } }
            'clear-line' { $value = ''; $cursor = 0 }
            'space' { $value = $value.Insert($cursor, ' '); $cursor++ }
            'char' { $value = $value.Insert($cursor, [string]$script:KeyChar); $cursor++ }
        }
    }
}

function Show-ConfirmDialog {
    param([string]$Text, [string]$Title = 'Confirm')
    $lines = @(Split-WrappedUiText $Text 54)
    Draw-DialogFrame $Title 66 (7 + $lines.Count)
    $d = $script:Dialog
    for ($index = 0; $index -lt $lines.Count; $index++) {
        Write-Ui ($d.X + 3) ($d.Y + 2 + $index) (Get-CenteredText $lines[$index] ($d.Width - 6)) 'Dialog'
    }
    $focus = 'cancel'
    while ($true) {
        Draw-DialogButtons 'Yes' 'No' $focus
        $key = Read-UiKey
        if ($key -in @('left','right','tab')) { $focus = if ($focus -eq 'ok') { 'cancel' } else { 'ok' }; continue }
        if ($key -eq 'char' -and $script:KeyChar -match '[yYдД]') { Draw-Screen; return $true }
        if ($key -eq 'enter') { $answer = $focus -eq 'ok'; Draw-Screen; return $answer }
        if ($key -in @('esc','f10') -or ($key -eq 'char' -and $script:KeyChar -match '[nNтТ]')) {
            Draw-Screen; return $false
        }
    }
}

function Show-Alert {
    param([string]$Title, [string]$Text)
    $lines = @(Split-WrappedUiText $Text 54)
    Draw-DialogFrame $Title 66 (7 + $lines.Count)
    $d = $script:Dialog
    for ($index = 0; $index -lt $lines.Count; $index++) {
        Write-Ui ($d.X + 3) ($d.Y + 2 + $index) (Get-CenteredText $lines[$index] ($d.Width - 6)) 'Dialog'
    }
    Draw-DialogButtons 'OK' '' 'ok'
    while ((Read-UiKey) -notin @('enter','space','esc','f10')) {}
    Draw-Screen
}

function Show-Lines {
    param([string]$Title, [string[]]$Lines)
    if ($null -eq $Lines -or $Lines.Count -eq 0) { $Lines = @('(пусто)') }
    $top = 0
    $inner = $script:Layout.Width - 2
    $contentStart = $script:Layout.Y + 1
    $bottom = $script:Layout.Y + $script:Layout.Height - 2
    $statusRow = $bottom - 1
    $available = $statusRow - $contentStart
    $maxTop = [Math]::Max(0, $Lines.Count - $available)
    Set-UiCursorVisible $false
    while ($true) {
        $label = ' ' + (Get-ClippedText $Title ($script:Layout.Width - 8)) + ' '
        $rest = [Math]::Max(0, $inner - $label.Length)
        $left = [int][Math]::Floor($rest / 2.0)
        Write-Ui $script:Layout.X $script:Layout.Y ('╔' + ('═' * $left)) 'Border'
        [Console]::Write($script:Styles.Menu + $label + $script:Styles.Border + ('═' * ($rest - $left)) + '╗')
        for ($row = 0; $row -lt $available; $row++) {
            $index = $top + $row
            $line = if ($index -lt $Lines.Count) { $Lines[$index] } else { '' }
            Write-Ui $script:Layout.X ($contentStart + $row) '║' 'Border'
            [Console]::Write($script:Styles.File + (Get-FittedText " $line" $inner) + $script:Styles.Border + '║')
        }
        $shownEnd = [Math]::Min($Lines.Count, $top + $available)
        Write-Ui $script:Layout.X $statusRow '║' 'Border'
        [Console]::Write($script:Styles.Status +
            (Get-CenteredText "Lines $($top + 1)–$shownEnd / $($Lines.Count)  ·  Esc/F3 — close" $inner) +
            $script:Styles.Border + '║')
        Write-Ui $script:Layout.X $bottom ('╚' + ('═' * $inner) + '╝') 'Border'
        Draw-FunctionBar
        $key = Read-UiKey
        switch ($key) {
            'up' { if ($top -gt 0) { $top-- } }
            'down' { if ($top + $available -lt $Lines.Count) { $top++ } }
            'pgup' { $top = [Math]::Max(0, $top - $available) }
            'pgdn' { $top = [Math]::Min($maxTop, $top + $available) }
            'home' { $top = 0 }
            'end' { $top = $maxTop }
            { $_ -in @('esc','f3','enter','f10') } { Draw-Screen; return }
        }
    }
}

function Show-Help {
    $text = @'
MKC — файловый менеджер MK61s

Tab          сменить активную панель
Стрелки      выбрать файл; PgUp/PgDn — страница
Enter        войти в каталог
Backspace    перейти в родительский каталог
Space/Ins    отметить несколько объектов
F3           текст, HEX и WBMP в шрифте Брайля
F5           копировать между компьютером и калькулятором
F6           переименовать или переместить в активной панели
F7           создать каталог
F8           удалить с подтверждением
F9           сведения о памяти калькулятора
F10          выход
Ctrl-R       обновить обе панели
Ctrl-O       повторно показать последний вывод MK61s

Командная строка работает в активной панели: слева команда выполняется через
cmd.exe, справа — терминалом MK61s с выводом внутри MKC. Серые файлы нельзя
загрузить на калькулятор, но можно просмотреть, переименовать или удалить.
FOCAL.MOD, BASIC.MOD и WBMP.MOD загружаются только в корень под этими именами.
'@
    Show-Lines 'Помощь' @($text -split "`r?`n")
}

function Set-CommandText {
    param([string]$Text)
    $script:CommandText = $Text
    $script:CommandCursor = $Text.Length
}

function Reset-CommandHistoryNavigation {
    $script:CommandHistoryIndex = -1
    $script:CommandHistoryDraft = ''
}

function Insert-CommandText {
    param([string]$Text)
    $script:CommandText = $script:CommandText.Insert($script:CommandCursor, $Text)
    $script:CommandCursor += $Text.Length
    Reset-CommandHistoryNavigation
}

function Remove-CommandCharacterBack {
    if ($script:CommandCursor -le 0) { return }
    $script:CommandText = $script:CommandText.Remove($script:CommandCursor - 1, 1)
    $script:CommandCursor--
    Reset-CommandHistoryNavigation
}

function Remove-CommandCharacter {
    if ($script:CommandCursor -ge $script:CommandText.Length) { return }
    $script:CommandText = $script:CommandText.Remove($script:CommandCursor, 1)
    Reset-CommandHistoryNavigation
}

function Add-CommandHistory {
    param([string]$Command)
    if ([string]::IsNullOrEmpty($Command)) { return }
    if ($script:CommandHistory.Count -eq 0 -or
        $script:CommandHistory[$script:CommandHistory.Count - 1] -ne $Command) {
        $script:CommandHistory += $Command
    }
    Reset-CommandHistoryNavigation
}

function Move-CommandHistory {
    param([string]$Direction)
    if ($script:CommandHistory.Count -eq 0) { return }
    if ($script:CommandHistoryIndex -lt 0) {
        $script:CommandHistoryDraft = $script:CommandText
        if ($Direction -ne 'previous') { return }
        $script:CommandHistoryIndex = $script:CommandHistory.Count - 1
    } elseif ($Direction -eq 'previous') {
        if ($script:CommandHistoryIndex -gt 0) { $script:CommandHistoryIndex-- }
    } else {
        $script:CommandHistoryIndex++
        if ($script:CommandHistoryIndex -ge $script:CommandHistory.Count) {
            $script:CommandHistoryIndex = -1
            Set-CommandText $script:CommandHistoryDraft
            return
        }
    }
    Set-CommandText $script:CommandHistory[$script:CommandHistoryIndex]
}

function Invoke-LocalPanelCommand {
    param([string]$Command)
    Set-UiStyle 'Outside'
    Set-UiCursorVisible $true
    if ($script:ScreenActive) { [Console]::Write("$($script:Escape)[?1049l") }
    [Console]::WriteLine()
    [Console]::WriteLine("$(Get-DisplayLocalPath)> $Command")
    $oldLocation = (Get-Location).Path
    $exitCode = 1
    try {
        Set-Location -LiteralPath $script:LocalPath
        $cmd = Resolve-Executable 'cmd.exe'
        if (-not [string]::IsNullOrEmpty($cmd)) {
            & $cmd /d /s /c $Command
        } else {
            $shell = Resolve-Executable '/bin/sh'
            if ([string]::IsNullOrEmpty($shell)) { throw 'cmd.exe не найден' }
            & $shell -lc $Command
        }
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        $exitCode = 1
    } finally {
        Set-Location -LiteralPath $oldLocation
    }
    $message = if ($exitCode -eq 0) { 'Enter — вернуться в MKC' }
        else { "Код завершения: $exitCode · Enter — вернуться в MKC" }
    [Console]::WriteLine()
    [Console]::Write("[$message]")
    [void][Console]::ReadLine()
    if ($script:ScreenActive) { [Console]::Write("$($script:Escape)[?1049h") }
    Load-LocalPanel
    Draw-Screen -ClearOutside
}

function Test-RemotePromptLine {
    param([string]$Line)
    if ($Line -match '^(/.*)> $') {
        $script:RemoteCapturePath = $Matches[1]
        return $true
    }
    if ($Line -eq '...> ') { return $true }
    return $false
}

function Invoke-RemoteCaptureCommand {
    param([string]$Command)
    $lines = New-Object 'System.Collections.Generic.List[string]'
    $script:RemoteCapturePath = $script:RemotePath
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        switch ($Command) {
            'pwd' { $lines.Add($script:RemotePath) }
            'help' { $lines.Add('Mock MK61s terminal'); $lines.Add('Commands are routed to the right panel.') }
            default { $lines.Add("Mock MK61s: $Command") }
        }
        return [pscustomobject]@{ Success = $true; Lines = $lines.ToArray() }
    }
    if ([Text.Encoding]::UTF8.GetByteCount($Command) -gt 96) {
        $script:StatusText = 'Команда MK61s длиннее безопасных 96 байт'
        return [pscustomobject]@{ Success = $false; Lines = @($script:StatusText) }
    }
    if (-not (Send-RemoteLine $Command)) {
        return [pscustomobject]@{ Success = $false; Lines = @($script:StatusText) }
    }
    Start-Sleep -Milliseconds 50
    if (-not (Send-RemoteLine '')) {
        return [pscustomobject]@{ Success = $false; Lines = @($script:StatusText) }
    }
    $sawEcho = $false
    for ($count = 0; $count -lt 2000; $count++) {
        if (-not (Read-SerialLine 8000)) {
            $script:StatusText = 'Таймаут ответа терминала MK61s'
            $lines.Add('[' + $script:StatusText + ']')
            return [pscustomobject]@{ Success = $false; Lines = $lines.ToArray() }
        }
        $line = $script:SerialLine
        if ($sawEcho -and (Test-RemotePromptLine $line)) {
            return [pscustomobject]@{ Success = $true; Lines = $lines.ToArray() }
        }
        if ($line -match '^(/.*|\.\.\.)> (.*)$') { $line = $Matches[2] }
        if (-not $sawEcho) {
            if ($line -eq $Command) { $sawEcho = $true; continue }
            if (Test-RemotePromptLine $line) { continue }
            $sawEcho = $true
        }
        $lines.Add($line)
    }
    $script:StatusText = 'Слишком длинный вывод терминала MK61s'
    $lines.Add('[' + $script:StatusText + ']')
    return [pscustomobject]@{ Success = $false; Lines = $lines.ToArray() }
}

function Invoke-RemotePanelCommand {
    param([string]$Command)
    $script:LastRemoteTitle = "MK61s · $Command"
    $shown = New-Object 'System.Collections.Generic.List[string]'
    $ok = $true
    if ([string]::IsNullOrEmpty($script:MockRoot)) {
        $sync = Invoke-RemoteCaptureCommand ('cd ' + (Format-RemoteQuotedPath $script:RemotePath))
        if (-not $sync.Success) {
            $shown.Add("MK61s:$($script:RemotePath)> $Command")
            foreach ($line in $sync.Lines) { $shown.Add($line) }
            $ok = $false
        }
    }
    if ($ok) {
        $capture = Invoke-RemoteCaptureCommand $Command
        $shown.Add("MK61s:$($script:RemotePath)> $Command")
        foreach ($line in $capture.Lines) { $shown.Add($line) }
        $ok = $capture.Success
        if ($ok -and $script:RemoteCapturePath.StartsWith('/')) {
            $script:RemotePath = Normalize-RemotePath '/' $script:RemoteCapturePath
            [void](Load-RemotePanel)
            Save-Config
        }
    }
    if ($shown.Count -eq 1) { $shown.Add('(команда выполнена без вывода)') }
    $script:LastRemoteOutput = @($shown.ToArray())
    Show-Lines $script:LastRemoteTitle $script:LastRemoteOutput
}

function Show-LastTerminalOutput {
    if ($script:LastRemoteOutput.Count -gt 0) {
        Show-Lines $script:LastRemoteTitle $script:LastRemoteOutput
    } else {
        Show-Alert 'Терминал MK61s' 'Команды в правой панели ещё не выполнялись.'
    }
}

function Invoke-CommandLine {
    $command = $script:CommandText
    if ([string]::IsNullOrWhiteSpace($command)) { return }
    $panel = $script:ActivePanel
    Add-CommandHistory $command
    Set-CommandText ''
    Draw-CommandLine
    if ($panel -eq 'L') { Invoke-LocalPanelCommand $command }
    else { Invoke-RemotePanelCommand $command }
}

function Read-WbmpMultiByteInteger {
    param([byte[]]$Bytes, [ref]$Offset)
    [long]$value = 0
    for ($count = 0; $count -lt 5; $count++) {
        if ($Offset.Value -ge $Bytes.Length) { throw 'обрезанный заголовок' }
        $octet = $Bytes[$Offset.Value]
        $Offset.Value++
        $value = $value * 128 + ($octet -band 127)
        if (($octet -band 128) -eq 0) { return $value }
    }
    throw 'слишком большое поле размера'
}

function Read-Wbmp {
    param([string]$Path)
    try { [byte[]]$bytes = [IO.File]::ReadAllBytes($Path) }
    catch { throw 'файл не читается' }
    if ($bytes.Length -lt 4) { throw 'обрезанный заголовок' }
    if ($bytes[0] -ne 0) { throw 'поддерживается только Type 0' }
    if (($bytes[1] -band 159) -ne 0) { throw 'некорректный fixed header' }
    $offset = 2
    $width = Read-WbmpMultiByteInteger $bytes ([ref]$offset)
    $height = Read-WbmpMultiByteInteger $bytes ([ref]$offset)
    if ($width -le 0 -or $height -le 0) { throw 'нулевой размер изображения' }
    $rowBytes = [int][Math]::Ceiling($width / 8.0)
    $expected = $offset + $rowBytes * $height
    if ($bytes.Length -ne $expected) {
        throw "размер файла $($bytes.Length) байт, ожидалось $expected"
    }
    $usedBits = $width -band 7
    if ($usedBits -ne 0) {
        $paddingMask = (1 -shl (8 - $usedBits)) - 1
        for ($row = 0; $row -lt $height; $row++) {
            $last = $bytes[$offset + $row * $rowBytes + $rowBytes - 1]
            if (($last -band $paddingMask) -ne 0) { throw 'ненулевые хвостовые биты строки' }
        }
    }
    return [pscustomobject]@{
        Bytes = $bytes; Offset = $offset; Width = [int]$width; Height = [int]$height; RowBytes = $rowBytes
    }
}

function Test-WbmpDarkPixel {
    param([object]$Image, [int]$X, [int]$Y)
    if ($X -lt 0 -or $X -ge $Image.Width -or $Y -lt 0 -or $Y -ge $Image.Height) { return $false }
    $value = $Image.Bytes[$Image.Offset + $Y * $Image.RowBytes + ($X -shr 3)]
    $mask = 128 -shr ($X -band 7)
    return ($value -band $mask) -eq 0
}

function Test-WbmpDarkBlock {
    param([object]$Image, [int]$StartX, [int]$StartY, [int]$Size)
    for ($y = $StartY; $y -lt [Math]::Min($Image.Height, $StartY + $Size); $y++) {
        for ($x = $StartX; $x -lt [Math]::Min($Image.Width, $StartX + $Size); $x++) {
            if (Test-WbmpDarkPixel $Image $x $y) { return $true }
        }
    }
    return $false
}

function Convert-WbmpToBrailleLines {
    param([string]$Path, [int]$MaxColumns = 0, [int]$MaxRows = 0)
    $image = Read-Wbmp $Path
    if ($MaxColumns -le 0) {
        $MaxColumns = if ($null -ne $script:Layout) { [Math]::Max(8, $script:Layout.Width - 6) } else { 74 }
    }
    if ($MaxRows -le 0) {
        $MaxRows = if ($null -ne $script:Layout) { [Math]::Max(2, $script:Layout.Height - 7) } else { 17 }
    }
    $scale = [Math]::Max(1, [int][Math]::Ceiling($image.Width / [double]($MaxColumns * 2)))
    $scale = [Math]::Max($scale, [int][Math]::Ceiling($image.Height / [double]($MaxRows * 4)))
    $columns = [int][Math]::Ceiling($image.Width / [double]($scale * 2))
    $rows = [int][Math]::Ceiling($image.Height / [double]($scale * 4))
    $suffix = if ($scale -eq 1) { '' } else { " · 1:$scale" }
    $result = New-Object 'System.Collections.Generic.List[string]'
    $result.Add("$($image.Width)×$($image.Height) · Braille preview$suffix")
    $result.Add('')
    $dotX = @(0,0,0,1,1,1,0,1)
    $dotY = @(0,1,2,0,1,2,3,3)
    $bits = @(1,2,4,8,16,32,64,128)
    for ($row = 0; $row -lt $rows; $row++) {
        $builder = New-Object Text.StringBuilder
        for ($column = 0; $column -lt $columns; $column++) {
            $dots = 0
            for ($dot = 0; $dot -lt 8; $dot++) {
                $x = ($column * 2 + $dotX[$dot]) * $scale
                $y = ($row * 4 + $dotY[$dot]) * $scale
                if (Test-WbmpDarkBlock $image $x $y $scale) { $dots = $dots -bor $bits[$dot] }
            }
            [void]$builder.Append([char](0x2800 + $dots))
        }
        $result.Add($builder.ToString())
    }
    return $result.ToArray()
}

function Convert-BytesToHexDumpLines {
    param([byte[]]$Bytes)
    $result = New-Object 'System.Collections.Generic.List[string]'
    for ($offset = 0; $offset -lt $Bytes.Length; $offset += 16) {
        $count = [Math]::Min(16, $Bytes.Length - $offset)
        $hex = New-Object Text.StringBuilder
        $ascii = New-Object Text.StringBuilder
        for ($index = 0; $index -lt 16; $index++) {
            if ($index -lt $count) {
                $byte = $Bytes[$offset + $index]
                [void]$hex.Append($byte.ToString('X2') + $(if ($index -eq 7) { '  ' } else { ' ' }))
                [void]$ascii.Append($(if ($byte -ge 32 -and $byte -le 126) { [char]$byte } else { '.' }))
            } else {
                [void]$hex.Append($(if ($index -eq 7) { '    ' } else { '   ' }))
            }
        }
        $result.Add(('{0:X8}  {1}|{2}|' -f $offset, $hex.ToString(), $ascii.ToString()))
    }
    if ($result.Count -eq 0) { $result.Add('00000000') }
    return $result.ToArray()
}

function Test-TextBytes {
    param([byte[]]$Bytes)
    if ($Bytes -contains 0) { return $false }
    try {
        $strict = New-Object Text.UTF8Encoding($false, $true)
        [void]$strict.GetString($Bytes)
        return $true
    } catch { return $false }
}

function Show-SelectedFile {
    $panel = $script:ActivePanel
    $entry = Get-SelectedEntry $panel
    if ($null -eq $entry -or $entry.Name -eq '..' -or $entry.Kind -eq 'd') {
        Show-Alert 'View' 'F3 открывает файлы, а не каталоги'
        return
    }
    if ($panel -eq 'L') { $source = Join-Path $script:LocalPath $entry.Name }
    else {
        $source = Join-Path $script:SessionDir 'view.bin'
        if (-not (Receive-RemoteFile (Join-RemotePath $script:RemotePath $entry.Name) $source)) {
            Show-Alert 'View' $script:StatusText
            return
        }
    }
    $lower = $entry.Name.ToLowerInvariant()
    if ($lower.EndsWith('.wbmp') -or $lower.EndsWith('.wbm')) {
        try { Show-Lines $entry.Name @(Convert-WbmpToBrailleLines $source) }
        catch { Show-Alert 'View' ('Некорректный WBMP: ' + $_.Exception.Message) }
        return
    }
    try { [byte[]]$bytes = [IO.File]::ReadAllBytes($source) }
    catch { Show-Alert 'View' $_.Exception.Message; return }
    if (-not ($lower.EndsWith('.fmk') -or $lower.EndsWith('.mod')) -and
        (Test-TextBytes $bytes)) {
        $text = [Text.Encoding]::UTF8.GetString($bytes)
        Show-Lines $entry.Name @([regex]::Split($text, "\r?\n") | Select-Object -First 400)
    } else {
        Show-Lines $entry.Name @(Convert-BytesToHexDumpLines $bytes)
    }
}

function Toggle-SelectedMark {
    $panel = $script:ActivePanel
    $state = $script:Panels[$panel]
    $entry = Get-SelectedEntry $panel
    if ($null -eq $entry -or $entry.Name -eq '..') { return }
    $entry.Marked = -not $entry.Marked
    $slot = $state.Selected - $state.Page
    Draw-PanelSlot $panel $slot
    Draw-PanelInfo $panel
    Move-PanelSelection 'down'
}

function Open-SelectedEntry {
    $panel = $script:ActivePanel
    $entry = Get-SelectedEntry $panel
    if ($null -eq $entry) { return }
    if ($entry.Kind -ne 'd') { Show-SelectedFile; return }
    if ($panel -eq 'L') {
        $target = if ($entry.Name -eq '..') { Get-LocalParent $script:LocalPath }
            else { Join-Path $script:LocalPath $entry.Name }
        if ([string]::IsNullOrEmpty($target) -or -not (Test-Path -LiteralPath $target -PathType Container)) {
            Show-Alert 'Open' "Нет каталога $target"
            return
        }
        $script:LocalPath = (Resolve-Path -LiteralPath $target).Path
        $script:Panels.L.Selected = 0
        Load-LocalPanel
    } else {
        $old = $script:RemotePath
        $script:RemotePath = if ($entry.Name -eq '..') { Get-RemoteParent $script:RemotePath }
            else { Normalize-RemotePath $script:RemotePath $entry.Name }
        $script:Panels.R.Selected = 0
        if (-not (Load-RemotePanel)) {
            $script:RemotePath = $old
            [void](Load-RemotePanel)
            Show-Alert 'Open' $script:StatusText
            return
        }
    }
    Save-Config
    Draw-Screen
}

function Open-ParentDirectory {
    if ($script:ActivePanel -eq 'L') {
        $parent = Get-LocalParent $script:LocalPath
        if (-not [string]::IsNullOrEmpty($parent)) {
            $script:LocalPath = $parent
            Load-LocalPanel
        }
    } else {
        if ($script:RemotePath -ne '/') {
            $script:RemotePath = Get-RemoteParent $script:RemotePath
            [void](Load-RemotePanel)
        }
    }
    Save-Config
    Draw-Screen
}

function Draw-CopyProgress {
    param([string]$Message, [long]$Current, [long]$Total)
    $percent = if ($Total -gt 0) { [int][Math]::Floor($Current * 100.0 / $Total) } else { 100 }
    $percent = [Math]::Max(0, [Math]::Min(100, $percent))
    if ($null -eq $script:Dialog -or $script:Dialog.Title -ne 'CopyProgress') {
        Draw-DialogFrame 'Copy' 66 9
        $script:Dialog | Add-Member -NotePropertyName Title -NotePropertyValue 'CopyProgress' -Force
    }
    $d = $script:Dialog
    $width = $d.Width - 10
    $filled = [int][Math]::Floor($width * $percent / 100.0)
    Write-Ui ($d.X + 3) ($d.Y + 2) (Get-CenteredText $Message ($d.Width - 6)) 'Dialog'
    Write-Ui ($d.X + 4) ($d.Y + 4) '[' 'Dialog'
    [Console]::Write($script:Styles.DialogButtonHot + (' ' * $filled) +
        $script:Styles.DialogInput + (' ' * ($width - $filled)) + $script:Styles.Dialog + ']')
    Write-Ui ($d.X + 3) ($d.Y + 6) (Get-CenteredText "$percent%" ($d.Width - 6)) 'Dialog'
}

function Invoke-CopyPlan {
    param([string]$Direction)
    [long]$completed = 0
    for ($index = 0; $index -lt $script:CopyPlan.Count; $index++) {
        $item = $script:CopyPlan[$index]
        $name = if ($Direction -eq 'L2R') { Split-Path -Leaf $item.Source }
            else { Split-Path -Leaf $item.Source.Replace('/', [IO.Path]::DirectorySeparatorChar) }
        Draw-CopyProgress "Копирую $($index + 1)/$($script:CopyPlan.Count): $name" $completed $script:CopyTotal
        if ($Direction -eq 'L2R') {
            if ($item.Kind -eq 'd') {
                if (-not (New-RemoteDirectory $item.Destination)) { return $false }
            } else {
                if (-not (Send-RemoteFile $item.Source $item.Destination)) { return $false }
                $completed += $item.Size
            }
        } else {
            if ($item.Kind -eq 'd') {
                try { [void](New-Item -ItemType Directory -Force -Path $item.Destination) }
                catch { $script:StatusText = "Не удалось создать $($item.Destination)"; return $false }
            } else {
                $parent = Split-Path -Parent $item.Destination
                try {
                    if (-not [string]::IsNullOrEmpty($parent)) {
                        [void](New-Item -ItemType Directory -Force -Path $parent)
                    }
                } catch { $script:StatusText = "Не удалось создать $parent"; return $false }
                if (-not (Receive-RemoteFile $item.Source $item.Destination)) { return $false }
                $completed += $item.Size
            }
        }
    }
    Draw-CopyProgress 'Копирование завершено' $script:CopyTotal $script:CopyTotal
    return $true
}

function Resolve-LocalInputPath {
    param([string]$Value)
    if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
    return [IO.Path]::GetFullPath((Join-Path $script:LocalPath $Value))
}

function Copy-SelectedEntries {
    $panel = $script:ActivePanel
    $indices = @(Get-ChosenIndices $panel)
    if ($indices.Count -eq 0) { Show-Alert 'Copy' 'Выберите файл или каталог'; return }
    if ($panel -eq 'L') {
        foreach ($index in $indices) {
            $entry = $script:Panels.L.Entries[$index]
            if (-not [string]::IsNullOrEmpty($entry.Reason)) {
                Show-Alert 'Copy' "Нельзя копировать $($entry.Name): $($entry.Reason)"
                return
            }
        }
        $default = if ($indices.Count -eq 1) {
            Join-RemotePath $script:RemotePath $script:Panels.L.Entries[$indices[0]].Name
        } else { $script:RemotePath }
        $answer = Show-InputDialog 'Copy' "Copy $($indices.Count) item(s) to MK61s:" $default 'Copy'
        if ($answer.Cancelled) { return }
        $target = Normalize-RemotePath $script:RemotePath $answer.Value
        Reset-CopyPlan
        if ($indices.Count -eq 1) {
            $entry = $script:Panels.L.Entries[$indices[0]]
            $source = Join-Path $script:LocalPath $entry.Name
            [void](Add-LocalTreeToPlan $source $target)
        } else {
            foreach ($index in $indices) {
                $entry = $script:Panels.L.Entries[$index]
                $source = Join-Path $script:LocalPath $entry.Name
                $destination = Join-RemotePath $target $entry.Name
                if (-not (Add-LocalTreeToPlan $source $destination)) { break }
            }
        }
        if (-not [string]::IsNullOrEmpty($script:PlanError)) {
            Show-Alert 'Copy' "Нельзя копировать: $($script:PlanError)"
            return
        }
        $script:Dialog = $null
        if (-not (Invoke-CopyPlan 'L2R')) {
            $errorText = $script:StatusText; Draw-Screen; Show-Alert 'Copy' $errorText; return
        }
        Clear-PanelMarks 'L'
        $script:StatusText = "Скопировано на MK61s: $($indices.Count)"
    } else {
        $default = if ($indices.Count -eq 1) {
            Join-Path $script:LocalPath $script:Panels.R.Entries[$indices[0]].Name
        } else { $script:LocalPath }
        $answer = Show-InputDialog 'Copy' "Copy $($indices.Count) item(s) to computer:" $default 'Copy'
        if ($answer.Cancelled) { return }
        try { $target = Resolve-LocalInputPath $answer.Value }
        catch { Show-Alert 'Copy' $_.Exception.Message; return }
        Reset-CopyPlan
        if ($indices.Count -eq 1) {
            $entry = $script:Panels.R.Entries[$indices[0]]
            $source = Join-RemotePath $script:RemotePath $entry.Name
            [void](Add-RemoteTreeToPlan $source $target $entry.Kind $entry.Size)
        } else {
            foreach ($index in $indices) {
                $entry = $script:Panels.R.Entries[$index]
                $added = Add-RemoteTreeToPlan (Join-RemotePath $script:RemotePath $entry.Name) `
                    (Join-Path $target $entry.Name) $entry.Kind $entry.Size
                if (-not $added) { break }
            }
        }
        if (-not [string]::IsNullOrEmpty($script:PlanError)) {
            Show-Alert 'Copy' "Нельзя копировать: $($script:PlanError)"
            return
        }
        $script:Dialog = $null
        if (-not (Invoke-CopyPlan 'R2L')) {
            $errorText = $script:StatusText; Draw-Screen; Show-Alert 'Copy' $errorText; return
        }
        Clear-PanelMarks 'R'
        $script:StatusText = "Скопировано на компьютер: $($indices.Count)"
    }
    $script:Dialog = $null
    Refresh-Panels
    Draw-Screen
}

function Rename-SelectedEntry {
    $panel = $script:ActivePanel
    $entry = Get-SelectedEntry $panel
    if ($null -eq $entry -or $entry.Name -eq '..') {
        Show-Alert 'Rename/Move' 'Нельзя переименовать ..'
        return
    }
    if ($panel -eq 'L') {
        $source = Join-Path $script:LocalPath $entry.Name
        $answer = Show-InputDialog 'Rename/Move' 'Rename or move to:' $source 'Move'
        if ($answer.Cancelled) { return }
        try {
            $destination = Resolve-LocalInputPath $answer.Value
            Move-Item -LiteralPath $source -Destination $destination -Force
        } catch { Show-Alert 'Rename/Move' ('Не удалось переместить: ' + $_.Exception.Message); return }
        Load-LocalPanel
    } else {
        $source = Join-RemotePath $script:RemotePath $entry.Name
        $answer = Show-InputDialog 'Rename/Move' 'Rename or move on MK61s to:' $source 'Move'
        if ($answer.Cancelled) { return }
        $destination = Normalize-RemotePath $script:RemotePath $answer.Value
        if (-not (Move-RemoteItem $source $destination)) { Show-Alert 'Rename/Move' $script:StatusText; return }
        [void](Load-RemotePanel)
    }
    Draw-Screen
}

function New-PanelDirectory {
    $answer = Show-InputDialog 'Make directory' 'Directory name:' 'New directory' 'Make'
    if ($answer.Cancelled) { return }
    if ([string]::IsNullOrWhiteSpace($answer.Value)) { Show-Alert 'Make directory' 'Имя каталога не задано'; return }
    if ($script:ActivePanel -eq 'L') {
        try {
            $destination = Resolve-LocalInputPath $answer.Value
            [void](New-Item -ItemType Directory -Path $destination)
            Load-LocalPanel
        } catch { Show-Alert 'Make directory' $_.Exception.Message; return }
    } else {
        $destination = Normalize-RemotePath $script:RemotePath $answer.Value
        if (-not (New-RemoteDirectory $destination)) { Show-Alert 'Make directory' $script:StatusText; return }
        [void](Load-RemotePanel)
    }
    Draw-Screen
}

function Remove-SelectedEntries {
    $panel = $script:ActivePanel
    $indices = @(Get-ChosenIndices $panel)
    if ($indices.Count -eq 0) { Show-Alert 'Delete' 'Выберите объект для удаления'; return }
    if (-not (Show-ConfirmDialog "Удалить безвозвратно: $($indices.Count) объект(ов)?" 'Delete')) { return }
    $failed = $false
    foreach ($index in $indices) {
        $entry = $script:Panels[$panel].Entries[$index]
        if ($panel -eq 'L') {
            $path = Join-Path $script:LocalPath $entry.Name
            try { Remove-Item -LiteralPath $path -Recurse -Force }
            catch { $failed = $true }
        } else {
            if (-not (Remove-RemoteItem (Join-RemotePath $script:RemotePath $entry.Name))) { $failed = $true }
        }
    }
    Refresh-Panels
    Draw-Screen
    if ($failed) { Show-Alert 'Delete' 'Часть объектов удалить не удалось' }
}

function Show-DeviceInfo {
    $lines = New-Object 'System.Collections.Generic.List[string]'
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        $lines.Add('Режим: тестовый каталог')
        $lines.Add("Путь: $($script:MockRoot)")
        try {
            $root = [IO.Path]::GetPathRoot($script:MockRoot)
            $drive = New-Object IO.DriveInfo($root)
            $lines.Add("Свободно: $($drive.AvailableFreeSpace) байт")
            $lines.Add("Всего: $($drive.TotalSize) байт")
        } catch {}
    } else {
        $lines.Add("Порт: $($script:Port)")
        $lines.Add('')
        if (-not (Send-RemoteLine 'df') -or -not (Send-RemoteLine 'ls "/"')) {
            Show-Alert 'Info' $script:StatusText
            return
        }
        for ($count = 0; $count -lt 10000; $count++) {
            if (-not (Read-SerialLine 10000)) { break }
            $line = $script:SerialLine
            if ($line -match '^(Flash:|Nodes:|Visible:|FAT12 cluster:|Settings:)') { $lines.Add($line) }
            if ($line -match ' entr(y|ies)\.$') { break }
        }
    }
    Show-Lines 'Устройство' $lines.ToArray()
}

function Invoke-MainLoop {
    while ($true) {
        $key = Read-UiKey
        switch ($key) {
            'up' { if ($script:CommandText.Length -gt 0) { Move-CommandHistory 'previous' } else { Move-PanelSelection 'up' } }
            'down' { if ($script:CommandText.Length -gt 0) { Move-CommandHistory 'next' } else { Move-PanelSelection 'down' } }
            'left' {
                if ($script:CommandText.Length -gt 0) { if ($script:CommandCursor -gt 0) { $script:CommandCursor-- } }
                else { Move-PanelSelection 'left' }
            }
            'right' {
                if ($script:CommandText.Length -gt 0) {
                    if ($script:CommandCursor -lt $script:CommandText.Length) { $script:CommandCursor++ }
                } else { Move-PanelSelection 'right' }
            }
            'home' { if ($script:CommandText.Length -gt 0) { $script:CommandCursor = 0 } else { Move-PanelSelection 'home' } }
            'end' { if ($script:CommandText.Length -gt 0) { $script:CommandCursor = $script:CommandText.Length } else { Move-PanelSelection 'end' } }
            'pgup' { if ($script:CommandText.Length -eq 0) { Move-PanelSelection 'pgup' } }
            'pgdn' { if ($script:CommandText.Length -eq 0) { Move-PanelSelection 'pgdn' } }
            'tab' { Switch-ActivePanel }
            'enter' { if ($script:CommandText.Length -gt 0) { Invoke-CommandLine } else { Open-SelectedEntry } }
            'backspace' { if ($script:CommandText.Length -gt 0) { Remove-CommandCharacterBack } else { Open-ParentDirectory } }
            'delete' { if ($script:CommandText.Length -gt 0) { Remove-CommandCharacter } }
            'space' { if ($script:CommandText.Length -gt 0) { Insert-CommandText ' ' } else { Toggle-SelectedMark } }
            'insert' { Toggle-SelectedMark }
            'history-up' { Move-CommandHistory 'previous' }
            'history-down' { Move-CommandHistory 'next' }
            'clear-line' { Set-CommandText ''; Reset-CommandHistoryNavigation }
            'refresh' { Refresh-Panels; Draw-Screen }
            'console' { Show-LastTerminalOutput }
            'f1' { Show-Help }
            'f3' { Show-SelectedFile }
            'f5' { Copy-SelectedEntries }
            'f6' { Rename-SelectedEntry }
            'f7' { New-PanelDirectory }
            'f8' { Remove-SelectedEntries }
            'f9' { Show-DeviceInfo }
            'f10' { return }
            'esc' { Set-CommandText ''; Reset-CommandHistoryNavigation }
            'char' { Insert-CommandText ([string]$script:KeyChar) }
        }
        Draw-CommandLine
    }
}

function Find-ArduinoCli {
    $resolved = Resolve-Executable $script:ArduinoCli
    if (-not [string]::IsNullOrEmpty($resolved)) { return $resolved }
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    if ($script:IsWindowsHost) {
        foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
            if ([string]::IsNullOrEmpty($base)) { continue }
            $candidates.Add((Join-Path $base 'Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'))
            $candidates.Add((Join-Path $base 'Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'))
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    return ''
}

function Enter-MkcTui {
    try { $script:OriginalCursorVisible = [Console]::CursorVisible } catch {}
    [Console]::Write("$($script:Escape)[?1049h")
    $script:ScreenActive = $true
    Set-UiCursorVisible $false
}

function Exit-MkcTui {
    if (-not $script:ScreenActive) { return }
    Set-UiStyle 'Outside'
    Set-UiCursorVisible $script:OriginalCursorVisible
    [Console]::Write("$($script:Escape)[?1049l")
    $script:ScreenActive = $false
}

function Invoke-MkcApplication {
    param([object[]]$Arguments)
    Load-Config
    if (-not (Parse-Arguments $Arguments)) { return 0 }
    if ($script:ListPortsOnly) {
        foreach ($port in @(Get-CdcPorts)) { [Console]::WriteLine($port) }
        return 0
    }
    if (-not [string]::IsNullOrEmpty($script:ClassifyOnly)) {
        $path = $script:ClassifyOnly
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path -Force
            $kind = if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { 'l' }
                elseif ($item.PSIsContainer) { 'd' } else { 'f' }
        } else { $kind = 'o' }
        $reason = Get-UnsupportedReason $path $kind
        if ([string]::IsNullOrEmpty($reason)) { [Console]::WriteLine('supported'); return 0 }
        [Console]::WriteLine("unsupported: $reason")
        return 1
    }
    if (-not (Test-Path -LiteralPath $script:LocalPath -PathType Container)) {
        throw "нет локального каталога: $($script:LocalPath)"
    }
    $script:LocalPath = (Resolve-Path -LiteralPath $script:LocalPath).Path
    if (-not [string]::IsNullOrEmpty($script:MockRoot)) {
        if (-not (Test-Path -LiteralPath $script:MockRoot -PathType Container)) {
            throw "нет тестового каталога: $($script:MockRoot)"
        }
        $script:MockRoot = (Resolve-Path -LiteralPath $script:MockRoot).Path
    } else {
        if (-not (Test-UseDirectSerialTransport)) {
            $foundCli = Find-ArduinoCli
            if ([string]::IsNullOrEmpty($foundCli)) {
                [Console]::WriteLine('MKC: arduino-cli не найден.')
                $entered = Read-Host 'Укажите полный путь к arduino-cli'
                $foundCli = Resolve-Executable $entered
                if ([string]::IsNullOrEmpty($foundCli)) { throw 'arduino-cli не найден' }
            }
            $script:ArduinoCli = $foundCli
        }
        if ([string]::IsNullOrEmpty($script:Port)) {
            $ports = @(Get-CdcPorts)
            if ($ports.Count -gt 0) { $script:Port = $ports[0] }
        }
        if ([string]::IsNullOrEmpty($script:Port)) {
            $script:Port = Read-Host 'MKC: устройство 0483:5740 не найдено. Укажите COM-порт'
        }
        if ([string]::IsNullOrWhiteSpace($script:Port)) { throw 'порт не указан' }
    }
    $script:SessionDir = Join-Path ([IO.Path]::GetTempPath()) ('mkc.' + [guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $script:SessionDir)
    if (-not (Start-Monitor)) {
        if ([string]::IsNullOrWhiteSpace($script:StatusText)) { throw "не удалось открыть $($script:Port)" }
        throw $script:StatusText
    }
    Enter-MkcTui
    Refresh-Panels
    Save-Config
    Draw-Screen -ClearOutside
    Invoke-MainLoop
    return 0
}

if ([Environment]::GetEnvironmentVariable('MKC_POWERSHELL_IMPORT_ONLY') -ne '1') {
    $exitCode = 1
    try { $exitCode = Invoke-MkcApplication $args }
    catch {
        Exit-MkcTui
        [Console]::Error.WriteLine('mkc: ' + $_.Exception.Message)
        $exitCode = 1
    } finally {
        Stop-Monitor
        Exit-MkcTui
        if (-not [string]::IsNullOrEmpty($script:SessionDir) -and
            (Test-Path -LiteralPath $script:SessionDir -PathType Container)) {
            Remove-Item -LiteralPath $script:SessionDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    exit $exitCode
}
