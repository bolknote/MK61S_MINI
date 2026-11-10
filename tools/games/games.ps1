#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
try {
    [Console]::InputEncoding = [Text.Encoding]::UTF8
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    $OutputEncoding = [Text.Encoding]::UTF8
} catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$script:ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$script:CatalogPath = Join-Path $PSScriptRoot 'catalog.json'
$script:Catalog = ConvertFrom-Json ([IO.File]::ReadAllText($script:CatalogPath))
$script:Items = @($script:Catalog.items)
$script:OutputRoot = Join-Path $script:ProjectRoot '.build/game-library'
$script:CacheRoot = Join-Path $script:OutputRoot 'cache'
$script:DryRun = $false

function Get-BytesSha256 {
    param([byte[]]$Bytes)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
    } finally { $algorithm.Dispose() }
}

function Assert-Bytes {
    param([byte[]]$Bytes, [string]$Expected, [string]$Label, [long]$ExpectedBytes = -1)
    if ($ExpectedBytes -ge 0 -and $Bytes.LongLength -ne $ExpectedBytes) {
        throw "Size mismatch for ${Label}: $($Bytes.LongLength) != $ExpectedBytes"
    }
    $actual = Get-BytesSha256 $Bytes
    if ($actual -cne $Expected) { throw "SHA-256 mismatch for ${Label}: $actual" }
    return ,$Bytes
}

function Get-DownloadedBytes {
    param([string]$Url, [string]$Sha256, [string]$Label)
    Write-Host "Download: $Url"
    if ($script:DryRun) { return $null }
    $client = New-Object Net.WebClient
    $client.Headers['User-Agent'] = 'MK61S-game-library/1'
    try { $bytes = $client.DownloadData($Url) }
    finally { $client.Dispose() }
    return ,(Assert-Bytes $bytes $Sha256 $Label)
}

function Save-CheckedDownload {
    param([string]$Url, [string]$Sha256, [string]$Label, [string]$Destination)
    if ([IO.File]::Exists($Destination)) {
        $existing = [IO.File]::ReadAllBytes($Destination)
        $actual = Get-BytesSha256 $existing
        if ($actual -ceq $Sha256) {
            Write-Host "Verified local: $Destination"
            return ,$existing
        }
        throw "SHA-256 mismatch for cached ${Label}: $actual"
    }
    $bytes = Get-DownloadedBytes $Url $Sha256 $Label
    if ($script:DryRun) { return $null }
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Destination))
    $temporary = $Destination + '.tmp'
    [IO.File]::WriteAllBytes($temporary, $bytes)
    Move-Item -LiteralPath $temporary -Destination $Destination -Force
    return ,$bytes
}

function Get-SafeTarget {
    param([string]$Relative)
    if ([string]::IsNullOrWhiteSpace($Relative) -or [IO.Path]::IsPathRooted($Relative) -or
        @(($Relative -replace '\\', '/') -split '/') -contains '..') {
        throw "Unsafe catalog path: $Relative"
    }
    $root = [IO.Path]::GetFullPath($script:OutputRoot).TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
    $target = [IO.Path]::GetFullPath((Join-Path $script:OutputRoot $Relative))
    if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Catalog path escapes output root: $Relative"
    }
    return $target
}

function Invoke-ZipDownload {
    param([object]$Item)
    $archive = Join-Path (Join-Path $script:CacheRoot 'archives') $Item.archive_name
    $bytes = Save-CheckedDownload $Item.url $Item.sha256 $Item.title $archive
    if ($script:DryRun -and $null -eq $bytes) {
        foreach ($member in $Item.members) { Write-Host "Would extract: $($member.target)" }
        return
    }
    $stream = New-Object IO.MemoryStream(,$bytes)
    try {
        $zip = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Read, $false)
        try {
            $entries = @{}
            foreach ($entry in $zip.Entries) { $entries[$entry.FullName] = $entry }
            $manifestFiles = [ordered]@{}
            foreach ($member in $Item.members) {
                if (-not $entries.ContainsKey([string]$member.source)) { throw "Missing archive member: $($member.source)" }
                $entry = $entries[[string]$member.source]
                $input = $entry.Open()
                $memory = New-Object IO.MemoryStream
                try { $input.CopyTo($memory); $data = $memory.ToArray() }
                finally { $input.Dispose(); $memory.Dispose() }
                [void](Assert-Bytes $data $member.sha256 $member.source ([long]$member.bytes))
                $target = Get-SafeTarget $member.target
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
                $temporary = $target + '.tmp'
                [IO.File]::WriteAllBytes($temporary, $data)
                Move-Item -LiteralPath $temporary -Destination $target -Force
                Write-Host "Prepared: $target"
                $manifestFiles[$member.target] = [ordered]@{
                    bytes = $data.LongLength
                    sha256 = Get-BytesSha256 $data
                    archive_member = $member.source
                }
            }
            $manifest = [ordered]@{
                format = 1; id = $Item.id; source_page = $Item.source_page
                url = $Item.url; archive_sha256 = $Item.sha256; rights = $Item.rights
                files = $manifestFiles
            }
            $manifestDirectory = Join-Path $script:OutputRoot 'manifests'
            [void][IO.Directory]::CreateDirectory($manifestDirectory)
            $json = ConvertTo-Json -InputObject $manifest -Depth 8
            [IO.File]::WriteAllText((Join-Path $manifestDirectory ($Item.id + '.json')),
                $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        } finally { $zip.Dispose() }
    } finally { $stream.Dispose() }
}

