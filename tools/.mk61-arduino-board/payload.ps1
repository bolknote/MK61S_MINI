function Get-Mk61NativePayloadPairs {
    param([string]$ProjectRoot, [string]$Target)
    . (Join-Path $ProjectRoot 'tools/.mk61-gcc/sdk.ps1')
    $sdk = Get-NativeSdkPath $ProjectRoot (Join-Path $ProjectRoot 'third_party/stm32f4')
    $metadata = ConvertFrom-Json ([IO.File]::ReadAllText(
        (Join-Path $ProjectRoot 'tools/.mk61-arduino-board/payload.json')))
    if ($metadata.schema -ne 1) { throw 'unsupported Arduino native payload schema' }
    $files = @{}
    foreach ($entry in $metadata.files.PSObject.Properties) {
        # This Unix sealer is never used by the Windows build/upload path.
        if ($env:OS -eq 'Windows_NT' -and $entry.Value -eq 'tools/seal-firmware-elf.py') { continue }
        $files[[string]$entry.Name] = [string]$entry.Value
    }
    $sdkManifest = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $sdk 'manifest.json')))
    foreach ($name in @('manifest.json') + @($sdkManifest.files.PSObject.Properties.Name)) {
        $files["third_party/stm32f4/$name"] = "system/stm32f4/$name"
    }
    foreach ($source in $files.Keys) {
        $destination = [string]$files[$source]
        foreach ($name in @($source, $destination)) {
            if ($name -match '(^/|(^|/)\.\.(/|$)|\\|:)') { throw "invalid native payload path: $name" }
        }
        [pscustomobject]@{ Source = Join-Path $ProjectRoot $source; Target = Join-Path $Target $destination }
    }
}

function Get-Mk61NativeCompiler {
    param([string]$ProjectRoot, [string]$Target, [string]$Explicit, [switch]$Install)
    . (Join-Path $ProjectRoot 'tools/.mk61-gcc/sdk.ps1')
    $version = (ConvertFrom-Json ([IO.File]::ReadAllText(
        (Join-Path $ProjectRoot 'tools/.mk61-gcc/toolchain-lock.json')))).version
    $selected = $Explicit
    if ($Install -and [string]::IsNullOrWhiteSpace($selected)) { $selected = $env:MK61_ARDUINO_TOOLCHAIN }
    if ($Install -and [string]::IsNullOrWhiteSpace($selected)) { $selected = $env:MK61_GCC_TOOLCHAIN }
    $local = Join-Path $Target 'platform.local.txt'
    if ([string]::IsNullOrWhiteSpace($selected) -and [IO.File]::Exists($local)) {
        foreach ($line in [IO.File]::ReadAllLines($local)) {
            if ($line -match '^compiler\.path=(.+)$') {
                if (-not $Install -or [IO.Directory]::Exists($Matches[1])) { $selected = $Matches[1] }
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($selected)) {
        $installRoot = Join-Path $Target 'tools/toolchains'
        $selected = Join-Path $installRoot "xpack-arm-none-eabi-gcc-$version"
        if (-not [IO.Directory]::Exists($selected)) {
            if (-not $Install) { throw 'native GNU Arm compiler is missing; reinstall the MK61s board' }
            $powerShell = (Get-Process -Id $PID).Path
            & $powerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $ProjectRoot 'tools/install_gcc_dependencies.ps1') -InstallRoot $installRoot
            if ($LASTEXITCODE -ne 0) { throw "GNU Arm installation failed ($LASTEXITCODE)" }
        }
    }
    $binary = Get-NativeGnuArmBin $ProjectRoot $version $selected
    Assert-NativeGnuArmVersion $binary $version
    return $binary
}

function Install-Mk61NativePayload {
    param([string]$ProjectRoot, [string]$Target, [string]$ToolchainDirectory)
    foreach ($pair in Get-Mk61NativePayloadPairs $ProjectRoot $Target) {
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($pair.Target)) | Out-Null
        Copy-Item -LiteralPath $pair.Source -Destination $pair.Target -Force
    }
    $binary = Get-Mk61NativeCompiler $ProjectRoot $Target $ToolchainDirectory -Install
    $local = Join-Path $Target 'platform.local.txt'
    $lines = @()
    if ([IO.File]::Exists($local)) {
        $lines = @([IO.File]::ReadAllLines($local) | Where-Object { $_ -notmatch '^compiler\.path=' })
    }
    $lines += 'compiler.path=' + $binary.Replace('\', '/') + '/'
    [IO.File]::WriteAllLines($local, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
    foreach ($name in @('library.properties', 'src/USBDevice.h', 'src/USBDevice.cpp')) {
        $old = Join-Path $Target "libraries/USBDevice/$name"
        if ([IO.File]::Exists($old)) { Remove-Item -LiteralPath $old -Force }
    }
    $oldPython = Join-Path $Target 'tools/seal-firmware-elf.py'
    if ($env:OS -eq 'Windows_NT' -and [IO.File]::Exists($oldPython)) { Remove-Item -LiteralPath $oldPython -Force }
    Write-Host "Native GNU Arm: $binary"
}

function Test-Mk61NativePayload {
    param([string]$ProjectRoot, [string]$Target)
    try {
        if ($env:OS -eq 'Windows_NT' -and [IO.File]::Exists((Join-Path $Target 'tools/seal-firmware-elf.py'))) { return $false }
        foreach ($pair in Get-Mk61NativePayloadPairs $ProjectRoot $Target) {
            if (-not [IO.File]::Exists($pair.Target) -or
                (Get-FileHash -Algorithm SHA256 -LiteralPath $pair.Source).Hash -ne
                (Get-FileHash -Algorithm SHA256 -LiteralPath $pair.Target).Hash) { return $false }
        }
        $null = Get-Mk61NativeCompiler $ProjectRoot $Target ''
        return $true
    } catch {
        Write-Host $_.Exception.Message
        return $false
    }
}
