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

    [IO.File]::WriteAllText((Join-Path $catalog 'catalog.json'), 'not json')
    $missing = Get-CachedPayload ([pscustomobject]@{
        Name = 'BROKEN.APP'; System = 'broken'
    }) 'broken'
    Assert-Test ($null -eq $missing) `
        'corrupt catalog was treated as a cache hit'
    Assert-Test (-not [IO.File]::Exists((Join-Path $catalog 'catalog.json'))) `
        'corrupt catalog was not quarantined for rebuild'

    Write-Host 'system_app_catalog_powershell_self_test: ok'
} finally {
    $env:MK61_POWERSHELL_IMPORT_ONLY = $null
    if ([IO.Directory]::Exists($temporary)) {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
