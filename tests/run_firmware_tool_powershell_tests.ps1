#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$tool = Join-Path $root 'tools/.mk61-firmware/mk61-firmware.ps1'
$launcher = Join-Path $root 'tools/mk61-firmware.cmd'
$pwsh = (Get-Process -Id $PID).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Invoke-Tool {
    param([string[]]$Arguments)
    $output = & $pwsh -NoLogo -NoProfile -File $tool @Arguments 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

Assert-True (Test-Path -LiteralPath $tool -PathType Leaf) 'PowerShell firmware tool is missing'
Assert-True (Test-Path -LiteralPath $launcher -PathType Leaf) 'Windows command launcher is missing'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $root 'tools/mk61-firmware'))) 'legacy shell entry point is still exposed'
Assert-True (-not (Test-Path -LiteralPath (Join-Path $root 'tools/mk61-firmware.ps1'))) 'legacy PowerShell entry point is still exposed'
$launcherText = [IO.File]::ReadAllText($launcher)
Assert-True ($launcherText -match '\A:; exec "\$\(dirname "\$0"\)/\.mk61-firmware/mk61-firmware\.sh" "\$@"') 'launcher is not a shell/batch polyglot'
Assert-True ($launcherText -match '(?i)pwsh\.exe -NoLogo -NoProfile -ExecutionPolicy Bypass') 'launcher options differ'
Assert-True ($launcherText -match '%~dp0\.mk61-firmware\\mk61-firmware\.ps1') 'launcher does not use its own directory'
$tokens = $null
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile($tool, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) {
    throw ('PowerShell parser errors: ' + (@($parseErrors | ForEach-Object { $_.Message }) -join '; '))
}

$profiles = Invoke-Tool @('--list-profiles')
Assert-True ($profiles.ExitCode -eq 0) '--list-profiles failed'
$expected = @(
    "mini-v3-a00`tmini V3 · LCD1602 A00`t-DMK61_LCD1602_A00"
    "mini-v3-a02`tmini V3 · LCD1602 A02`t-DMK61_LCD1602_A02"
    "mini-v2-a00`tmini V2 · LCD1602 A00`t-DREVISION_V2 -DMK61_LCD1602_A00"
    "mini-v2-a02`tmini V2 · LCD1602 A02`t-DREVISION_V2 -DMK61_LCD1602_A02"
    "classic-v2`tClassic V2 · UC1609 192×64`t-DMK61_BOARD_CLASSIC_V2"
    "classic-v3`tClassic V3 · UC1609 192×64`t-DMK61_BOARD_CLASSIC_V3"
    "40th`tMK61s 40th · UC1609 192×64`t-DMK61_BOARD_40TH"
)
Assert-True (($profiles.Output -join "`n") -eq ($expected -join "`n")) 'profile matrix differs from Bash tool'

$invalid = Invoke-Tool @('--profile','unsupported','--build')
Assert-True ($invalid.ExitCode -eq 2) "invalid profile returned $($invalid.ExitCode), expected 2"

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("mk61-powershell-tests-" + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $tempRoot)
$oldConfig = $env:MK61_CONFIG_FILE
$oldBuild = $env:MK61_BUILD_ROOT
try {
    $config = Join-Path $tempRoot 'settings.conf'
    $env:MK61_CONFIG_FILE = $config
    $env:MK61_BUILD_ROOT = Join-Path $tempRoot 'build'
    [IO.File]::WriteAllLines($config, @(
        'PROFILE=classic-v3'
        'DFU_UTIL_PATH=C:\Tools\dfu-util.exe'
        'MK61_ENABLE_FOCAL=0'
        'MK61_ENABLE_TINYBASIC=1'
        'MK61_ENABLE_WBMP_VIEWER=0'
        'MK61_ENABLE_EXTENDED_FONT_SETTINGS=1'
        'MK61_USER_EXPLORER_SHORTCUT=0'
        'MK61_MATH_BACKEND=1'
    ))

    $configResult = Invoke-Tool @('--show-config')
    Assert-True ($configResult.ExitCode -eq 0) '--show-config failed'
    $configText = $configResult.Output -join "`n"
    Assert-True ($configText -match '(?m)^PLATFORM=classic-v3$') 'legacy platform migration failed'
    Assert-True ($configText -match '(?m)^SCREEN=uc1609$') 'legacy screen migration failed'
    Assert-True ($configText -match '(?m)^PROFILE=classic-v3$') 'legacy profile migration failed'
    Assert-True ($configText -match '(?m)^DFU_UTIL_PATH=C:\\Tools\\dfu-util\.exe$') 'DFU path was not preserved'
    Assert-True ($configText -match '(?m)^MK61_ENABLE_FOCAL=0$') 'FOCAL flag was not preserved'
    Assert-True ($configText -match '(?m)^MK61_ENABLE_EXTENDED_FONT_SETTINGS=1$') 'font flag was not preserved'
    Assert-True ($configText -match 'COMPILE_FLAGS=-DMK61_BOARD_CLASSIC_V3 .*MK61_MATH_BACKEND=1') 'compile flags differ'

    $override = Invoke-Tool @('--profile','mini-v3-a00','--show-config')
    Assert-True (($override.Output -join "`n") -match '(?m)^PROFILE=mini-v3-a00$') 'CLI profile override failed'

    [IO.File]::WriteAllLines($config, @('PLATFORM=classic-v3','SCREEN=lcd1602-a00'))
    $incompatible = Invoke-Tool @('--show-config')
    $incompatibleText = $incompatible.Output -join "`n"
    Assert-True ($incompatibleText -match '(?m)^PLATFORM=classic-v3$') 'incompatible platform was lost'
    Assert-True ($incompatibleText -match '(?m)^SCREEN=lcd1602-a00$') 'incompatible screen was lost'
    Assert-True ($incompatibleText -match '(?m)^PROFILE=$') 'incompatible pair produced a profile'
} finally {
    $env:MK61_CONFIG_FILE = $oldConfig
    $env:MK61_BUILD_ROOT = $oldBuild
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

[Console]::WriteLine('firmware_tool_powershell_tests: ok')