function Get-SpectrumPackage {
    param([string]$Id)
    $path = Join-Path $script:ProjectRoot 'third_party/spectrum-games/catalog.json'
    $catalog = ConvertFrom-Json ([IO.File]::ReadAllText($path))
    $matches = @($catalog.packages | Where-Object { $_.id -ceq $Id })
    if ($matches.Count -ne 1) { throw "Unknown Spectrum package: $Id" }
    return $matches[0]
}

function Invoke-SpectrumDownload {
    param([object]$Item)
    $package = Get-SpectrumPackage $Item.package
    switch ([string]$package.id) {
        'ianna' {
            $destination = Join-Path (Join-Path $script:ProjectRoot 'third_party/spectrum-games') $package.archive
            [void](Save-CheckedDownload $package.download_url $package.sha256 $package.title $destination)
        }
        'cosmic-payback' {
            $destination = Join-Path (Join-Path $script:CacheRoot 'spectrum') 'Cosmic-Payback.tap'
            [void](Save-CheckedDownload $package.download_url $package.download_sha256 $package.title $destination)
            Write-Host 'The verified TAP is cached; macOS/Linux can wrap it into the pinned package later.'
        }
        'ulaplus' {
            $destination = Join-Path (Join-Path $script:CacheRoot 'spectrum') $package.upstream_archive
            if ([IO.File]::Exists($destination) -and
                (Get-BytesSha256 ([IO.File]::ReadAllBytes($destination))) -ceq $package.upstream_sha256) {
                Write-Host "Verified local: $destination"
                return
            }
            if ([IO.File]::Exists($destination)) { throw "SHA-256 mismatch for cached $($package.upstream_archive)" }
            Write-Host "Request download: $($package.source)"
            if ($script:DryRun) { return }
            $client = New-Object Net.WebClient
            $client.Headers['Referer'] = [string]$package.source
            $client.Headers['User-Agent'] = 'MK61S-game-library/1'
            try {
                $form = New-Object Collections.Specialized.NameValueCollection
                $form['action'] = 'download'
                $answer = [Text.Encoding]::UTF8.GetString($client.UploadValues(
                    "$($package.source)/file/$($package.upstream_upload_id)", $form)) | ConvertFrom-Json
            } finally { $client.Dispose() }
            [void](Save-CheckedDownload $answer.url $package.upstream_sha256 $package.upstream_archive $destination)
            Write-Host 'The verified upstream ZIP is cached; macOS/Linux can prepare the pinned package later.'
        }
        default { throw "No native PowerShell downloader for Spectrum package: $($package.id)" }
    }
}

function Get-ItemById {
    param([string]$Id)
    $matches = @($script:Items | Where-Object { $_.id -ceq $Id })
    if ($matches.Count -ne 1) { throw "Unknown game-library item: $Id" }
    return $matches[0]
}

function Test-WindowsSupported {
    param([object]$Item)
    return -not ($Item.PSObject.Properties.Name -contains 'windows_supported') -or [bool]$Item.windows_supported
}

function Invoke-Selected {
    param([string[]]$Ids)
    if ($Ids.Count -eq 0) { throw 'No items selected' }
    foreach ($id in $Ids) {
        $item = Get-ItemById $id
        if (-not (Test-WindowsSupported $item)) { throw "$($item.title) has no native PowerShell builder yet" }
        Write-Host
        Write-Host "== $($item.title) ==" -ForegroundColor Cyan
        if ($item.PSObject.Properties.Name -contains 'rights') { Write-Host "Note: $($item.rights)" }
        switch ([string]$item.runner) {
            'download_zip' { Invoke-ZipDownload $item }
            'spectrum_package' { Invoke-SpectrumDownload $item }
            default { throw "Unsupported native PowerShell runner: $($item.runner)" }
        }
    }
    Write-Host
    Write-Host "Ready folder: $(Join-Path $script:OutputRoot 'sd')"
}

