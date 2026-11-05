#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResidentElf,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [switch]$UsbText
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$HelpFileLimit = 1536
$HelpTagLength = 9
$HelpBodyLimit = 2 * ($HelpFileLimit - $HelpTagLength)

function Get-Le16 {
    param([byte[]]$Bytes, [int]$Offset)
    if ($Offset -lt 0 -or $Offset + 2 -gt $Bytes.Length) {
        throw 'truncated ELF 16-bit field'
    }
    return [uint16]([uint16]$Bytes[$Offset] -bor
        ([uint16]$Bytes[$Offset + 1] -shl 8))
}

function Get-Le32 {
    param([byte[]]$Bytes, [int]$Offset)
    if ($Offset -lt 0 -or $Offset + 4 -gt $Bytes.Length) {
        throw 'truncated ELF 32-bit field'
    }
    return [uint32]([uint32]$Bytes[$Offset] -bor
        ([uint32]$Bytes[$Offset + 1] -shl 8) -bor
        ([uint32]$Bytes[$Offset + 2] -shl 16) -bor
        ([uint32]$Bytes[$Offset + 3] -shl 24))
}

function Get-Section {
    param([byte[]]$Bytes, [uint32]$Table, [uint16]$EntrySize,
          [uint16]$Count, [int]$Index)
    if ($Index -lt 0 -or $Index -ge $Count) {
        throw 'ELF section index is out of range'
    }
    [uint64]$offset = [uint64]$Table + [uint64]$Index * $EntrySize
    if ($EntrySize -ne 40 -or $offset + 40 -gt $Bytes.Length) {
        throw 'truncated ELF section table'
    }
    return [pscustomobject]@{
        Name = Get-Le32 $Bytes ([int]$offset)
        Type = Get-Le32 $Bytes ([int]$offset + 4)
        Flags = Get-Le32 $Bytes ([int]$offset + 8)
        Address = Get-Le32 $Bytes ([int]$offset + 12)
        Offset = Get-Le32 $Bytes ([int]$offset + 16)
        Size = Get-Le32 $Bytes ([int]$offset + 20)
        Link = Get-Le32 $Bytes ([int]$offset + 24)
        Info = Get-Le32 $Bytes ([int]$offset + 28)
        Alignment = Get-Le32 $Bytes ([int]$offset + 32)
        EntrySize = Get-Le32 $Bytes ([int]$offset + 36)
    }
}

function Get-BytesSlice {
    param([byte[]]$Bytes, [uint32]$Offset, [uint32]$Size)
    if ($Offset -gt $Bytes.Length -or $Size -gt $Bytes.Length - $Offset) {
        throw 'truncated ELF section'
    }
    $result = [byte[]]::new([int]$Size)
    if ($Size -gt 0) {
        [Array]::Copy($Bytes, [int]$Offset, $result, 0, [int]$Size)
    }
    return $result
}

function Get-SectionName {
    param([byte[]]$Names, [uint32]$Offset)
    if ($Offset -ge $Names.Length) { throw 'invalid ELF section name' }
    $end = [int]$Offset
    while ($end -lt $Names.Length -and $Names[$end] -ne 0) { $end++ }
    if ($end -ge $Names.Length) { throw 'unterminated ELF section name' }
    return [Text.Encoding]::ASCII.GetString(
        $Names, [int]$Offset, $end - [int]$Offset)
}

function Convert-M8ToUtf8 {
    param([byte[]]$Bytes)
    $special = @{
        0x0E = [char]0x2190; 0x0F = [char]0x2192
        0x10 = [char]0x2191; 0x11 = [char]0x2193
        0x12 = [char]0x03C0; 0x13 = [char]0x221A
        0x14 = [char]0x21BB; 0x15 = [char]0x2260
        0x16 = [char]0x2264; 0x17 = [char]0x2265
        0x18 = [char]0x00D7; 0x19 = [char]0x00F7
        0x1A = [char]0x00B2; 0x1B = [char]0x02B8
        0x1C = [char]0x02E3; 0x1D = [char]0x22BB
        0x1E = [char]0x207B; 0x1F = [char]0x21B5
    }
    try {
        [Text.Encoding]::RegisterProvider(
            [Text.CodePagesEncodingProvider]::Instance)
    } catch {
        # Windows PowerShell uses .NET Framework, where CP1251 is built in and
        # CodePagesEncodingProvider is not a separate type.
    }
    $cp1251 = [Text.Encoding]::GetEncoding(
        1251, [Text.EncoderFallback]::ExceptionFallback,
        [Text.DecoderFallback]::ExceptionFallback)
    $builder = New-Object Text.StringBuilder
    foreach ($value in $Bytes) {
        if ($special.ContainsKey([int]$value)) {
            [void]$builder.Append($special[[int]$value])
            continue
        }
        if (-not ($value -in 9, 10, 13 -or
                  ($value -ge 0x0E -and $value -le 0x7E) -or
                  ($value -ge 0x80 -and $value -ne 0x98))) {
            throw ('invalid M8 help byte: 0x{0:x2}' -f $value)
        }
        [void]$builder.Append($cp1251.GetString([byte[]]@($value)))
    }
    return [Text.Encoding]::UTF8.GetBytes($builder.ToString())
}

