#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResidentElf,
    [Parameter(Mandatory = $true)]
    [string]$ArmToolchainBin,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$CatalogDirectory,
    [ValidateSet('0', '1')][string]$Graphics = '1',
    [ValidateSet('0', '1')][string]$UiFonts = '1',
    [ValidateSet('0', '1')][string]$Focal = '1',
    [ValidateSet('0', '1')][string]$Basic = '1',
    [ValidateSet('0', '1')][string]$Wbmp = '1',
    [ValidateSet('0', '1')][string]$Markdown = '1',
    [ValidateSet('0', '1')][string]$Chip8 = '1',
    [ValidateSet('0', '1')][string]$Setup = '1',
    [ValidateSet('0', '1')][string]$UsbDisk = '1',
    [ValidateSet('0', '1')][string]$Explorer = '0',
    [ValidateSet('0', '1')][string]$LocalFloatMath = '0'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
$Canonical = @(
    'FOCAL.APP', 'BASIC.APP', 'WBMP.APP', 'MARKDOWN.APP', 'CHIP8.APP',
    'SETUP.APP', 'USBDISK.APP', 'EXPLORER.APP', 'HELP0.TXT', 'HELP1.TXT')
$Modules = @(
    [pscustomobject]@{ Key = 'setup'; Name = 'SETUP.APP'; System = 'setup' },
    [pscustomobject]@{ Key = 'focal'; Name = 'FOCAL.APP'; System = 'focal' },
    [pscustomobject]@{ Key = 'basic'; Name = 'BASIC.APP'; System = 'tinybasic' },
    [pscustomobject]@{ Key = 'wbmp'; Name = 'WBMP.APP'; System = 'wbmp-viewer' },
    [pscustomobject]@{ Key = 'markdown'; Name = 'MARKDOWN.APP'; System = 'markdown-viewer' },
    [pscustomobject]@{ Key = 'chip8'; Name = 'CHIP8.APP'; System = 'chip8' },
    [pscustomobject]@{ Key = 'usbdisk'; Name = 'USBDISK.APP'; System = 'usbdisk' },
    [pscustomobject]@{ Key = 'explorer'; Name = 'EXPLORER.APP'; System = 'explorer' })
$Enabled = @{
    setup = $Setup -eq '1'; focal = $Focal -eq '1'; basic = $Basic -eq '1'
    wbmp = $Wbmp -eq '1' -and $Markdown -ne '1'
    markdown = $Markdown -eq '1'; chip8 = $Chip8 -eq '1'
    usbdisk = $UsbDisk -eq '1'; explorer = $Explorer -eq '1'
}

function Get-CurrentPowerShell {
    if ($PSVersionTable.PSEdition -eq 'Desktop') {
        return (Join-Path $PSHOME 'powershell.exe')
    }
    return (Get-Process -Id $PID).Path
}

function Invoke-BuildTool {
    param([string]$Path, [string[]]$Arguments, [switch]$Capture)
    if ($Capture) {
        $lines = @(& $Path @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        $text = ($lines | Out-String).TrimEnd()
        if ($exitCode -ne 0) {
            throw "$([IO.Path]::GetFileName($Path)) failed with exit code " +
                "${exitCode}:`n$text"
        }
        return $text
    }
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$([IO.Path]::GetFileName($Path)) failed with exit code $LASTEXITCODE"
    }
}

