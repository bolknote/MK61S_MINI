#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $root 'tools/build-gcc.cmd'
$backend = Join-Path $root 'tools/.mk61-gcc/build.ps1'
$cmakeProject = Join-Path $root 'tools/.mk61-gcc/CMakeLists.txt'
$toolchain = Join-Path $root 'tools/.mk61-gcc/arm-none-eabi.cmake'
$firmwareMain = Join-Path $root 'tools/.mk61-gcc/firmware_main.cpp.in'
$firmwarePowerShell = Join-Path $root `
    'tools/.mk61-firmware/mk61-firmware.ps1'
$firmwareShell = Join-Path $root `
    'tools/.mk61-firmware/mk61-firmware.sh'
$releaseWorkflow = Join-Path $root `
    '.github/workflows/firmware-release.yml'
$arduinoSetupAction = Join-Path $root `
    '.github/actions/setup-arduino-cli/action.yml'
$arduinoSetupScript = Join-Path $root `
    '.github/actions/setup-arduino-cli/install.ps1'
$pwsh = (Get-Process -Id $PID).Path

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Invoke-Backend {
    param([string[]]$Arguments)
    $output = & $pwsh -NoLogo -NoProfile -File $backend @Arguments 2>&1
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = @($output)
    }
}

foreach ($file in @(
    $launcher,
    $backend,
    $cmakeProject,
    $toolchain,
    $firmwareMain,
    $firmwarePowerShell,
    $firmwareShell,
    $releaseWorkflow,
    $arduinoSetupAction,
    $arduinoSetupScript
)) {
    Assert-True (Test-Path -LiteralPath $file -PathType Leaf) `
        "direct GCC build file is missing: $file"
}

$tokens = $null
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile(
    $backend, [ref]$tokens, [ref]$parseErrors)
Assert-True ($parseErrors.Count -eq 0) (
    "$backend has parser errors: " +
    (@($parseErrors | ForEach-Object { $_.Message }) -join '; '))

$launcherText = [IO.File]::ReadAllText($launcher)
Assert-True ($launcherText -match
    '\A:; exec pwsh -NoLogo -NoProfile -File "\$\(dirname "\$0"\)/\.mk61-gcc/build\.ps1" "\$@"') `
    'direct GCC launcher is not a shell/batch polyglot'
Assert-True ($launcherText -match
    '(?i)powershell\.exe -NoLogo -NoProfile -ExecutionPolicy Bypass') `
    'direct GCC launcher has no Windows PowerShell fallback'

$help = Invoke-Backend @('-Help')
$helpText = $help.Output -join "`n"
Assert-True ($help.ExitCode -eq 0) 'direct GCC help failed'
Assert-True ($helpText -match 'Arduino IDE and arduino-cli are not invoked') `
    'help does not state that the build is direct'
Assert-True ($helpText -match '(?s)mini-v2-a00.+classic-v2') `
    'help does not list the supported profiles'
Assert-True ($helpText -match '-Check\s+validate dependencies') `
    'help does not expose dependency preflight'
Assert-True ($helpText -match '-Markdown 0\|1\s+default 1') `
    'help does not expose the Markdown System APP'

$invalid = Invoke-Backend @(
    '-Profile', 'mini-v3-a00',
    '-Wbmp', '1',
    '-UsbScreen', '0')
Assert-True ($invalid.ExitCode -eq 1) `
    'LCD1602 profile accepted a graphics APP without USB Screen'
Assert-True (($invalid.Output -join "`n") -match
    'WBMP/CHIP-8 requires') `
    'invalid graphics selection has no useful diagnostic'

$backendText = [IO.File]::ReadAllText($backend)
$cmakeText = [IO.File]::ReadAllText($cmakeProject)
$toolchainText = [IO.File]::ReadAllText($toolchain)
$firmwareMainText = [IO.File]::ReadAllText($firmwareMain)
$firmwarePowerShellText = [IO.File]::ReadAllText($firmwarePowerShell)
$firmwareShellText = [IO.File]::ReadAllText($firmwareShell)
$releaseWorkflowText = [IO.File]::ReadAllText($releaseWorkflow)
$arduinoSetupActionText = [IO.File]::ReadAllText($arduinoSetupAction)
$arduinoSetupScriptText = [IO.File]::ReadAllText($arduinoSetupScript)
$allWorkflowText = @(
    Get-ChildItem -LiteralPath (Join-Path $root '.github/workflows') `
        -File -Filter '*.yml' |
        ForEach-Object { [IO.File]::ReadAllText($_.FullName) }
) -join "`n"
Assert-True ($backendText -notmatch
    '(?i)Get-CommandPath\s+[''"]arduino-cli(?:\.exe)?[''"]') `
    'direct GCC backend invokes arduino-cli'
Assert-True ($backendText -match
    "Join-Path \`$Directory 'Apps'[\s\S]+Remove-Item " +
    '-LiteralPath \$customApps -Recurse -Force') `
    'direct GCC backend can leave stale custom APP in a rebuilt bundle'
