[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Sketchbook,
    [string]$ConfigFile
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$configArguments = @()
if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $configArguments = @('--config-file', $ConfigFile)
}
$expectedPlatform = [IO.Path]::GetFullPath(
    (Join-Path $Sketchbook 'hardware/mk61/stm32')).Replace('\', '/')

# These are the exact saved choices that broke after two-state menus became
# builtin/APP/disabled. Run against the installed platform through Arduino,
# not by inspecting the repository's boards.txt or selecting the new "app".
foreach ($modules in @(
    @('mk61_basic'),
    @('mk61_focal'),
    @('mk61_chip8'),
    @('mk61_basic', 'mk61_focal', 'mk61_chip8')
)) {
    $choices = ($modules | ForEach-Object { "$_=enabled" }) -join ','
    $fqbn = "mk61:stm32:mk61_f401_app:$choices"
    $output = & arduino-cli @configArguments board details `
        --fqbn $fqbn --show-properties=expanded
    if ($LASTEXITCODE -ne 0) {
        throw "Arduino rejected saved FQBN: $fqbn"
    }
    $properties = @{}
    foreach ($line in $output) {
        if ($line -match '^([^=]+)=(.*)$') {
            $properties[$Matches[1]] = $Matches[2]
        }
    }
    $actualPlatform = [string]$properties['build.board.platform.path']
    if ($actualPlatform.Replace('\', '/') -ne $expectedPlatform) {
        throw "Arduino loaded another board package: $actualPlatform"
    }
    foreach ($module in $modules) {
        foreach ($property in @("build.$module", "build.${module}_app")) {
            if ($properties[$property] -ne '1') {
                throw "Saved FQBN did not select APP: $fqbn ($property)"
            }
        }
    }
    Write-Host "Accepted saved FQBN: $fqbn"
}