function Get-HexHash {
    param([byte[]]$Payload)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash($Payload) } finally { $sha.Dispose() }
    return (($hash | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Write-AtomicBytes {
    param([string]$Path, [byte[]]$Payload)
    $parent = [IO.Path]::GetDirectoryName($Path)
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $temporary = Join-Path $parent (
        ".$([IO.Path]::GetFileName($Path)).$([guid]::NewGuid().ToString('N')).tmp")
    $backup = $null
    try {
        [IO.File]::WriteAllBytes($temporary, $Payload)
        if ([IO.File]::Exists($Path)) {
            $backup = Join-Path $parent (
                ".$([IO.Path]::GetFileName($Path)).$([guid]::NewGuid().ToString('N')).bak")
            try {
                [IO.File]::Replace($temporary, $Path, $backup)
            } catch [PlatformNotSupportedException] {
                Remove-Item -LiteralPath $Path -Force
                [IO.File]::Move($temporary, $Path)
            }
        } else {
            [IO.File]::Move($temporary, $Path)
        }
        $temporary = $null
    } finally {
        if ($null -ne $temporary -and [IO.File]::Exists($temporary)) {
            Remove-Item -LiteralPath $temporary -Force
        }
        if ($null -ne $backup -and [IO.File]::Exists($backup)) {
            Remove-Item -LiteralPath $backup -Force
        }
    }
}

function Get-EmptyCatalog {
    return [pscustomobject]@{ format = 1; abi = 6; apps = @() }
}

function Read-Catalog {
    param([string]$Directory)
    $manifestPath = Join-Path $Directory 'catalog.json'
    if (-not [IO.File]::Exists($manifestPath)) { return Get-EmptyCatalog }
    $manifest = ConvertFrom-Json -InputObject (
        [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8))
    if ($null -eq $manifest -or $manifest -is [Array] -or
        $manifest.format -ne 1 -or $manifest.abi -ne 6 -or
        $null -eq $manifest.apps) {
        throw "unsupported APP catalog: $manifestPath"
    }
    foreach ($record in @($manifest.apps)) {
        foreach ($field in @('name', 'system', 'variant', 'build_key',
                              'sha256', 'path', 'size')) {
            if ($null -eq $record.$field) {
                throw "invalid APP catalog record: $manifestPath"
            }
        }
    }
    return $manifest
}

function Write-Catalog {
    param([string]$Directory, [object]$Manifest)
    $json = $Manifest | ConvertTo-Json -Depth 5
    Write-AtomicBytes (Join-Path $Directory 'catalog.json') `
        ([Text.Encoding]::UTF8.GetBytes($json + [Environment]::NewLine))
}

function Enter-CatalogLock {
    param([string]$Directory)
    [IO.Directory]::CreateDirectory($Directory) | Out-Null
    $path = Join-Path $Directory '.catalog.lock'
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    while ($true) {
        try {
            return [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate,
                [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch [IO.IOException] {
            if ([DateTime]::UtcNow -ge $deadline) {
                throw "timed out waiting for APP catalog lock: $path"
            }
            Start-Sleep -Milliseconds 50
        }
    }
}

function Get-AppVariant {
    param([string]$SystemName)
    $parts = New-Object 'System.Collections.Generic.List[string]'
    $parts.Add($(if ($UiFonts -eq '1') { 'ui-fonts' } else { 'plain' }))
    if ($SystemName -eq 'markdown-viewer') {
        $parts.Add($(if ($Graphics -eq '1') { 'graphics' } else { 'text' }))
    }
    if ($SystemName -in @('focal', 'tinybasic')) {
        $parts.Add($(if ($LocalFloatMath -eq '1') { 'float' } else { 'core' }))
    }
    return $parts -join '+'
}

function Get-SourceKey {
    param([string]$Toolchain)
    $suffixes = @('.S', '.c', '.cpp', '.def', '.h', '.hpp', '.inc',
                  '.ino', '.json', '.ld', '.ps1', '.cs', '.rs', '.sh')
    $inputs = New-Object 'System.Collections.Generic.List[string]'
    foreach ($directory in @('code', 'sdk/portable', 'tools/.mk61-app')) {
        foreach ($file in Get-ChildItem -LiteralPath `
                (Join-Path $ProjectRoot $directory) -Recurse -File) {
            if ($file.FullName -notmatch '[/\\]__pycache__[/\\]' -and
                $file.Extension -cin $suffixes) {
                $inputs.Add($file.FullName)
            }
        }
    }
    foreach ($file in @(
        $PSCommandPath,
        (Join-Path $ProjectRoot 'tools/build-portable-app.ps1'),
        (Join-Path $ProjectRoot 'tools/.mk61-app/build-terminal-help.ps1'))) {
        $inputs.Add([IO.Path]::GetFullPath($file))
    }
    $memory = New-Object IO.MemoryStream
    try {
        foreach ($path in @($inputs | Sort-Object -Unique)) {
            $relative = $path.Substring($ProjectRoot.Length).
                TrimStart([IO.Path]::DirectorySeparatorChar,
                          [IO.Path]::AltDirectorySeparatorChar).
                Replace([IO.Path]::DirectorySeparatorChar, '/')
            [byte[]]$name = [Text.Encoding]::UTF8.GetBytes($relative)
            [byte[]]$payload = [IO.File]::ReadAllBytes($path)
            $length = [BitConverter]::GetBytes([int]$name.Length)
            $memory.Write($length, 0, $length.Length)
            $memory.Write($name, 0, $name.Length)
            $size = [BitConverter]::GetBytes([long]$payload.Length)
            $memory.Write($size, 0, $size.Length)
            $memory.Write($payload, 0, $payload.Length)
        }
        $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
        $gcc = Join-Path $Toolchain "arm-none-eabi-gcc$suffix"
        $version = Invoke-BuildTool $gcc @('--version') -Capture
        $first = ($version -split "`r?`n")[0]
        [byte[]]$identity = [Text.Encoding]::UTF8.GetBytes(
            $first + "`nPowerShell-$($PSVersionTable.PSEdition)")
        $memory.Write($identity, 0, $identity.Length)
        return Get-HexHash $memory.ToArray()
    } finally { $memory.Dispose() }
}

