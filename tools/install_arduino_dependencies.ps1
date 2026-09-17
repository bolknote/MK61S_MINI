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
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [ValidateRange(1, 8)][int]$Attempts = 1
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        & arduino-cli @Arguments
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) { return }
        if ($attempt -lt $Attempts) {
            $delaySeconds = [Math]::Min(8, [Math]::Pow(2, $attempt - 1))
            Write-Warning (
                "arduino-cli failed ($exitCode), retrying in " +
                "$delaySeconds s ($attempt/$Attempts): " +
                ($Arguments -join ' '))
            Start-Sleep -Seconds $delaySeconds
        }
    }
    throw "arduino-cli failed ($exitCode): $($Arguments -join ' ')"
}

Invoke-ArduinoCli -Arguments @('config', 'init', '--overwrite')
Invoke-ArduinoCli -Arguments @(
    'config', 'set', 'board_manager.additional_urls',
    [string]$manifest.toolchain.stm32_package_url)
Invoke-ArduinoCli -Arguments @('core', 'update-index') -Attempts 4
Invoke-ArduinoCli -Arguments @(
    'core', 'install',
    "STMicroelectronics:stm32@$($manifest.toolchain.stm32_core)") -Attempts 4
Invoke-ArduinoCli -Arguments @('lib', 'update-index') -Attempts 4
foreach ($library in $manifest.toolchain.libraries.PSObject.Properties) {
    Invoke-ArduinoCli -Arguments @(
        'lib', 'install', "$($library.Name)@$($library.Value)") -Attempts 4
}
