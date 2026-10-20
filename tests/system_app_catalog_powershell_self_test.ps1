#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$builder = Join-Path $root 'tools/build-system-app-bundle.ps1'
$temporary = Join-Path ([IO.Path]::GetTempPath()) (
    'mk61-app-catalog-ps-' + [guid]::NewGuid().ToString('N'))
$catalog = Join-Path $temporary 'catalog'
$powerShell = if ($PSVersionTable.PSEdition -eq 'Desktop') {
    Join-Path $PSHOME 'powershell.exe'
} else { (Get-Process -Id $PID).Path }

function Assert-Test {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function New-AppPayload {
    param([int]$Seed)
    [byte[]]$payload = New-Object byte[] 80
    [Array]::Copy([Text.Encoding]::ASCII.GetBytes("MK61APP`0"), $payload, 8)
    [BitConverter]::GetBytes([uint16]6).CopyTo($payload, 12)
    [BitConverter]::GetBytes($Seed).CopyTo($payload, 64)
    return $payload
}

try {
    [IO.Directory]::CreateDirectory($temporary) | Out-Null
    $processes = New-Object 'System.Collections.Generic.List[object]'
    for ($index = 0; $index -lt 16; $index++) {
        $source = Join-Path $temporary "source-$index.APP"
        [IO.File]::WriteAllBytes($source, (New-AppPayload $index))
        $command = @"
`$env:MK61_POWERSHELL_IMPORT_ONLY = '1'
. '$($builder.Replace("'", "''"))' -ResidentElf x -ArmToolchainBin x -OutputDirectory x -CatalogDirectory '$($catalog.Replace("'", "''"))' -UiFonts 0 -Graphics 0
`$module = [pscustomobject]@{ Name = 'TEST$index.APP'; System = 'test-$index' }
Publish-Catalog '$($source.Replace("'", "''"))' `$module 'build-$index'
"@
        $encoded = [Convert]::ToBase64String(
            [Text.Encoding]::Unicode.GetBytes($command))
        $processes.Add((Start-Process -FilePath $powerShell -ArgumentList @(
            '-NoLogo', '-NoProfile', '-EncodedCommand', $encoded) `
            -PassThru))
    }
    foreach ($process in $processes) {
        $process.WaitForExit()
        Assert-Test ($process.ExitCode -eq 0) `
            "catalog publisher failed with exit code $($process.ExitCode)"
        $process.Dispose()
    }

    $env:MK61_POWERSHELL_IMPORT_ONLY = '1'
    . $builder -ResidentElf x -ArmToolchainBin x -OutputDirectory x `
        -CatalogDirectory $catalog -UiFonts 0 -Graphics 0
    $manifest = Read-Catalog $catalog
    Assert-Test (@($manifest.apps).Count -eq 16) `
        'parallel catalog publish lost a record'
    Assert-Test (@(Get-ChildItem -LiteralPath (Join-Path $catalog 'objects') `
        -Filter '*.APP' -File).Count -eq 16) `
        'parallel catalog publish left an invalid object set'
    for ($index = 0; $index -lt 16; $index++) {
        $module = [pscustomobject]@{
            Name = "TEST$index.APP"; System = "test-$index"
        }
        [byte[]]$payload = Get-CachedPayload $module "build-$index"
        Assert-Test ($null -ne $payload) "TEST$index.APP was not cached"
        Assert-Test ([BitConverter]::ToInt32($payload, 64) -eq $index) `
            "TEST$index.APP cached the wrong payload"
    }

    # A local APP can exceed CI compactness ceilings. Never treat it as
    # already checked when the same catalog is consumed by CI.
    $originalCi = [Environment]::GetEnvironmentVariable('CI', 'Process')
    try {
        $module = [pscustomobject]@{ Name = 'FOCAL.APP'; System = 'focal' }
        $source = Join-Path $temporary 'FOCAL.APP'
        [IO.File]::WriteAllBytes($source, (New-AppPayload 42))
        $env:CI = 'false'
        $localKey = Get-AppBuildKey 'sources' $module
        Publish-Catalog $source $module $localKey | Out-Null
        Assert-Test ($null -ne (Get-CachedPayload $module $localKey)) `
            'ordinary build did not reuse its own APP'
        foreach ($ci in @('true', 'TRUE', '1', ' true ')) {
            $env:CI = $ci
            $ciKey = Get-AppBuildKey 'sources' $module
            Assert-Test ($ciKey -ne $localKey) 'CI reused an unchecked build key'
            Assert-Test ($null -eq (Get-CachedPayload $module $ciKey)) `
                'CI reused an unchecked ordinary APP'
        }
        foreach ($ci in @($null, '', '0')) {
            $env:CI = $ci
            Assert-Test ((Get-AppBuildKey 'sources' $module) -eq $localKey) `
                'ordinary build used a CI build key'
        }
    } finally { $env:CI = $originalCi }

    [IO.File]::WriteAllText((Join-Path $catalog 'catalog.json'), 'not json')
    $missing = Get-CachedPayload ([pscustomobject]@{
        Name = 'BROKEN.APP'; System = 'broken'
    }) 'broken'
    Assert-Test ($null -eq $missing) `
        'corrupt catalog was treated as a cache hit'
    Assert-Test (-not [IO.File]::Exists((Join-Path $catalog 'catalog.json'))) `
        'corrupt catalog was not quarantined for rebuild'

    # The default IDE/GCC wrappers do not pass VM switches. The ELF must
    # select compiler APPs and include hot/cold executors only for overlay mode.
    function Invoke-BuildTool { return $script:residentSymbols }
    foreach ($mode in @(0, 1, 2)) {
        $script:residentSymbols = '{0:x8} A mk61_language_vm_mode' -f $mode
        $LanguageVmCompiler = 'auto'
        $OverlayLanguageVm = 'auto'
        $Focal = if ($mode -eq 0) { '0' } else { '1' }
        Set-LanguageVmPlacement 'toolchain' 'resident.elf'
        Assert-Test (($LanguageVmCompiler -eq '1') -eq ($mode -ne 0)) `
            'resident VM metadata selected the wrong compiler mode'
        Assert-Test ($Enabled['language-vm'] -eq ($mode -eq 2)) `
            'resident VM metadata selected the wrong hot executor'
        Assert-Test ($Enabled['language-input'] -eq ($mode -eq 2)) `
            'resident VM metadata selected the wrong cold executor'
    }
    $compilerVariant = Get-AppVariant 'tinybasic'
    foreach ($cacheMode in @(0, 1)) {
        $script:residentSymbols = '{0:x8} A mk61_vm_file_cache_enabled' -f $cacheMode
        $OverlayLanguageVm = '1'
        $Enabled['language-vm'] = $true
        Set-VmFileCachePolicy 'toolchain' 'resident.elf'
        Assert-Test ($Enabled['vm-file-cache'] -eq ($cacheMode -eq 1)) `
            'resident cache metadata selected the wrong helper policy'
    }
    foreach ($mode in @(0, 1)) {
        $script:residentSymbols = ('{0:x8} A mk61_terminal_commands_as_app' -f $mode) + "`n00000003 A mk61_terminal_command_abi"
        Set-VmFileCachePolicy 'toolchain' 'resident.elf'
        Assert-Test ($Enabled['terminal'] -eq ($mode -eq 1)) 'wrong terminal APP policy'
        Assert-Test ($Enabled['terminal-clock'] -eq ($mode -eq 1)) 'wrong clock APP policy'
    }
    $script:residentSymbols = "00000001 A mk61_terminal_commands_as_app`n00000002 A mk61_terminal_command_abi"
    $rejected = $false
    try { Set-VmFileCachePolicy 'toolchain' 'resident.elf' }
    catch { $rejected = $_.Exception.Message -like '*rebuild the firmware*' }
    Assert-Test $rejected 'stale resident terminal ABI was packaged'
    Assert-Test ('TERMINAL.APP' -in $Canonical -and 'CLOCK.APP' -in $Canonical) 'missing terminal helpers'
    Assert-Test ('VMCache/VMSTORE.APP' -in $Canonical) 'nested helper is not canonical'
    $LanguageVmCompiler = '0'
    Assert-Test ($compilerVariant -ne (Get-AppVariant 'tinybasic')) `
        'compiler BASIC reused the native interpreter cache variant'

    Write-Host 'system_app_catalog_powershell_self_test: ok'
} finally {
    $env:MK61_POWERSHELL_IMPORT_ONLY = $null
    if ([IO.Directory]::Exists($temporary)) {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
