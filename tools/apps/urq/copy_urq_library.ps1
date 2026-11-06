#requires -Version 5.1
# Synchronize reserved generated payloads in known catalog namespaces only.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [string]$LibraryOutput,
    [string]$LicensesOutput
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($LibraryOutput) -and [string]::IsNullOrWhiteSpace($LicensesOutput)) { return }
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)

function Get-SafeItem([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -ne $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Unsafe URQ distribution link: $Path"
    }
    return $item
}
function Assert-Directory([string]$Path) {
    $item = Get-SafeItem $Path
    if ($null -ne $item -and -not $item.PSIsContainer) { throw "Unsafe URQ distribution directory: $Path" }
}
function Read-Payload([string]$Path) {
    $item = Get-SafeItem $Path
    if ($null -eq $item -or $item.PSIsContainer) { throw "Missing/unsafe URQ distribution file: $Path" }
    return ,([IO.File]::ReadAllBytes($Path))
}
function Assert-TargetFile([string]$Path) {
    $item = Get-SafeItem $Path
    if ($null -ne $item -and $item.PSIsContainer) { throw "Unsafe URQ distribution file: $Path" }
}
function Test-DeviceName([string]$Name) { return $Name -imatch '^(game\.urq|p[0-9]{4}\.uqd|autoexec\.wbmp)$' }

$report = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $ProjectRoot 'tools/apps/urq/catalog-report.json')))
$known = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($game in $report.games) { [void]$known.Add($game.id) }
# Matches DEVICE_EXCLUSIONS in library.py; an old report may still publish it.
[void]$known.Add('house_that_jack_built')
foreach ($key in $known) {
    if ($key -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*$') { throw "Invalid URQ distribution namespace: $key" }
}
$published = @($report.published | Where-Object { $_ -cne 'house_that_jack_built' } | Sort-Object -Unique)
foreach ($key in $published) {
    if (-not $known.Contains($key)) { throw "Unknown published URQ namespace: $key" }
}
$library = Join-Path $ProjectRoot 'programs/urq'
$sources = Join-Path $ProjectRoot 'tools/apps/urq/sources'
Assert-Directory $library
$files = [Collections.Generic.Dictionary[string,byte[]]]::new([StringComparer]::Ordinal)
$files.Add('autoexec.wbmp', (Read-Payload (Join-Path $library 'autoexec.wbmp')))
foreach ($key in $published) {
    $folder = Join-Path $library $key
    Assert-Directory $folder
    $index = Read-Payload (Join-Path $folder 'game.urq')
    if ($index.Length -lt 64 -or [Convert]::ToBase64String($index, 0, 10) -cne 'TUs2MVVSUQABAA==') {
        throw "Invalid URQ index: $folder"
    }
    $parts = [int]$index[40] + 256 * [int]$index[41]
    if ($parts -lt 1) { throw "URQ index has no data parts: $key" }
    $files.Add("$key/game.urq", $index)
    $files.Add("$key/autoexec.wbmp", (Read-Payload (Join-Path $folder 'autoexec.wbmp')))
    for ($part = 0; $part -lt $parts; $part++) {
        $name = 'p{0:D4}.uqd' -f $part
        $files.Add("$key/$name", (Read-Payload (Join-Path $folder $name)))
    }
}

function New-SyncPlan([string]$Destination, $Payloads, [bool]$Licenses) {
    $Destination = [IO.Path]::GetFullPath($Destination)
    $comparison = [StringComparison]::Ordinal
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { $comparison = [StringComparison]::OrdinalIgnoreCase }
    foreach ($source in @($library, $sources)) {
        $left = $Destination.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
        $right = [IO.Path]::GetFullPath($source).TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
        if ($left.StartsWith($right, $comparison) -or $right.StartsWith($left, $comparison)) {
            throw "URQ distribution must not overlap its sources: $Destination"
        }
    }
    Assert-Directory $Destination
    if (-not $Licenses) { Assert-TargetFile (Join-Path $Destination 'autoexec.wbmp') }
    $stockIcon = $null
    if ($Licenses) { $stockIcon = [Convert]::ToBase64String((Read-Payload (Join-Path $ProjectRoot 'doc/explorer-icons/license.wbmp'))) }
    $removals = [Collections.Generic.List[string]]::new()
    $folders = [Collections.Generic.List[string]]::new()
    foreach ($key in ($known | Sort-Object)) {
        $folder = Join-Path $Destination $key
        Assert-Directory $folder
        if (-not [IO.Directory]::Exists($folder)) { continue }
        $folders.Add($folder)
        foreach ($item in (Get-ChildItem -LiteralPath $folder -Force)) {
            $owned = Test-DeviceName $item.Name
            if ($Licenses) { $owned = $item.Name -imatch '^(AUTHORS\.txt|LICENSE\.txt|autoexec\.wbmp)$' }
            if (-not $owned) { continue }
            Assert-TargetFile $item.FullName
            $relative = "$key/$($item.Name)"
            if ($Licenses -and $item.Name -ieq 'autoexec.wbmp') {
                if ($Payloads.ContainsKey("$key/LICENSE.txt") -or
                    [Convert]::ToBase64String([IO.File]::ReadAllBytes($item.FullName)) -cne $stockIcon) { continue }
            }
            if (-not $Payloads.ContainsKey($relative)) { $removals.Add($item.FullName) }
        }
    }
    foreach ($relative in $Payloads.Keys) {
        $target = Join-Path $Destination $relative
        Assert-Directory ([IO.Path]::GetDirectoryName($target))
        Assert-TargetFile $target
    }
    return [pscustomobject]@{ Destination = $Destination; Files = $Payloads; Removals = $removals; Folders = $folders }
}

# Read sources and preflight destinations before deleting/overwriting anything.
# Saves, notes and unknown/custom directories are never traversed or removed.
$plans = @()
if (-not [string]::IsNullOrWhiteSpace($LibraryOutput)) { $plans += New-SyncPlan $LibraryOutput $files $false }
if (-not [string]::IsNullOrWhiteSpace($LicensesOutput)) {
    Assert-Directory $sources
    $licenses = [Collections.Generic.Dictionary[string,byte[]]]::new([StringComparer]::Ordinal)
    foreach ($key in $published) {
        $folder = Join-Path $sources $key
        Assert-Directory $folder
        foreach ($name in @('AUTHORS.txt', 'LICENSE.txt')) {
            $licenses.Add("$key/$name", (Read-Payload (Join-Path $folder $name)))
        }
    }
    $plans += New-SyncPlan $LicensesOutput $licenses $true
}
foreach ($plan in $plans) {
    foreach ($path in $plan.Removals) { [IO.File]::Delete($path) }
    foreach ($relative in $plan.Files.Keys) {
        $target = Join-Path $plan.Destination $relative
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
        [IO.File]::WriteAllBytes($target, $plan.Files[$relative])
    }
    foreach ($folder in $plan.Folders) {
        if (@(Get-ChildItem -LiteralPath $folder -Force).Count -eq 0) { [IO.Directory]::Delete($folder) }
    }
}
