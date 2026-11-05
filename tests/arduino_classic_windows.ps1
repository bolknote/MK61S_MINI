#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Prepare', 'Build', 'Verify', 'Upload')][string]$Phase,
    [Parameter(Mandatory = $true)][string]$WorkRoot,
    [string]$TestPython
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSEdition -ne 'Desktop') {
    throw 'This regression runs on stock Windows PowerShell 5.1'
}
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tools/firmware/stm32/sdk.ps1')
$fixturePath = Join-Path $PSScriptRoot 'fixtures/arduino_classic_windows.json'
$case = ConvertFrom-Json ([IO.File]::ReadAllText($fixturePath))
if ($case.schema -ne 1) { throw 'Unsupported Classic Windows case schema' }
$WorkRoot = [IO.Path]::GetFullPath($WorkRoot)
$caseProfile = Join-Path $WorkRoot 'profile'
$data = Join-Path $caseProfile 'AppData/Local/Arduino15'
$book = Join-Path $caseProfile 'Documents/Arduino'
$build = Join-Path $caseProfile 'AppData/Local/arduino/sketches/classic-v2-f401'
$config = Join-Path $caseProfile '.arduinoIDE/arduino-cli.yaml'
$ide = Join-Path $WorkRoot 'Arduino IDE'
$cli = Join-Path $ide $case.cli_relative_path
$tools = Join-Path $book 'hardware/mk61/stm32/tools'
$published = Join-Path $root ".build/firmware/$($case.bundle)"
foreach ($path in @($root, $caseProfile, $data, $book, $build, $config, $ide)) {
    if ($path -match '[^\x20-\x7e]') { throw "This case requires ASCII paths: $path" }
}
[void][IO.Directory]::CreateDirectory((Join-Path $caseProfile 'AppData/Local/Temp'))
$env:TEMP = Join-Path $caseProfile 'AppData/Local/Temp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:MK61_ARDUINO_CONFIG_FILE = $config
$env:ARDUINO_DIRECTORIES_DATA = $data
$env:ARDUINO_DIRECTORIES_USER = $book
$providedToolchain = $env:MK61_GCC_TOOLCHAIN
$env:MK61_GCC_TOOLCHAIN = ''
$env:MK61_ARDUINO_TOOLCHAIN = ''

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    # Windows PowerShell also wraps native stderr warnings in ErrorRecords.
    # Preserve them and decide success from the actual process exit code.
    $ErrorActionPreference = 'Continue'
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed ($LASTEXITCODE)" }
}

if ($Phase -eq 'Prepare') {
    $archive = Join-Path $WorkRoot 'arduino-ide-windows.zip'
    if (-not [IO.File]::Exists($archive)) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Write-Host "Downloading official Arduino IDE $($case.ide_version) Windows ZIP"
        Invoke-WebRequest -UseBasicParsing -Uri $case.ide_url -OutFile $archive
    }
    if ((Get-NativeFileSha256 $archive) -cne $case.ide_sha256) {
        throw 'Arduino IDE ZIP checksum mismatch'
    }
    if (-not [IO.File]::Exists($cli)) {
        # Exercise the exact bundled backend. Unrelated Electron node_modules
        # need not be unpacked into Windows PowerShell's MAX_PATH-limited ZIP
        # extractor, and the GUI is not part of this gRPC test.
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            foreach ($name in @($case.cli_relative_path, 'resources/app/package.json')) {
                $entry = $zip.GetEntry($name)
                if ($null -eq $entry) { throw "IDE ZIP omits $name" }
                $destination = Join-Path $ide $name
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $destination))
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $true)
            }
        } finally { $zip.Dispose() }
    }
    $package = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $ide 'resources/app/package.json')))
    if ($package.version -cne $case.ide_version) { throw 'Wrong Arduino IDE package version' }
    $version = (& $cli version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch ('Version:\s+' + [regex]::Escape($case.cli_version) + '\b')) {
        throw "Wrong bundled Arduino CLI: $version"
    }
    [void][IO.Directory]::CreateDirectory((Split-Path -Parent $config))
    [void][IO.Directory]::CreateDirectory($data)
    [IO.File]::WriteAllLines($config, [string[]]@(
        'directories:',
        "  data: '$($data.Replace('\', '/'))'",
        "  user: '$($book.Replace('\', '/'))'",
        'build_cache:',
        "  path: '$((Split-Path -Parent $build).Replace('\', '/'))'"
    ), (New-Object Text.UTF8Encoding($false)))
    Invoke-Checked $cli @('--config-file', $config, 'core', 'update-index')
    $lock = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $root 'tools/firmware/stm32/toolchain-lock.json')))
    $compiler = Get-NativeGnuArmBin $root $lock.version $providedToolchain
    Assert-NativeGnuArmVersion $compiler $lock.version
    # Model the reporter's existing Arduino15 compiler, without installing a
    # vendor Core. The board must discover this path without an override and
    # must not download/create its own duplicate toolchain.
    $arduinoCompiler = Join-Path $data "packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/$($lock.version)"
    & robocopy.exe (Split-Path -Parent $compiler) $arduinoCompiler /E /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { throw "Cannot stage existing Arduino compiler ($LASTEXITCODE)" }
    $env:ARDUINO_DIRECTORIES_DATA = '' # Discovery must read directories.data from the IDE YAML.
    $powerShell = (Get-Process -Id $PID).Path
    Invoke-Checked $powerShell @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'tools/arduino/install.ps1'))
    $registration = [IO.File]::ReadAllText((Join-Path $book 'hardware/mk61/stm32/platform.local.txt'))
    if (-not $registration.Contains('compiler.path=' + $arduinoCompiler.Replace('\', '/') + '/bin/')) {
        throw 'Board installation did not discover the existing Arduino15 compiler'
    }
    if ([IO.Directory]::Exists((Join-Path $tools 'toolchains'))) {
        throw 'Board installation downloaded a duplicate compiler despite the compatible Arduino15 compiler'
    }
    Invoke-Checked $powerShell @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'tools/arduino/install.ps1'), '-Check')
    Copy-Item -LiteralPath $fixturePath -Destination (Join-Path $WorkRoot 'case.json')
    Write-Host "Reporter case ready: IDE $($case.ide_version), $version, $($case.fqbn)"
    return
}
if (-not [IO.File]::Exists($cli)) { throw 'Run the Prepare phase first' }
if ([IO.Directory]::Exists((Join-Path $data 'packages/STMicroelectronics/hardware'))) {
    throw 'The native IDE regression unexpectedly installed STM32 Core'
}
if ($Phase -in @('Build', 'Verify') -and -not [IO.File]::Exists($TestPython)) {
    throw 'The explicit integration-test Python client was not found'
}
if ($Phase -eq 'Build') {
    $trap = Join-Path $WorkRoot 'blocked-python'
    [void][IO.Directory]::CreateDirectory($trap)
    foreach ($name in @('python.exe', 'python3.exe', 'py.exe')) {
        Copy-Item "$env:WINDIR/System32/where.exe" (Join-Path $trap $name) -Force
    }
    $env:PATH = "$trap;$env:PATH"
    $env:MK61_HOST_CXX = Join-Path $WorkRoot 'missing-host-cxx.exe'
    if ([IO.File]::Exists($env:MK61_HOST_CXX)) { throw 'Host compiler sentinel exists' }
    Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'arduino_daemon_compile.py'),
        '--cli', $cli, '--config-file', $config, '--sketch', (Join-Path $root 'code'),
        '--build-path', $build, '--fqbn', $case.fqbn)
    return
}
if ($Phase -eq 'Upload') {
    # The existing harness pins its own fake CubeProgrammer and serial adapter;
    # it never discovers a connected device. Use this IDE's bundled CLI too.
    $env:PATH = "$(Split-Path -Parent $cli);$env:PATH"
    Invoke-Checked (Get-Process -Id $PID).Path @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', (Join-Path $PSScriptRoot 'arduino_windows_e2e.ps1'),
        '-BuildPath', $build, '-Fqbn', $case.fqbn, '-ConfigFile', $config,
        '-PlatformToolsDirectory', $tools, '-PublishedSystem', (Join-Path $published 'System'))
    return
}

