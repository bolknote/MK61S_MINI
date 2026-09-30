#requires -Version 5.1

[CmdletBinding()]
param(
    # Accepted for CLI compatibility with the native and Python packers.  The
    # PowerShell implementation only writes current portable ABI 6 modules.
    [switch]$Portable,
    [Parameter(Mandatory = $true)]
    [ValidateSet('focal', 'tinybasic', 'wbmp-viewer', 'app', 'chip8',
                 'markdown-viewer', 'setup', 'usbdisk', 'explorer')]
    [string]$Kind,
    [Parameter(Mandatory = $true)]
    [string]$Image,
    [Parameter(Mandatory = $true)]
    [string]$Relocations,
    [Parameter(Mandatory = $true)]
    [Alias('memory-size')]
    [int]$MemorySize,
    [Parameter(Mandatory = $true)]
    [Alias('entry-offset')]
    [int]$EntryOffset,
    [Alias('load-address')]
    [uint32]$LoadAddress = 0x20000000,
    [Alias('handled-magic')]
    [string]$HandledMagic,
    [Parameter(Mandatory = $true)]
    [string]$Output
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try {
    if (-not ('Mk61.Build.AppPacker' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'Mk61AppPacker.cs')
    }
    $result = [Mk61.Build.AppPacker]::PackFile(
        $Kind,
        [IO.Path]::GetFullPath($Image),
        [IO.Path]::GetFullPath($Relocations),
        $MemorySize,
        $EntryOffset,
        $LoadAddress,
        $HandledMagic,
        [IO.Path]::GetFullPath($Output))
    $selected = if ($result.UsesBcj) { 'BCJ' } else { 'plain' }
    Write-Host (
        "ZX0 candidates: plain=$($result.PlainBytes) " +
        "BCJ=$($result.BcjBytes); selected=$selected")
    $ratio = ($result.AppBytes - 64) * 100.0 / $result.ImageBytes
    Write-Host ('{0}: {1} bytes, payload ratio {2:F1}%' -f
        ([IO.Path]::GetFullPath($Output)), $result.AppBytes, $ratio)
} catch {
    [Console]::Error.WriteLine(
        "mk61_module_pack: $($_.Exception.Message)")
    exit 2
}
