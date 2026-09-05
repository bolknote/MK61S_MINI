#requires -Version 5.1

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $root 'tools/build-gcc.cmd'
$backend = Join-Path $root 'tools/.mk61-gcc/build.ps1'
$cmakeProject = Join-Path $root 'tools/.mk61-gcc/CMakeLists.txt'
$ramCheck = Join-Path $root 'tools/.mk61-gcc/check-ram.cmake'
$flashCheck = Join-Path $root 'tools/.mk61-gcc/check-flash.cmake'
$toolchain = Join-Path $root 'tools/.mk61-gcc/arm-none-eabi.cmake'
$systemAppExports = Join-Path $root `
    'tools/.mk61-gcc/system-app-exports.list'
$firmwareMain = Join-Path $root 'tools/.mk61-gcc/firmware_main.cpp.in'
$firmwarePowerShell = Join-Path $root `
    'tools/.mk61-firmware/mk61-firmware.ps1'
$firmwareShell = Join-Path $root `
    'tools/.mk61-firmware/mk61-firmware.sh'
$releaseWorkflow = Join-Path $root `
    '.github/workflows/firmware-release.yml'
$releaseManifest = Join-Path $root 'tools/release-contract.json'
$releaseContract = Join-Path $root 'tools/release_contract.py'
$f401ReleaseMatrix = Join-Path $root 'tests/run_f401_release_matrix.sh'
$arduinoSetupAction = Join-Path $root `
    '.github/actions/setup-arduino-cli/action.yml'
$arduinoSetupScript = Join-Path $root `
    '.github/actions/setup-arduino-cli/install.ps1'
$dependencyInstaller = Join-Path $root 'tools/install_arduino_dependencies.ps1'
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
    $ramCheck,
    $flashCheck,
    $toolchain,
    $systemAppExports,
    $firmwareMain,
    $firmwarePowerShell,
    $firmwareShell,
    $releaseWorkflow,
    $releaseManifest,
    $releaseContract,
    $f401ReleaseMatrix,
    $arduinoSetupAction,
    $arduinoSetupScript,
    $dependencyInstaller
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
Assert-True ($helpText -match 'tools/release-contract\.json') `
    'help does not identify the canonical profile source'
Assert-True ($helpText -match '-Check\s+validate dependencies') `
    'help does not expose dependency preflight'
Assert-True ($helpText -match '-Markdown 0\|1\s+default 1') `
    'help does not expose the Markdown System APP'
Assert-True ($helpText -match '-Lto 0\|1\s+default 1') `
    'help does not enable LTO by default'
Assert-True ($helpText -match '-Ws0010Graphics 0\|1') `
    'help does not expose isolated WS0010 graphics qualification'

$invalid = Invoke-Backend @(
    '-Profile', 'mini-v3-a00',
    '-Wbmp', '1',
    '-Markdown', '0',
    '-UsbScreen', '0')
Assert-True ($invalid.ExitCode -eq 1) `
    'LCD1602 profile accepted a graphics APP without USB Screen'
Assert-True (($invalid.Output -join "`n") -match
    'WBMP requires UC1609') `
    'invalid graphics selection has no useful diagnostic'

$invalidWsGraphics = Invoke-Backend @(
    '-Profile', 'mini-v3-a00',
    '-Ws0010Graphics', '1')
Assert-True ($invalidWsGraphics.ExitCode -eq 1) `
    'non-WS0010 profile accepted WS0010 graphics qualification'
Assert-True (($invalidWsGraphics.Output -join "`n") -match
    'requires profile mini-v3-ws0010') `
    'invalid WS0010 graphics selection has no useful diagnostic'

$backendText = [IO.File]::ReadAllText($backend)
$cmakeText = [IO.File]::ReadAllText($cmakeProject)
$ramCheckText = [IO.File]::ReadAllText($ramCheck)
$toolchainText = [IO.File]::ReadAllText($toolchain)
$systemAppExportsText = [IO.File]::ReadAllText($systemAppExports)
$firmwareMainText = [IO.File]::ReadAllText($firmwareMain)
$firmwarePowerShellText = [IO.File]::ReadAllText($firmwarePowerShell)
$firmwareShellText = [IO.File]::ReadAllText($firmwareShell)
$releaseWorkflowText = [IO.File]::ReadAllText($releaseWorkflow)
$releaseManifestText = [IO.File]::ReadAllText($releaseManifest)
$f401ReleaseMatrixText = [IO.File]::ReadAllText($f401ReleaseMatrix)
$arduinoSetupActionText = [IO.File]::ReadAllText($arduinoSetupAction)
$arduinoSetupScriptText = [IO.File]::ReadAllText($arduinoSetupScript)
$dependencyInstallerText = [IO.File]::ReadAllText($dependencyInstaller)
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
Assert-True ($cmakeText -match
    'MK61_GLOBAL_RAM_LIMIT=\$\{MK61_GLOBAL_RAM_LIMIT\}') `
    'canonical F401 build does not consume its selected RAM budget'
Assert-True ($cmakeText -match
    'MK61_FLASH_MIN_HEADROOM=\$\{MK61_FLASH_MIN_HEADROOM\}') `
    'canonical F401 build does not consume its selected Flash budget'
Assert-True ($cmakeText -match '-P "\$\{CMAKE_CURRENT_SOURCE_DIR\}/check-flash\.cmake"') `
    'canonical F401 build does not invoke the shared Flash budget gate'
