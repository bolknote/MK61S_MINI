#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot,
    [string]$ArchivePath,
    [switch]$Check,
    [switch]$Help
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($Help) {
    Write-Host 'Install pinned standalone GNU Arm GCC into .build/toolchains. No Arduino package is used.'
    Write-Host 'Options: -InstallRoot DIR, -ArchivePath FILE (offline, SHA256 checked), -Check, -Help'
    Write-Host 'CMake 3.21+, Ninja and PowerShell must be installed separately.'
    exit 0
}
try {
    . (Join-Path $PSScriptRoot '.mk61-gcc/sdk.ps1')
    $sdk = Get-NativeSdkPath $project ''
    $lock = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText(
        (Join-Path $PSScriptRoot '.mk61-gcc/toolchain-lock.json')))
    $contract = ConvertFrom-Json -InputObject ([IO.File]::ReadAllText(
        (Join-Path $PSScriptRoot 'release-contract.json')))
    if ($lock.schema -ne 1 -or $lock.version -ne $contract.toolchain.gnu_arm) {
        throw 'GNU Arm lock version does not match the release contract'
    }
    if ($Check) {
        $checkTarget = if ([string]::IsNullOrWhiteSpace($InstallRoot)) { ''
        } else { Join-Path $InstallRoot "xpack-arm-none-eabi-gcc-$($lock.version)" }
        $bin = Get-NativeGnuArmBin $project $lock.version $checkTarget
        Assert-NativeGnuArmVersion $bin $lock.version
        Write-Host "Native SDK: $sdk"
        Write-Host "GNU Arm: $bin"
        exit 0
    }
    if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
        $InstallRoot = Join-Path $project '.build/toolchains'
    }
    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    $platform = if ($env:OS -eq 'Windows_NT') { 'win32-x64' } else {
        $osName = if ([Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([Runtime.InteropServices.OSPlatform]::OSX)) { 'darwin' } else { 'linux' }
        $arch = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
        "$osName-$arch"
    }
    $property = $lock.assets.PSObject.Properties[$platform]
    if ($null -eq $property) { throw "Unsupported GNU Arm host platform: $platform" }
    $asset = $property.Value
    $folder = "xpack-arm-none-eabi-gcc-$($lock.version)"
    $target = Join-Path $InstallRoot $folder
    if ([IO.Directory]::Exists($target)) {
        $bin = Get-NativeGnuArmBin $project $lock.version $target
        Assert-NativeGnuArmVersion $bin $lock.version
        Write-Host "GNU Arm already installed: $bin"
        exit 0
    }
    [void][IO.Directory]::CreateDirectory($InstallRoot)
    $stage = Join-Path $InstallRoot ('.install-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($stage)
    try {
        if ([string]::IsNullOrWhiteSpace($ArchivePath)) {
            $archive = Join-Path $stage $asset.archive
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Write-Host "Downloading $($asset.archive)"
            Invoke-WebRequest -UseBasicParsing -Uri $asset.url -OutFile $archive
        } else { $archive = [IO.Path]::GetFullPath($ArchivePath) }
        $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $asset.sha256) { throw "GNU Arm archive checksum mismatch: $archive" }
        $unpack = Join-Path $stage 'unpack'
        [void][IO.Directory]::CreateDirectory($unpack)
        if ($asset.archive.EndsWith('.zip')) {
            Expand-Archive -LiteralPath $archive -DestinationPath $unpack
        } else {
            & tar -xzf $archive -C $unpack
            if ($LASTEXITCODE -ne 0) { throw 'GNU Arm archive extraction failed' }
        }
        $source = Join-Path $unpack $folder
        $bin = Get-NativeGnuArmBin $project $lock.version $source
        Assert-NativeGnuArmVersion $bin $lock.version
        $receipt = @{ version=$lock.version; platform=$platform; archive_sha256=$hash }
        [IO.File]::WriteAllText((Join-Path $source 'mk61-install.json'),
            (ConvertTo-Json $receipt), (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $source -Destination $target
        Write-Host "GNU Arm installed: $(Join-Path $target 'bin')"
        Write-Host "Native SDK: $sdk"
    } finally {
        if ([IO.Directory]::Exists($stage)) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