Assert-True ($cmakeText -match
    'add_library\(board ALIAS BLACKPILL_F401CC\)') `
    'CMake build does not select the F401 board'
Assert-True ($cmakeText -match 'CMAKE_EXPORT_COMPILE_COMMANDS ON') `
    'CMake build does not emit compile_commands.json'
Assert-True ($cmakeText -match 'MK61_ENABLE_MARKDOWN_VIEWER') `
    'CMake build does not forward the Markdown selection'
Assert-True ($cmakeText -match 'STM32 Arduino Core 2\.12\.0 is required') `
    'CMake build does not pin the STM32 Core'
Assert-True ($toolchainText -match 'arm-none-eabi-gcc') `
    'CMake toolchain does not use GNU Arm GCC'
Assert-True ($firmwareMainText -match '#include "mk61s-M\.ino"') `
    'generated firmware translation unit does not include the sketch'
Assert-True ($firmwarePowerShellText -match
    'Invoke-F401GccBundleBuild') `
    'PowerShell firmware frontend does not use the direct GCC backend'
Assert-True ($firmwareShellText -match
    'tools/build-gcc\.cmd[\s\S]+-BuildRoot') `
    'macOS/Linux firmware frontend does not use the direct GCC backend'
Assert-True ($releaseWorkflowText -match
    'tools/build-gcc\.cmd') `
    'release workflow does not use the canonical F401 GCC backend'
Assert-True ($releaseWorkflowText -match
    'mk61-firmware\.cmd[\s\S]+--mcu f401') `
    'platform matrix does not exercise the public F401 frontend'
Assert-True ($releaseWorkflowText -match
    'macos-latest[\s\S]+windows-latest') `
    'direct F401 GCC build is not checked on macOS and Windows'
Assert-True ($releaseWorkflowText -notmatch
    'arduino/setup-arduino-cli') `
    'release workflow still uses the Node.js 20 Arduino CLI action'
Assert-True ($allWorkflowText -notmatch
    'actions/checkout@v[1-5](?!\d)') `
    'a workflow still uses checkout before its Node.js 24 release'
Assert-True ($allWorkflowText -notmatch
    'actions/upload-artifact@v[1-6](?!\d)') `
    'a workflow still uses upload-artifact before its Node.js 24 release'
Assert-True (([regex]::Matches(
    $releaseWorkflowText,
    'uses:\s+\./\.github/actions/setup-arduino-cli')).Count -eq 2) `
    'release workflow does not consistently use the local Arduino CLI setup'
Assert-True ($releaseWorkflowText -match
    '(?m)^\s+ARDUINO_CLI_VERSION:\s+1\.5\.1\s*$') `
    'release workflow does not pin the checksum-covered Arduino CLI version'
Assert-True ($arduinoSetupActionText -match
    '(?m)^\s+using:\s+composite\s*$') `
    'local Arduino CLI setup is not a composite action'
Assert-True ($arduinoSetupScriptText -match
    "'1\.5\.1'\s*=\s*@\{") `
    'local Arduino CLI setup does not pin the configured release'
Assert-True ($arduinoSetupScriptText -match
    'Get-FileHash[\s\S]+Algorithm SHA256') `
    'local Arduino CLI setup does not verify its downloaded archive'
$f401Job = [regex]::Match(
    $releaseWorkflowText,
    '(?ms)^  f401-gcc-platforms:\r?\n(?<body>.*?)(?=^  build-release:)')
Assert-True ($f401Job.Success) `
    'release workflow has no direct F401 GCC matrix job'
Assert-True ($f401Job.Groups['body'].Value -notmatch
    '(?m)^\s+needs:') `
    'direct F401 GCC matrix is hidden when an unrelated host job fails'
Assert-True (-not (Test-Path -LiteralPath (
    Join-Path $root 'tools/.mk61-firmware/build-f401-native.ps1'))) `
    'obsolete Arduino-CLI F401 worker is still present'

[Console]::WriteLine('gcc_build_tests: ok')