Assert-True ($cmakeText -match
    '(?s)elseif\(MK61_ENABLE_LTO\).*?target_link_options\(resident PRIVATE -ffunction-sections -fdata-sections\)') `
    'per-function/data GC must be limited to LTO without System APP imports'
Assert-True ($cmakeText -match 'HAL_UART_MODULE_ONLY') `
    'canonical F401 build still retains the unused hardware UART state'
Assert-True ($cmakeText -match 'USBD_CLASS_USER_STRING_DESC=0') `
    'canonical F401 build still retains the empty USB user-string buffer'
foreach ($section in @('_mk61_data', '_mk61_bss', '_mk61_noinit')) {
    Assert-True ($ramCheckText.Contains($section)) `
        "F401 RAM budget does not count $section"
}
Assert-True ($cmakeText -match 'MK61_ENABLE_MARKDOWN_VIEWER') `
    'CMake build does not forward the Markdown selection'
Assert-True ($cmakeText -match 'MK61_WS0010_GRAPHICS_100X16') `
    'CMake build does not forward WS0010 graphics qualification'
Assert-True ($cmakeText -match
    'overall_settings\(OPTIMIZATION s LTO\)') `
    'CMake build does not enable GNU Arm LTO'
Assert-True ($cmakeText -match
    '--export-dynamic-symbol-list=\$\{_mk61_system_app_exports\}') `
    'LTO build does not preserve the System APP ABI'
Assert-True ($systemAppExportsText -match
    '_ZN18language_workspace4dataENS_5OwnerE;') `
    'System APP LTO export list is incomplete'
Assert-True ($cmakeText -match
    'STM32 Arduino Core \$\{MK61_CORE_VERSION\} is required') `
    'CMake build does not consume the selected STM32 Core version'
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
    'tests/run_f401_release_matrix\.sh') `
    'release workflow does not use the repository-owned F401 matrix'
Assert-True ($releaseWorkflowText -match
    'mk61-firmware\.cmd[\s\S]+--mcu f401') `
    'platform matrix does not exercise the public F401 frontend'
Assert-True ($releaseWorkflowText -match
    'macos-latest[\s\S]+windows-latest') `
    'direct F401 GCC build is not checked on macOS and Windows'
foreach ($setting in @(
    'MK61_ENABLE_FOCAL=1',
    'MK61_ENABLE_TINYBASIC=1',
    'MK61_ENABLE_WBMP_VIEWER=0',
    'MK61_ENABLE_MARKDOWN_VIEWER=1',
    'MK61_ENABLE_CHIP8=1',
    'MK61_ENABLE_USB_SCREEN=1',
    'MK61_MATH_BACKEND=1',
    'System/FOCAL.APP',
    'System/BASIC.APP',
    'System/WBMP.APP',
    'System/MARKDOWN.APP',
    'System/CHIP8.APP'
)) {
    Assert-True ($releaseWorkflowText.Contains($setting)) `
        "cross-platform full F401 matrix is missing $setting"
}
Assert-True ($f401ReleaseMatrixText -match
    'release_contract\.py[\s\S]+cases --group "\$group" --format tsv') `
    'F401 release matrix does not enumerate the shared contract'
Assert-True ($f401ReleaseMatrixText -match '-ReleaseCase "\$case_id"') `
    'F401 GCC builds are not bound to their selected release case'
Assert-True ($releaseWorkflowText -match
    '(?s)run: tests/run_f401_release_matrix\.sh.+?' +
    'find \. -type f ! -name SHA256SUMS\.txt -print0.+?' +
    'xargs -0 sha256sum > SHA256SUMS\.txt') `
    'release checksums do not cover the packaged F401 ZIP and APP'
Assert-True ($f401ReleaseMatrixText -match
    '(?s)System/FOCAL\.APP.+?System/BASIC\.APP.+?System/MARKDOWN\.APP.+?' +
    'System/WBMP\.APP.+?System/CHIP8\.APP.+?' +
    'disabled APP was packaged') `
    'release workflow can publish an incomplete F401 ZIP'
Assert-True ($releaseWorkflowText -match
    '(?s)Verify resident and combined System APP.+?' +
    '\$container\[15\] -ne 1.+?' +
    'F401 APP is not packed with ZX0') `
    'cross-platform workflow does not reject raw System APP'
Assert-True ($f401ReleaseMatrixText -match
    "(?s)od -An -tu1 -j15 -N1.+?System APP is not ZX0") `
    'release packaging does not reject raw System APP'
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
Assert-True ($releaseWorkflowText -notmatch 'ARDUINO_CLI_VERSION') `
    'release workflow duplicates the Arduino CLI contract version'
Assert-True ($arduinoSetupActionText -match
    '(?m)^\s+using:\s+composite\s*$') `
    'local Arduino CLI setup is not a composite action'
Assert-True ($arduinoSetupActionText -match
    'release_contract\.py[\s\S]+toolchain --field arduino_cli') `
    'local Arduino CLI setup does not consume the release contract'
Assert-True ($arduinoSetupScriptText -match
    "'1\.5\.1'\s*=\s*@\{") `
    'local Arduino CLI setup does not pin the configured release'
Assert-True ($arduinoSetupScriptText -match
    'Get-FileHash[\s\S]+Algorithm SHA256') `
    'local Arduino CLI setup does not verify its downloaded archive'
Assert-True (([regex]::Matches(
    $releaseWorkflowText,
    'run:\s+tools/install_arduino_dependencies\.ps1')).Count -eq 2) `
    'release jobs do not share the repository-owned dependency installer'
Assert-True ($dependencyInstallerText -match
    'release-contract\.json[\s\S]+toolchain\.libraries') `
    'dependency installer has a second hard-coded library list'
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