function Show-Usage {
    Write-Host 'Usage:'
    Write-Host '  games.cmd                         interactive checklist'
    Write-Host '  games.cmd list'
    Write-Host '  games.cmd run --select ID [--select ID ...] [--dry-run]'
}

function Invoke-Arguments {
    param([object[]]$Arguments)
    if ($Arguments.Count -eq 0) { return $false }
    $command = [string]$Arguments[0]
    if ($command -in @('-h', '--help', 'help')) { Show-Usage; return $true }
    if ($command -eq 'list') {
        foreach ($item in $script:Items) {
            $suffix = if (Test-WindowsSupported $item) { '' } else { ' [macOS/Linux]' }
            Write-Host "$($item.id): $($item.title)$suffix"
        }
        return $true
    }
    if ($command -ne 'run') { throw "Unknown command: $command" }
    $ids = New-Object 'Collections.Generic.List[string]'
    $cacheExplicit = $false
    for ($i = 1; $i -lt $Arguments.Count; $i++) {
        switch ([string]$Arguments[$i]) {
            '--select' { $i++; if ($i -ge $Arguments.Count) { throw '--select needs ID' }; $ids.Add([string]$Arguments[$i]) }
            '--output-root' { $i++; if ($i -ge $Arguments.Count) { throw '--output-root needs PATH' }; $script:OutputRoot = [IO.Path]::GetFullPath([string]$Arguments[$i]) }
            '--cache-root' { $i++; if ($i -ge $Arguments.Count) { throw '--cache-root needs PATH' }; $script:CacheRoot = [IO.Path]::GetFullPath([string]$Arguments[$i]); $cacheExplicit = $true }
            '--dry-run' { $script:DryRun = $true }
            default { throw "Unknown option: $($Arguments[$i])" }
        }
    }
    if (-not $cacheExplicit) { $script:CacheRoot = Join-Path $script:OutputRoot 'cache' }
    Invoke-Selected $ids.ToArray()
    return $true
}

try {
    if (Invoke-Arguments $args) { exit 0 }
} catch {
    [Console]::Error.WriteLine("games: $($_.Exception.Message)")
    exit 1
}

$menuItems = @($script:Items | Where-Object { Test-WindowsSupported $_ })
[bool[]]$checked = @($menuItems | ForEach-Object { [bool]$_.default })
$selected = 0
while ($true) {
    Clear-Host
    Write-Host ' MK61S GAME LIBRARY ' -ForegroundColor Cyan
    Write-Host ' Choose downloads'
    Write-Host
    for ($i = 0; $i -lt $menuItems.Count; $i++) {
        $marker = if ($checked[$i]) { '[x]' } else { '[ ]' }
        $cursor = if ($i -eq $selected) { '>' } else { ' ' }
        $line = "$cursor $marker  $($menuItems[$i].title)"
        if ($i -eq $selected) { Write-Host $line -ForegroundColor Black -BackgroundColor Gray }
        else { Write-Host $line }
    }
    Write-Host
    Write-Host (' ' + $menuItems[$selected].description)
    Write-Host
    Write-Host ' Up/Down choose  Space toggle  Enter run  Esc/Q quit' -ForegroundColor Cyan
    $key = [Console]::ReadKey($true)
    switch ($key.Key) {
        'UpArrow' { $selected--; if ($selected -lt 0) { $selected = $menuItems.Count - 1 } }
        'DownArrow' { $selected++; if ($selected -ge $menuItems.Count) { $selected = 0 } }
        'Home' { $selected = 0 }
        'End' { $selected = $menuItems.Count - 1 }
        'Spacebar' { $checked[$selected] = -not $checked[$selected] }
        'X' { $checked[$selected] = -not $checked[$selected] }
        'Escape' { Clear-Host; exit 0 }
        'Q' { Clear-Host; exit 0 }
        'Enter' {
            $ids = New-Object 'Collections.Generic.List[string]'
            for ($i = 0; $i -lt $menuItems.Count; $i++) { if ($checked[$i]) { $ids.Add([string]$menuItems[$i].id) } }
            Clear-Host
            try { Invoke-Selected $ids.ToArray(); exit 0 }
            catch { [Console]::Error.WriteLine("games: $($_.Exception.Message)"); exit 1 }
        }
    }
}
