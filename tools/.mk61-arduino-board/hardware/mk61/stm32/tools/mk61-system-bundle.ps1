#requires -Version 5.1

$script:Mk61SystemFiles = @('USBDISK.APP', 'SETUP.APP', 'FOCAL.APP', 'BASIC.APP',
    'LANGVM.APP', 'LANGIN.APP', 'WBMP.APP', 'MARKDOWN.APP', 'CHIP8.APP',
    'EXPLORER.APP', 'HELP0.TXT', 'HELP1.TXT', 'VMCache/VMSTORE.APP')

function Get-Mk61FirmwareProfile {
    param([string]$BundleProfile)
    return $BundleProfile -creplace '^(mini-v[23])-(?:lcd1602|oled1602)-', '$1-'
}

function Get-Mk61ProfileHash {
    param([string]$Profile)
    [uint64]$value = 2166136261
    foreach ($byte in [Text.Encoding]::ASCII.GetBytes($Profile)) {
        $value = (($value -bxor $byte) * 16777619) -band 4294967295
    }
    return $value.ToString('X8')
}

function Get-Mk61ResidentIdentity {
    param([string]$Path)
    [byte[]]$bytes = [IO.File]::ReadAllBytes($Path)
    $text = [Text.Encoding]::ASCII.GetString($bytes)
    $magic = 'MK61FWC' + [char]0
    $footer = $text.IndexOf($magic, [StringComparison]::Ordinal)
    if ($footer -lt 0 -or $footer % 4 -ne 0 -or $footer + 40 -gt $bytes.Length -or
        $text.IndexOf($magic, $footer + 1, [StringComparison]::Ordinal) -ge 0) {
        throw 'current resident has no unique aligned firmware footer'
    }
    $build = [BitConverter]::ToUInt32($bytes, $footer + 24)
    if ([BitConverter]::ToUInt16($bytes, $footer + 8) -ne 1 -or
        [BitConverter]::ToUInt16($bytes, $footer + 10) -ne 40 -or
        [BitConverter]::ToUInt32($bytes, $footer + 12) -ne 134217728 -or
        [BitConverter]::ToUInt32($bytes, $footer + 16) -ne $bytes.Length -or
        $build -eq 0 -or $build -ne [BitConverter]::ToUInt32($bytes, $footer + 20) -or
        [BitConverter]::ToUInt32($bytes, $footer + 32) -ne 1 -or
        [BitConverter]::ToUInt32($bytes, $footer + 36) -ne 0) {
        throw 'current resident is not a sealed CRC-required firmware'
    }
    return [pscustomobject]@{
        build_id = $build.ToString('X8')
        profile_id = ([BitConverter]::ToUInt32($bytes, $footer + 28)).ToString('X8')
    }
}

function Get-Mk61FileSha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path -ErrorAction Stop).Hash
}

function Get-Mk61SystemInventory {
    param([string]$System)
    $result = @()
    foreach ($file in @(Get-ChildItem -LiteralPath $System -Recurse -File -Force)) {
        $name = $file.FullName.Substring($System.TrimEnd('\', '/').Length + 1).Replace('\', '/')
        if ($name -cnotin $script:Mk61SystemFiles) { throw "unexpected System file: $name" }
        $result += [pscustomobject]@{
            name = $name; size = $file.Length; sha256 = Get-Mk61FileSha256 $file.FullName
        }
    }
    foreach ($required in @('HELP0.TXT', 'HELP1.TXT')) {
        if ($required -cnotin @($result | ForEach-Object { $_.name })) {
            throw "incomplete System bundle: missing $required"
        }
    }
    return @($result | Sort-Object name)
}

function Write-Mk61SystemManifest {
    param([string]$Stage, [string]$Bundle, [string]$Mcu)
    if (-not $Bundle.StartsWith('mk61s-M-', [StringComparison]::Ordinal) -or
        -not $Bundle.EndsWith("-$Mcu", [StringComparison]::Ordinal)) {
        throw "invalid bundle name: $Bundle"
    }
    $label = $Bundle.Substring(8, $Bundle.Length - 8 - $Mcu.Length - 1)
    $profile = Get-Mk61FirmwareProfile $label
    $resident = Join-Path $Stage "$Bundle.bin"
    $identity = Get-Mk61ResidentIdentity $resident
    if ($identity.profile_id -cne (Get-Mk61ProfileHash $profile)) {
        throw "compiled firmware identity does not match bundle profile $profile"
    }
    $manifest = [ordered]@{
        schema = 1; bundle = $Bundle; mcu = $Mcu; profile = $profile
        build_id = $identity.build_id; profile_id = $identity.profile_id
        resident_sha256 = Get-Mk61FileSha256 $resident
        elf_sha256 = Get-Mk61FileSha256 (Join-Path $Stage "$Bundle.elf")
        installer_sha256 = Get-Mk61FileSha256 (Join-Path $Stage 'mk61-system-installer.ps1')
        system = @(Get-Mk61SystemInventory (Join-Path $Stage 'System'))
    }
    [IO.File]::WriteAllText((Join-Path $Stage 'build.system.json'),
        ($manifest | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
}

function Get-VerifiedMk61SystemManifest {
    param([string]$Stage, [string]$Bundle, [string]$Mcu, [string]$Resident)
    $path = Join-Path $Stage 'build.system.json'
    if (-not [IO.File]::Exists($path)) {
        throw 'current build has no build.system.json; recompile with the current MK61s board package'
    }
    $manifest = [IO.File]::ReadAllText($path) | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.bundle -cne $Bundle -or $manifest.mcu -cne $Mcu) {
        throw 'System manifest does not match the selected Arduino build'
    }
    $stagedResident = Join-Path $Stage "$Bundle.bin"
    $identity = Get-Mk61ResidentIdentity $stagedResident
    if ($manifest.build_id -cne $identity.build_id -or
        $manifest.profile_id -cne $identity.profile_id -or
        $identity.profile_id -cne (Get-Mk61ProfileHash $manifest.profile)) {
        throw 'System manifest identity does not match the compiled firmware'
    }
    foreach ($record in @(
        @($stagedResident, $manifest.resident_sha256),
        @($Resident, $manifest.resident_sha256),
        @((Join-Path $Stage "$Bundle.elf"), $manifest.elf_sha256),
        @((Join-Path $Stage 'mk61-system-installer.ps1'), $manifest.installer_sha256))) {
        if ((Get-Mk61FileSha256 $record[0]) -cne $record[1]) {
            throw "build artifact changed or belongs to another build: $($record[0])"
        }
    }
    $actual = @(Get-Mk61SystemInventory (Join-Path $Stage 'System'))
    $expected = @($manifest.system | Sort-Object name)
    if ($actual.Count -ne $expected.Count) { throw 'System bundle file set changed after compilation' }
    for ($index = 0; $index -lt $actual.Count; $index++) {
        foreach ($field in @('name', 'size', 'sha256')) {
            if ($actual[$index].$field -cne $expected[$index].$field) {
                throw "System bundle changed after compilation: $($actual[$index].name)"
            }
        }
    }
    return $manifest
}

function Sync-Mk61PublishedSystem {
    param([string]$Source, [string]$Destination)
    foreach ($name in $script:Mk61SystemFiles) {
        $from = Join-Path $Source $name
        $to = Join-Path $Destination $name
        if ([IO.File]::Exists($from)) {
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $to))
            Copy-Item -LiteralPath $from -Destination $to -Force
        } elseif ([IO.File]::Exists($to)) {
            Remove-Item -LiteralPath $to -Force
        }
    }
}