. (Join-Path $tools 'mk61-system-bundle.ps1')
# Artifact analysis emits Unicode paths even though this particular case uses
# ASCII. Keep these test tools' diagnostics consistent with their UTF-8 input.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$stage = Join-Path $build "mk61-system-apps/$($case.bundle)"
$manifest = Get-VerifiedMk61SystemManifest $stage $case.bundle f401 (Join-Path $build 'code.ino.bin')
if ($manifest.profile -cne $case.profile -or $manifest.profile_id -cne $case.profile_id) {
    throw 'The compiled identity differs from the reported Classic V2 profile'
}
$flags = [IO.File]::ReadAllText((Join-Path $published 'build.flags')) -split '\s+'
foreach ($definition in $case.definitions) {
    if ($definition -cnotin $flags) { throw "Reporter setting was not compiled: $definition" }
}
foreach ($name in $case.required_system_files) {
    if (-not [IO.File]::Exists((Join-Path $stage "System/$name"))) { throw "Missing selected System/$name" }
}
foreach ($name in $case.disabled_system_files) {
    if ([IO.File]::Exists((Join-Path $stage "System/$name"))) { throw "Disabled System/$name was built" }
}
$registered = @([IO.File]::ReadAllLines((Join-Path $book 'hardware/mk61/stm32/platform.local.txt')) |
    Where-Object { $_.StartsWith('compiler.path=') })
if ($registered.Count -ne 1) { throw 'Expected exactly one native compiler registration' }
$compiler = Get-NativeGnuArmBin $root '' $registered[0].Substring('compiler.path='.Length)
$env:ARM_NONE_EABI_NM = Join-Path $compiler 'arm-none-eabi-nm.exe'
$elf = Join-Path $build 'code.ino.elf'
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'check_standalone_sdk_build.py'), '--arduino', (Join-Path $build 'compile_commands.json'))
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'check_native_runtime_libraries.py'), '--without-libc', (Join-Path $build 'code.ino.map'))
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'check_usb_cdc_rx_elf.py'), $elf, '--objdump', (Join-Path $compiler 'arm-none-eabi-objdump.exe'))
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'check_narrow_stm32_drivers_elf.py'), '--native-panel', $elf)
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'check_app_memory_elf.py'), '--system-dir', (Join-Path $stage 'System'), $elf)
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'stm32f4_cdc_arm_self_test.py'), $elf)
Invoke-Checked $TestPython @((Join-Path $PSScriptRoot 'stm32f4_usb_arm_self_test.py'), $elf)
Write-Host 'Reported Classic V2 F401 configuration: exact options, System identity, full APP capacity and production USB ARM models PASS'