function Get-AppBuildKey {
    param([string]$SourceKey, [object]$Module)
    $identity = $SourceKey + [char]0 + $Module.Name + [char]0 +
        $Module.System + [char]0 + (Get-AppVariant $Module.System)
    return Get-HexHash ([Text.Encoding]::UTF8.GetBytes($identity))
}

function Get-CachedPayload {
    param([object]$Module, [string]$BuildKey)
    if ([string]::IsNullOrWhiteSpace($CatalogDirectory)) { return $null }
    $catalog = [IO.Path]::GetFullPath($CatalogDirectory)
    $lock = Enter-CatalogLock $catalog
    try {
        try { $manifest = Read-Catalog $catalog }
        catch {
            [Console]::Error.WriteLine(
                "System APP cache ignored and will be rebuilt: $($_.Exception.Message)")
            $manifestPath = Join-Path $catalog 'catalog.json'
            if ([IO.File]::Exists($manifestPath)) {
                Remove-Item -LiteralPath $manifestPath -Force
            }
            return $null
        }
        $variant = Get-AppVariant $Module.System
        foreach ($record in @($manifest.apps)) {
            if ($record.name -ne $Module.Name -or
                $record.variant -ne $variant -or
                $record.build_key -ne $BuildKey) { continue }
            try {
                $digest = [string]$record.sha256
                $relative = [string]$record.path
                if ($digest -notmatch '^[0-9a-f]{64}$' -or
                    $relative -ne "objects/$digest.APP") {
                    throw "invalid APP catalog record: $($Module.Name)"
                }
                $stored = Join-Path $catalog ($relative.Replace('/', '\'))
                if (-not [IO.File]::Exists($stored)) {
                    throw "APP catalog object is missing: $stored"
                }
                [byte[]]$payload = [IO.File]::ReadAllBytes($stored)
                if ((Get-HexHash $payload) -ne $digest -or
                    $payload.Length -ne [int]$record.size -or
                    $payload.Length -lt 64 -or
                    [Text.Encoding]::ASCII.GetString($payload, 0, 7) -ne
                        'MK61APP' -or $payload[7] -ne 0 -or
                    [BitConverter]::ToUInt16($payload, 12) -ne 6) {
                    throw "APP catalog object is corrupted: $stored"
                }
                return $payload
            } catch {
                [Console]::Error.WriteLine(
                    "System APP cache entry ignored and will be rebuilt: " +
                    $_.Exception.Message)
                $manifest.apps = @($manifest.apps | Where-Object {
                    $_ -ne $record
                })
                Write-Catalog $catalog $manifest
                return $null
            }
        }
        return $null
    } finally { $lock.Dispose() }
}

function Publish-Catalog {
    param([string]$Source, [object]$Module, [string]$BuildKey)
    if ([string]::IsNullOrWhiteSpace($CatalogDirectory)) { return }
    $catalog = [IO.Path]::GetFullPath($CatalogDirectory)
    [byte[]]$payload = [IO.File]::ReadAllBytes($Source)
    $digest = Get-HexHash $payload
    $lock = Enter-CatalogLock $catalog
    try {
        $objects = Join-Path $catalog 'objects'
        [IO.Directory]::CreateDirectory($objects) | Out-Null
        $stored = Join-Path $objects "$digest.APP"
        if ([IO.File]::Exists($stored)) {
            [byte[]]$existing = [IO.File]::ReadAllBytes($stored)
            if ((Get-HexHash $existing) -ne $digest) {
                throw "APP catalog hash collision: $stored"
            }
        } else { Write-AtomicBytes $stored $payload }
        try { $manifest = Read-Catalog $catalog }
        catch {
            [Console]::Error.WriteLine(
                "System APP catalog was invalid and has been reset: " +
                $_.Exception.Message)
            $manifest = Get-EmptyCatalog
        }
        $variant = Get-AppVariant $Module.System
        $records = @($manifest.apps | Where-Object {
            $_.name -ne $Module.Name -or $_.variant -ne $variant
        })
        $records += [pscustomobject]@{
            name = $Module.Name; system = $Module.System
            variant = $variant; build_key = $BuildKey
            sha256 = $digest; size = $payload.Length
            path = "objects/$digest.APP"
        }
        $manifest.apps = @($records | Sort-Object name, variant)
        Write-Catalog $catalog $manifest
        $referenced = @{}
        foreach ($record in @($manifest.apps)) {
            $referenced[[string]$record.path] = $true
        }
        foreach ($candidate in Get-ChildItem -LiteralPath $objects `
                -Filter '*.APP' -File) {
            if (-not $referenced.ContainsKey("objects/$($candidate.Name)")) {
                Remove-Item -LiteralPath $candidate.FullName -Force
            }
        }
    } finally { $lock.Dispose() }
}

# Tests import the real catalog implementation and exercise it concurrently
# in separate Windows PowerShell processes. Normal callers never set this.
if ($env:MK61_POWERSHELL_IMPORT_ONLY -eq '1') { return }

try {
    $resident = [IO.Path]::GetFullPath($ResidentElf)
    if (-not [IO.File]::Exists($resident)) {
        throw "resident ELF not found: $resident"
    }
    $toolchain = [IO.Path]::GetFullPath($ArmToolchainBin)
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    $gcc = Join-Path $toolchain "arm-none-eabi-gcc$suffix"
    if (-not [IO.File]::Exists($gcc)) {
        throw "ARM GCC toolchain not found in: $toolchain"
    }
    $output = [IO.Path]::GetFullPath($OutputDirectory)
    [IO.Directory]::CreateDirectory($output) | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($CatalogDirectory)) {
        $CatalogDirectory = [IO.Path]::GetFullPath($CatalogDirectory)
        $sourceKey = Get-SourceKey $toolchain
    } else { $sourceKey = $null }
    $workspace = Join-Path ([IO.Path]::GetDirectoryName($output)) `
        ('.mk61-system-app-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($workspace) | Out-Null
    try {
        $stage = Join-Path $workspace 'System'
        [IO.Directory]::CreateDirectory($stage) | Out-Null
        $built = New-Object 'System.Collections.Generic.List[string]'
        $hits = New-Object 'System.Collections.Generic.List[string]'
        $powerShell = Get-CurrentPowerShell
        foreach ($module in $Modules) {
            if (-not $Enabled[$module.Key]) { continue }
            $buildKey = if ($null -ne $sourceKey) {
                Get-AppBuildKey $sourceKey $module
            } else { $null }
            [byte[]]$cached = if ($null -ne $buildKey) {
                Get-CachedPayload $module $buildKey
            } else { $null }
            $destination = Join-Path $stage $module.Name
            if ($null -eq $cached) {
                $moduleOutput = Join-Path $workspace $module.Key
                $arguments = New-Object 'System.Collections.Generic.List[string]'
                foreach ($value in @('-NoLogo', '-NoProfile', '-File',
                    (Join-Path $ProjectRoot 'tools/build-portable-app.ps1'),
                    '-System', $module.System,
                    '-ArmToolchainBin', $toolchain,
                    '-OutputDirectory', $moduleOutput)) {
                    $arguments.Add([string]$value)
                }
                if ($UiFonts -ne '1') { $arguments.Add('-NoUiFonts') }
                if ($module.System -eq 'markdown-viewer' -and
                    $Graphics -ne '1') { $arguments.Add('-TextOnly') }
                if ($LocalFloatMath -eq '1' -and
                    $module.System -in @('focal', 'tinybasic')) {
                    $arguments.Add('-LocalFloatMath')
                }
                Invoke-BuildTool $powerShell $arguments.ToArray()
                $source = Join-Path $moduleOutput $module.Name
                if (-not [IO.File]::Exists($source)) {
                    throw "System APP build did not produce: $source"
                }
                if ($null -ne $buildKey) {
                    Publish-Catalog $source $module $buildKey
                }
                [IO.File]::Copy($source, $destination, $true)
            } else {
                Write-AtomicBytes $destination $cached
                $hits.Add($module.Name)
            }
            $built.Add($module.Name)
        }
        Invoke-BuildTool $powerShell @(
            '-NoLogo', '-NoProfile', '-File',
            (Join-Path $ProjectRoot `
                'tools/.mk61-app/build-terminal-help.ps1'),
            '-ResidentElf', $resident, '-OutputDirectory', $stage,
            '-UsbText')
        $built.Add('HELP0.TXT')
        $built.Add('HELP1.TXT')

        foreach ($name in $Canonical) {
            $source = Join-Path $stage $name
            $destination = Join-Path $output $name
            if ([IO.File]::Exists($source)) {
                Write-AtomicBytes $destination ([IO.File]::ReadAllBytes($source))
            } elseif ([IO.File]::Exists($destination)) {
                Remove-Item -LiteralPath $destination -Force
            }
        }
        [ordered]@{
            abi = 6; resident = $resident; output = $output
            apps = $built.ToArray(); graphics = $Graphics -eq '1'
            ui_fonts = $UiFonts -eq '1'
            local_float_math = $LocalFloatMath -eq '1'
            catalog = $CatalogDirectory; catalog_hits = $hits.ToArray()
            builder = 'PowerShell'
        } | ConvertTo-Json -Depth 4 | Write-Host
    } finally {
        if ([IO.Directory]::Exists($workspace)) {
            Remove-Item -LiteralPath $workspace -Recurse -Force
        }
    }
} catch {
    [Console]::Error.WriteLine(
        "System APP build: $($_.Exception.Message)")
    exit 1
}
