# Windows builds do not require Python to record their actual final options.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Bundle,
      [Parameter(Mandatory=$true)][string]$Firmware,
      [Parameter(Mandatory=$true)][string]$Profile,
      [Parameter(Mandatory=$true)][ValidateSet('f401','f411')][string]$Mcu)
$ErrorActionPreference = 'Stop'
$schema = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'program-capabilities.json') -Raw | ConvertFrom-Json
$flags = [IO.File]::ReadAllText((Join-Path $Bundle 'build.flags'))
$definitions = @{}
foreach ($match in [regex]::Matches($flags, '(?:^|\s)-D(\w+)(?:=([^\s]+))?')) {
    $value = $match.Groups[2].Value
    if (-not $value) { $value = '1' }
    $definitions[$match.Groups[1].Value] = $value
}
function Get-Bit([string]$Name) {
    if ($definitions[$Name] -notin @('0','1')) { throw "missing/ambiguous final definition: $Name" }
    return $definitions[$Name] -eq '1'
}
$features = [ordered]@{}
foreach ($feature in $schema.features.PSObject.Properties) { $features[$feature.Name] = Get-Bit $feature.Value }
$features.graphics = $features.usb_screen
foreach ($name in $schema.graphics_defines) { if ($definitions.ContainsKey($name)) { $features.graphics = $true } }
$features.bitmap = $features.graphics -or ($definitions.ContainsKey('MK61_OLED1602_WS0010') -and $definitions['MK61_WS0010_GRAPHICS_100X16'] -eq '1')
$features.apps = $true; $features.s1 = $true; $features.math = $features.focal -or $features.basic
$features.urq = (Test-Path -LiteralPath (Join-Path $Bundle 'Apps/URQ.APP')) -and `
                (Test-Path -LiteralPath (Join-Path $Bundle 'Apps/URQUI.APP'))
$system = [ordered]@{}
foreach ($feature in $schema.system_apps.PSObject.Properties) {
    if ($features[$feature.Name] -and (Get-Bit $feature.Value[0]) -and -not ($feature.Name -eq 'wbmp' -and $features.markdown)) { $system[$feature.Name] = $feature.Value[1] }
}
[byte[]]$image = [IO.File]::ReadAllBytes($Firmware)
$marker = [Text.Encoding]::ASCII.GetBytes("MK61FWC`0")
$found = @()
for ($i=0; $i -le $image.Length-40; $i+=4) {
    $matches = $true
    for ($j=0; $j -lt 8; $j++) { if ($image[$i+$j] -ne $marker[$j]) { $matches = $false; break } }
    if ($matches -and [BitConverter]::ToUInt16($image,$i+8) -eq 1 -and [BitConverter]::ToUInt16($image,$i+10) -eq 40 -and
        [BitConverter]::ToUInt32($image,$i+16) -eq $image.Length -and [BitConverter]::ToUInt32($image,$i+24) -ne 0) {
        $found += [BitConverter]::ToUInt32($image,$i+24).ToString('X8')
    }
}
if ($found.Count -ne 1) { throw 'a uniquely sealed firmware is required' }
$name = [IO.Path]::GetFileName($Firmware)
$identity = $Profile
if ($Profile.StartsWith('classic-') -or $Profile -eq '40th') { $identity += '-uc1609' }
$hash = [Security.Cryptography.SHA256]::Create()
try { $digest = ([BitConverter]::ToString($hash.ComputeHash($image))).Replace('-','').ToLowerInvariant() } finally { $hash.Dispose() }
$metadata = [ordered]@{ format=1; platform='stm32'; mcu=$Mcu; profile=$Profile; device_profile=$identity;
    build_id=$found[0]; abi=$schema.abi; firmware=$name; firmware_sha256=$digest;
    features=$features; system_apps=$system; app_memory_limit=20480 }
[IO.File]::WriteAllText((Join-Path $Bundle 'program-capabilities.json'), ($metadata | ConvertTo-Json -Depth 8) + "`n", (New-Object Text.UTF8Encoding($false)))