try {
    $elfPath = [IO.Path]::GetFullPath($ResidentElf)
    if (-not [IO.File]::Exists($elfPath)) {
        throw "resident ELF not found: $elfPath"
    }
    [byte[]]$data = [IO.File]::ReadAllBytes($elfPath)
    if ($data.Length -lt 52 -or $data[0] -ne 0x7F -or
        $data[1] -ne 0x45 -or $data[2] -ne 0x4C -or $data[3] -ne 0x46 -or
        $data[4] -ne 1 -or $data[5] -ne 1 -or
        (Get-Le16 $data 18) -ne 40) {
        throw 'expected ARM ELF32'
    }
    $sectionTable = Get-Le32 $data 32
    $sectionEntrySize = Get-Le16 $data 46
    $sectionCount = Get-Le16 $data 48
    $stringIndex = Get-Le16 $data 50
    $sections = @()
    for ($index = 0; $index -lt $sectionCount; $index++) {
        $sections += Get-Section $data $sectionTable $sectionEntrySize `
            $sectionCount $index
    }
    $stringSection = $sections[$stringIndex]
    [byte[]]$names = Get-BytesSlice $data $stringSection.Offset `
        $stringSection.Size
    $matches = @($sections | Where-Object {
        (Get-SectionName $names $_.Name) -eq '.mk61_help'
    })
    if ($matches.Count -ne 1 -or ($matches[0].Flags -band 2) -ne 0) {
        throw ('missing non-allocating .mk61_help metadata; regenerate the ' +
               'portable linker script')
    }
    [byte[]]$content = Get-BytesSlice $data $matches[0].Offset $matches[0].Size
    if ($content.Length -eq 0 -or $content[-1] -ne 0) {
        throw 'invalid help metadata'
    }
    for ($index = 0; $index -lt $content.Length - 1; $index++) {
        if ($content[$index] -eq 0) { throw 'invalid help metadata' }
    }
    if ($content.Length - 1 -gt $HelpBodyLimit) {
        throw 'help exceeds two pages'
    }
    [byte[]]$body = $content[0..($content.Length - 2)]
    [uint32]$checksum = 2166136261
    foreach ($value in $body) {
        $checksum = [uint32](([uint64]($checksum -bxor $value) * 16777619) `
            -band [uint64]4294967295)
    }
    [byte[]]$tag = [Text.Encoding]::ASCII.GetBytes(
        ('{0:x8}' -f $checksum) + "`n")
    $pageBodyLimit = $HelpFileLimit - $tag.Length
    $split = [Math]::Min($pageBodyLimit, $body.Length)
    if ($split -lt $body.Length) {
        $line = -1
        for ($index = $split; $index -ge 0; $index--) {
            if ($body[$index] -eq 10) { $line = $index; break }
        }
        if ($line -ge 0 -and $body.Length - ($line + 1) -le $pageBodyLimit) {
            $split = $line + 1
        }
    }
    $output = [IO.Path]::GetFullPath($OutputDirectory)
    [IO.Directory]::CreateDirectory($output) | Out-Null
    for ($page = 0; $page -lt 2; $page++) {
        $start = if ($page -eq 0) { 0 } else { $split }
        $length = if ($page -eq 0) { $split } else { $body.Length - $split }
        [byte[]]$part = [byte[]]::new($length)
        if ($length -gt 0) { [Array]::Copy($body, $start, $part, 0, $length) }
        if ($UsbText) { $part = Convert-M8ToUtf8 $part }
        [byte[]]$pageBytes = [byte[]]::new($tag.Length + $part.Length)
        [Array]::Copy($tag, 0, $pageBytes, 0, $tag.Length)
        [Array]::Copy($part, 0, $pageBytes, $tag.Length, $part.Length)
        if ($pageBytes.Length -gt $HelpFileLimit -and -not $UsbText) {
            throw 'help page exceeds TEXT file limit'
        }
        [IO.File]::WriteAllBytes(
            (Join-Path $output "HELP$page.TXT"), $pageBytes)
    }
    [pscustomobject]@{
        bytes = $body.Length
        tag = ('{0:x8}' -f $checksum)
    } | ConvertTo-Json -Compress | Write-Host
} catch {
    [Console]::Error.WriteLine(
        "terminal help build: $($_.Exception.Message)")
    exit 1
}
