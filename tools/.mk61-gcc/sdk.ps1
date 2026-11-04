# Shared native SDK/toolchain discovery. No installed board package is queried.
function Get-NativeFileSha256 {
    param([string]$Path)
    # Arduino can start Windows PowerShell with a different PSModulePath.
    # Hashing must not depend on the optional Get-FileHash module function.
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [IO.File]::OpenRead($Path)
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $algorithm.Dispose()
    }
}

function Get-NativeSdkPath {
    param([string]$ProjectRoot, [string]$Explicit)
    $selected = if (-not [string]::IsNullOrWhiteSpace($Explicit)) { $Explicit
    } elseif (-not [string]::IsNullOrWhiteSpace($env:MK61_GCC_SDK)) { $env:MK61_GCC_SDK
    } else { Join-Path $ProjectRoot 'third_party/stm32f4' }
    $selected = [IO.Path]::GetFullPath($selected)
    $manifest = Join-Path $selected 'manifest.json'
    if (-not [IO.File]::Exists($manifest)) { throw "Native SDK manifest is missing: $manifest" }
    $data = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($manifest))
    if ($data.schema -ne 1 -or @($data.files.PSObject.Properties).Count -lt 10) {
        throw 'Unsupported or incomplete native SDK manifest'
    }
    foreach ($entry in $data.files.PSObject.Properties) {
        $name = [string]$entry.Name
        if ($name -match '(^/|(^|/)\.\.(/|$)|\\|:)' ) { throw "Invalid native SDK file path: $name" }
        $path = Join-Path $selected $name
        if (-not [IO.File]::Exists($path)) { throw "Native SDK file is missing: $name" }
        if ((Get-NativeFileSha256 $path) -ne [string]$entry.Value) {
            throw "Native SDK checksum mismatch: $name"
        }
    }
    return $selected
}
# GCC itself accepts Unicode sources, but the pinned Windows gcc-ar cannot
# locate its LTO plugin when its own installation path contains Unicode.
function Get-NativeGnuArmInstallRoot {
    param([string]$Requested)
    $requestedPath = [IO.Path]::GetFullPath($Requested)
    if ($env:OS -ne 'Windows_NT' -or $requestedPath -notmatch '[^\x20-\x7e]') { return $requestedPath }
    $public = [Environment]::GetEnvironmentVariable('PUBLIC')
    $documents = if ([string]::IsNullOrWhiteSpace($public)) {
        [Environment]::GetFolderPath('CommonDocuments')
    } else { Join-Path $public 'Documents' }
    if ([string]::IsNullOrWhiteSpace($documents) -or $documents -match '[^\x20-\x7e]') {
        throw 'GNU Arm requires an ASCII-only installation path on Windows; pass an ASCII -InstallRoot or -ToolchainDirectory.'
    }
    # Keep independent sketchbooks/projects isolated, with a stable real path.
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($hasher.ComputeHash(
        [Text.Encoding]::UTF8.GetBytes($requestedPath.ToLowerInvariant()))).Replace('-', '').Substring(0, 12).ToLowerInvariant()
    } finally { $hasher.Dispose() }
    return Join-Path $documents "MK61Arduino/toolchains-$hash"
}

function Get-NativeGnuArmBin {
    param([string]$ProjectRoot, [string]$Version, [string]$Explicit)
    $selected = $Explicit
    if ([string]::IsNullOrWhiteSpace($selected)) { $selected = $env:MK61_GCC_TOOLCHAIN }
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    if ([string]::IsNullOrWhiteSpace($selected)) {
        $cacheRoot = Get-NativeGnuArmInstallRoot (Join-Path $ProjectRoot '.build/toolchains')
        $cached = Join-Path $cacheRoot "xpack-arm-none-eabi-gcc-$Version"
        if ([IO.Directory]::Exists($cached)) { $selected = $cached
        } else {
            $gcc = Get-Command "arm-none-eabi-gcc$suffix" -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -ne $gcc) { $selected = Split-Path -Parent $gcc.Source }
        }
    }
    if ([string]::IsNullOrWhiteSpace($selected)) {
        throw 'GNU Arm GCC is missing; run tools/install_gcc_dependencies.ps1, put arm-none-eabi-gcc on PATH or set MK61_GCC_TOOLCHAIN'
    }
    $selected = [IO.Path]::GetFullPath($selected)
    if ($env:OS -eq 'Windows_NT' -and $selected -match '[^\x20-\x7e]') {
        throw 'GNU Arm compiler must use an ASCII-only path on Windows (gcc-ar cannot find liblto_plugin.dll otherwise). Reinstall the MK61s board or select an ASCII -ToolchainDirectory.'
    }
    if (-not [IO.File]::Exists((Join-Path $selected "arm-none-eabi-gcc$suffix"))) {
        $selected = Join-Path $selected 'bin'
    }
    foreach ($name in @('gcc','g++','ar','ranlib','objcopy','size','nm','objdump','c++filt')) {
        $path = Join-Path $selected "arm-none-eabi-$name$suffix"
        if (-not [IO.File]::Exists($path)) { throw "GNU Arm tool not found: $path" }
    }
    return $selected
}

function Assert-NativeGnuArmVersion {
    param([string]$Bin, [string]$Version)
    $suffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
    $compiler = Join-Path $Bin "arm-none-eabi-gcc$suffix"
    $actual = & $compiler -dumpfullversion
    $expected = ($Version -split '-')[0]
    if ($LASTEXITCODE -ne 0 -or [string]$actual -ne $expected) {
        throw "GNU Arm GCC $expected is required; compiler returned: $actual"
    }
}
