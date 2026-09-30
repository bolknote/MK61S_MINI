#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$Bundle,
    [string]$Archive
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try {
    if ([string]::IsNullOrWhiteSpace($Bundle) -and
        [string]::IsNullOrWhiteSpace($Archive)) {
        throw 'at least one output is required'
    }
    $sourceRoot = $PSScriptRoot
    $files = [ordered]@{
        'licenses/ui-fonts/LICENSE-Ark-Pixel.txt' =
            'ui-atlases/LICENSE-Ark-Pixel.txt'
        'licenses/ui-fonts/LICENSE-DejaVu.txt' =
            'external-fonts/LICENSE-DejaVu.txt'
        'licenses/ui-fonts/LICENSE-MK61-16x35r.txt' =
            'ui-atlases/LICENSE-MK61-16x35r.txt'
        'licenses/ui-fonts/FONT-SOURCES.md' = 'ui-atlases/README.md'
    }
    if (-not [string]::IsNullOrWhiteSpace($Bundle)) {
        $bundlePath = [IO.Path]::GetFullPath($Bundle)
        foreach ($entry in $files.GetEnumerator()) {
            $source = Join-Path $sourceRoot $entry.Value
            if (-not [IO.File]::Exists($source)) {
                throw "font notice not found: $source"
            }
            $target = Join-Path $bundlePath $entry.Key
            [IO.Directory]::CreateDirectory(
                [IO.Path]::GetDirectoryName($target)) | Out-Null
            [IO.File]::WriteAllBytes(
                $target, [IO.File]::ReadAllBytes($source))
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($Archive)) {
        Add-Type -AssemblyName System.IO.Compression
        $archivePath = [IO.Path]::GetFullPath($Archive)
        [IO.Directory]::CreateDirectory(
            [IO.Path]::GetDirectoryName($archivePath)) | Out-Null
        $stream = [IO.File]::Open(
            $archivePath, [IO.FileMode]::Create,
            [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $zip = New-Object IO.Compression.ZipArchive(
                $stream, [IO.Compression.ZipArchiveMode]::Create, $false)
            try {
                foreach ($item in $files.GetEnumerator()) {
                    $entry = $zip.CreateEntry(
                        $item.Key, [IO.Compression.CompressionLevel]::Optimal)
                    $entry.LastWriteTime = [DateTimeOffset]::new(
                        2026, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
                    $target = $entry.Open()
                    try {
                        [byte[]]$payload = [IO.File]::ReadAllBytes(
                            (Join-Path $sourceRoot $item.Value))
                        $target.Write($payload, 0, $payload.Length)
                    } finally { $target.Dispose() }
                }
            } finally { $zip.Dispose() }
        } finally { $stream.Dispose() }
    }
} catch {
    [Console]::Error.WriteLine(
        "font license packaging: $($_.Exception.Message)")
    exit 1
}
