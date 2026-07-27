#requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [string]$InstallDirectory = '',

    [string]$GitHubPath = $env:GITHUB_PATH
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$archives = @{
    'Linux/X64'   = 'Linux_64bit.tar.gz'
    'Linux/ARM64' = 'Linux_ARM64.tar.gz'
    'macOS/X64'   = 'macOS_64bit.tar.gz'
    'macOS/ARM64' = 'macOS_ARM64.tar.gz'
    'Windows/X64' = 'Windows_64bit.zip'
}

$checksums = @{
    '1.5.1' = @{
        'arduino-cli_1.5.1_Linux_64bit.tar.gz' = `
            '28a8e119c498a25607821c36cb2dc49e8463941b261a0d99091baa7bc692dd2b'
        'arduino-cli_1.5.1_Linux_ARM64.tar.gz' = `
            '1e69e077479f300614d4551334e0a33f08ee40b04315d83b8e7e0e94f0d0ee62'
        'arduino-cli_1.5.1_macOS_64bit.tar.gz' = `
            'c982e940027996bea9901050e95fae99c59c1dcfee54beedecaf28141e7bf2e7'
        'arduino-cli_1.5.1_macOS_ARM64.tar.gz' = `
            'cb952e8c1621c95ef5f1d17831c945e3d0ec5973f89c557a7ec8feb9c4f7d4c9'
        'arduino-cli_1.5.1_Windows_64bit.zip' = `
            'fabe42e0eb04d00e776a66178299ff95a46c623dbc260f997e58fd514853dd40'
    }
}

if ([string]::IsNullOrWhiteSpace($env:RUNNER_OS) -or
    [string]::IsNullOrWhiteSpace($env:RUNNER_ARCH)) {
    throw 'RUNNER_OS and RUNNER_ARCH must identify the GitHub Actions runner.'
}

$platform = "$($env:RUNNER_OS)/$($env:RUNNER_ARCH)"
if (-not $archives.ContainsKey($platform)) {
    throw "Arduino CLI is not pinned for runner platform $platform."
}
if (-not $checksums.ContainsKey($Version)) {
    throw "Arduino CLI $Version has no pinned checksums."
}

$archiveName = "arduino-cli_${Version}_$($archives[$platform])"
$versionChecksums = $checksums[$Version]
if (-not $versionChecksums.ContainsKey($archiveName)) {
    throw "Arduino CLI $Version has no pinned checksum for $platform."
}

$runnerTemp = $env:RUNNER_TEMP
if ([string]::IsNullOrWhiteSpace($runnerTemp)) {
    $runnerTemp = [IO.Path]::GetTempPath()
}
if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $runnerTemp `
        "arduino-cli-$Version-$($env:RUNNER_OS)-$($env:RUNNER_ARCH)"
}
if ([string]::IsNullOrWhiteSpace($GitHubPath)) {
    throw 'GITHUB_PATH must be set so Arduino CLI is available to later steps.'
}

$downloadDirectory = Join-Path $runnerTemp `
    "arduino-cli-download-$PID-$([guid]::NewGuid().ToString('N'))"
$archivePath = Join-Path $downloadDirectory $archiveName
$downloadUrl = (
    "https://github.com/arduino/arduino-cli/releases/download/" +
    "v$Version/$archiveName"
)

New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
try {
    Write-Host "Downloading Arduino CLI $Version for $platform"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath

    $actualChecksum = (
        Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    $expectedChecksum = $versionChecksums[$archiveName]
    if ($actualChecksum -ne $expectedChecksum) {
        throw (
            "Checksum mismatch for ${archiveName}: " +
            "expected $expectedChecksum, got $actualChecksum"
        )
    }

    if (Test-Path -LiteralPath $InstallDirectory) {
        $existingFiles = @(Get-ChildItem -LiteralPath $InstallDirectory -Force)
        if ($existingFiles.Count -ne 0) {
            throw "Arduino CLI install directory is not empty: $InstallDirectory"
        }
    } else {
        New-Item -ItemType Directory -Path $InstallDirectory | Out-Null
    }

    if ($archiveName.EndsWith('.zip')) {
        Expand-Archive -LiteralPath $archivePath `
            -DestinationPath $InstallDirectory
    } else {
        & tar -xzf $archivePath -C $InstallDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to extract $archiveName."
        }
    }

    $executableName = if ($env:RUNNER_OS -eq 'Windows') {
        'arduino-cli.exe'
    } else {
        'arduino-cli'
    }
    $executable = Join-Path $InstallDirectory $executableName
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
        throw "Arduino CLI executable is missing after extraction: $executable"
    }

    if ($env:RUNNER_OS -ne 'Windows') {
        & chmod +x $executable
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to make Arduino CLI executable: $executable"
        }
    }

    Add-Content -LiteralPath $GitHubPath -Value $InstallDirectory `
        -Encoding utf8
    & $executable version
    if ($LASTEXITCODE -ne 0) {
        throw 'Installed Arduino CLI failed its version check.'
    }
} finally {
    if (Test-Path -LiteralPath $downloadDirectory) {
        Remove-Item -LiteralPath $downloadDirectory -Recurse -Force
    }
}
