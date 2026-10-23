#requires -Version 5.1
# PowerShell backend of the single public entry point, ../bbs.cmd.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Show-BbsUsage {
    @'
Usage: bbs.cmd serve --port DEVICE [--host 127.0.0.1] [--listen 2323]
       bbs.cmd package --output FILE.zip

serve    Bridge USB CDC to one UTF-8 TCP/Telnet visitor (e.g. --port COM3).
package  Package the BASIC modules, both host backends, and documentation.
--listen accepts 0..65535; 0 asks the OS to choose a free TCP port.
'@
}

function Write-BbsPackage([string]$OutputPath) {
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    $source = Join-Path $root 'programs/network/BBS'
    if (-not [IO.Directory]::Exists($source)) { $source = Join-Path $root 'C6/network/BBS' }
    if (-not [IO.File]::Exists((Join-Path $source 'autoexec.m61'))) {
        throw 'BBS sources not found next to the host tools'
    }
    $files = @()
    foreach ($file in (Get-ChildItem -LiteralPath $source -Recurse -File -Force | Sort-Object FullName)) {
        $relative = $file.FullName.Substring($source.Length + 1).Replace('\', '/')
        $files += @{ Path = $file.FullName; Name = 'C6/network/BBS/' + $relative }
    }
    $hostDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    foreach ($name in 'bbs.cmd', '.bbs/bbs.py', '.bbs/bbs.ps1', '.bbs/bridge.ps1') {
        $files += @{ Path = (Join-Path $hostDirectory $name); Name = 'host/' + $name }
    }
    $codec = Join-Path $hostDirectory 'm8_codec.py'
    if (-not [IO.File]::Exists($codec)) { $codec = Join-Path $hostDirectory '.bbs/m8_codec.py' }
    $files += @{ Path = $codec; Name = 'host/.bbs/m8_codec.py' }
    foreach ($name in 'BBS.md', 'BASIC-TEXT.md') { $files += @{ Path = (Join-Path $root $name); Name = $name } }
    Add-Type -AssemblyName System.IO.Compression
    $outputFile = [IO.Path]::GetFullPath($OutputPath)
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputFile))
    $stream = [IO.File]::Create($outputFile)
    try {
        $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($file in $files) {
                $entry = $archive.CreateEntry($file.Name, [IO.Compression.CompressionLevel]::Optimal)
                $entry.ExternalAttributes = if ($file.Name -eq 'host/bbs.cmd') { 0x81ED0000 } else { 0x81A40000 }
                $target = $entry.Open()
                try {
                    $inputFile = [IO.File]::OpenRead($file.Path)
                    try { $inputFile.CopyTo($target) } finally { $inputFile.Dispose() }
                } finally { $target.Dispose() }
            }
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
    Write-Output "${OutputPath}: $($files.Count) files; firmware/System must be built from this branch"
}

$cli = @($args)
if ($cli.Count -and $cli[0] -cin '-h', '--help') { Show-BbsUsage; exit 0 }
if (-not $cli.Count -or $cli[0] -cnotin 'serve', 'package') {
    [Console]::Error.WriteLine('Expected serve or package; use bbs.cmd --help'); exit 2
}
$mode = $cli[0]
$options = @{ '--port' = ''; '--host' = '127.0.0.1'; '--listen' = '2323'; '--output' = '' }
$allowed = if ($mode -eq 'serve') { @('--port', '--host', '--listen') } else { @('--output') }
for ($i = 1; $i -lt $cli.Count; $i++) {
    if ($cli[$i] -cin '-h', '--help') { Show-BbsUsage; exit 0 }
    $parts = $cli[$i] -split '=', 2
    $name = $parts[0]
    if ($name -cnotin $allowed -or ($parts.Count -eq 1 -and
        ($i + 1 -ge $cli.Count -or $cli[$i + 1].StartsWith('--')))) {
        [Console]::Error.WriteLine('Invalid or incomplete option: {0}', $name); exit 2
    }
    if ($parts.Count -eq 2) { $options[$name] = $parts[1] }
    else { $i++; $options[$name] = $cli[$i] }
}
if (($mode -eq 'serve' -and -not $options['--port']) -or
    ($mode -eq 'package' -and -not $options['--output'])) {
    [Console]::Error.WriteLine('Missing --port or --output; use bbs.cmd --help'); exit 2
}
[int]$listenPort = 0
if ($mode -eq 'serve' -and (-not [int]::TryParse($options['--listen'], [ref]$listenPort) -or
    $listenPort -lt 0 -or $listenPort -gt 65535)) {
    [Console]::Error.WriteLine('--listen must be in 0..65535'); exit 2
}
try {
    if ($mode -eq 'package') { Write-BbsPackage $options['--output'] }
    else {
        . (Join-Path $PSScriptRoot 'bridge.ps1')
        Start-BbsServer $options['--port'] $options['--host'] $listenPort
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message); exit 1
}
