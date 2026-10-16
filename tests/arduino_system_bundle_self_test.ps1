#requires -Version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'fixtures/arduino_bundle.ps1')
. (Join-Path $root 'tools/.mk61-arduino-board/hardware/mk61/stm32/tools/mk61-system-bundle.ps1')
# The Arduino-launched 5.1 process can lack this optional module function.
function Get-FileHash { throw 'Get-FileHash is deliberately unavailable' }
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61 bundle check ' + [guid]::NewGuid().ToString('N'))
$bundle = 'mk61s-M-mini-v2-lcd1602-a00-f411'
$stage = Join-Path (Join-Path $work 'mk61-system-apps') $bundle
$system = Join-Path $stage 'System'
$resident = Join-Path $work 'code.ino.bin'
function Assert-Rejected {
    try { [void](Get-VerifiedMk61SystemManifest $stage $bundle f411 $resident) }
    catch { return }
    throw 'A changed, incomplete or mismatched bundle passed preflight'
}
try {
    [void][IO.Directory]::CreateDirectory((Join-Path $system 'VMCache'))
    Copy-Item (Join-Path $root 'tools/.mkc/mkc.ps1') (Join-Path $stage 'mk61-system-installer.ps1')
    [IO.File]::WriteAllBytes((Join-Path $system 'VMCache/VMSTORE.APP'), [byte[]]::new(64))
    $id = New-Mk61TestArduinoBundle $work $bundle f411 -ResidentUsbDisk
    $manifest = Get-VerifiedMk61SystemManifest $stage $bundle f411 $resident
    if ($manifest.profile -cne 'mini-v2-a00' -or $manifest.build_id -cne $id.build_id) {
        throw 'Manifest differs from the sealed firmware identity'
    }
    [byte[]]$original = [IO.File]::ReadAllBytes($resident)
    # Ignore the non-header magic in executable code, but still reject two
    # genuine format headers before trusting any metadata.
    [byte[]]$duplicate = [byte[]]::new($original.Length + 40)
    [Array]::Copy($original, $duplicate, $original.Length)
    [Array]::Copy($original, 16, $duplicate, $original.Length, 40)
    [IO.File]::WriteAllBytes($resident, $duplicate)
    $duplicateRejected = $false
    try { [void](Get-Mk61ResidentIdentity $resident) }
    catch { $duplicateRejected = $_.Exception.Message -match 'multiple firmware footers' }
    if (-not $duplicateRejected) { throw 'Two real footer headers were accepted' }
    [IO.File]::WriteAllBytes($resident, $original)
    [byte[]]$changed = $original.Clone()
    $changed[0] = $changed[0] -bxor 1
    [IO.File]::WriteAllBytes($resident, $changed)
    Assert-Rejected
    [IO.File]::WriteAllBytes($resident, $original)
    $help = Join-Path $system 'HELP0.TXT'
    [byte[]]$helpBytes = [IO.File]::ReadAllBytes($help)
    [IO.File]::WriteAllText($help, 'changed')
    Assert-Rejected
    [IO.File]::WriteAllBytes($help, $helpBytes)
    Remove-Item -LiteralPath $help
    Assert-Rejected
    [IO.File]::WriteAllBytes($help, $helpBytes)
    [IO.File]::WriteAllBytes((Join-Path $system 'BASIC.APP'), [byte[]]::new(64))
    Assert-Rejected
    Remove-Item -LiteralPath (Join-Path $system 'BASIC.APP')
    $installer = Join-Path $stage 'mk61-system-installer.ps1'
    [byte[]]$installerBytes = [IO.File]::ReadAllBytes($installer)
    [IO.File]::WriteAllText($installer, '# stale installer')
    Assert-Rejected
    [IO.File]::WriteAllBytes($installer, $installerBytes)
    [void](Get-VerifiedMk61SystemManifest $stage $bundle f411 $resident)

    $published = Join-Path $work 'published/System'
    Sync-Mk61PublishedSystem $system $published
    if (-not [IO.File]::Exists((Join-Path $published 'VMCache/VMSTORE.APP'))) {
        throw 'Published System lost the nested VM cache helper'
    }
    [IO.File]::WriteAllText((Join-Path $published 'VMCache/VMC-0042.APP'), 'retained data')
    Remove-Item -LiteralPath (Join-Path $system 'VMCache/VMSTORE.APP')
    Sync-Mk61PublishedSystem $system $published
    if ([IO.File]::Exists((Join-Path $published 'VMCache/VMSTORE.APP')) -or
        -not [IO.File]::Exists((Join-Path $published 'VMCache/VMC-0042.APP'))) {
        throw 'Published System did not remove only the disabled helper'
    }
    Write-Host 'arduino_system_bundle_self_test: ok (identity, hashes, complete System, nested helper)'
} finally {
    if ([IO.Directory]::Exists($work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
