#requires -Version 5.1

[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$manifestPath = Join-Path $root 'tools/release-contract.json'
if (-not [IO.File]::Exists($manifestPath)) {
    throw "Release contract is missing: $manifestPath"
}
$manifest = ConvertFrom-Json -InputObject (
    [IO.File]::ReadAllText($manifestPath))

function Invoke-ArduinoCli {
    param([string[]]$Arguments)
    & arduino-cli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "arduino-cli failed ($LASTEXITCODE): $($Arguments -join ' ')"
    }
}

Invoke-ArduinoCli @('config', 'init', '--overwrite')
Invoke-ArduinoCli @(
    'config', 'set', 'board_manager.additional_urls',
    [string]$manifest.toolchain.stm32_package_url)
Invoke-ArduinoCli @('core', 'update-index')
Invoke-ArduinoCli @(
    'core', 'install',
    "STMicroelectronics:stm32@$($manifest.toolchain.stm32_core)")
Invoke-ArduinoCli @('lib', 'update-index')
foreach ($library in $manifest.toolchain.libraries.PSObject.Properties) {
    Invoke-ArduinoCli @('lib', 'install', "$($library.Name)@$($library.Value)")
}
