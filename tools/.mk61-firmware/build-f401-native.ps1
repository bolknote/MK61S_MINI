#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArduinoCli,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$BuildRoot,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [Parameter(Mandatory = $true)][string]$Profile,
    [Parameter(Mandatory = $true)][string]$Platform,
    [Parameter(Mandatory = $true)][string]$Display,
    [Parameter(Mandatory = $true)][string]$Bundle,
    [Parameter(Mandatory = $true)][string]$CompileFlags,
    [Parameter(Mandatory = $true)][ValidateSet('0', '1')][string]$Focal,
    [Parameter(Mandatory = $true)][ValidateSet('0', '1')][string]$Basic,
    [Parameter(Mandatory = $true)][ValidateSet('0', '1')][string]$Wbmp,
    [Parameter(Mandatory = $true)][ValidateSet('0', '1')][string]$Chip8
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:Fqbn = 'STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'
$script:Utf8NoBom = New-Object Text.UTF8Encoding($false)

function Stop-NativeBuild {
    param([Parameter(Mandatory = $true)][string]$Message)
    throw "MK61s native F401 build: $Message"
}

function Test-RequiredFile {
    param([string]$Path, [string]$Description)
    if ([string]::IsNullOrWhiteSpace($Path) -or
        -not [IO.File]::Exists($Path)) {
        Stop-NativeBuild "$Description not found: $Path"
    }
}

function Invoke-NativeTool {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Path @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-NativeBuild "$([IO.Path]::GetFileName($Path)) failed with exit code $LASTEXITCODE"
    }
}

function Get-CurrentPowerShell {
    if ($PSVersionTable.PSEdition -eq 'Desktop') {
        $candidate = Join-Path $PSHOME 'powershell.exe'
        Test-RequiredFile $candidate 'Windows PowerShell'
        return $candidate
    }
    $candidate = (Get-Process -Id $PID).Path
    Test-RequiredFile $candidate 'PowerShell'
    return $candidate
}

function Get-PowerShellScriptArguments {
    param(
        [Parameter(Mandatory = $true)][string]$Script,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $result = New-Object 'System.Collections.Generic.List[string]'
    $result.Add('-NoLogo')
    $result.Add('-NoProfile')
    if ($env:OS -eq 'Windows_NT') {
        $result.Add('-ExecutionPolicy')
        $result.Add('Bypass')
    }
    $result.Add('-File')
    $result.Add($Script)
    foreach ($argument in $Arguments) {
        $result.Add($argument)
    }
    return $result.ToArray()
}

function Remove-GeneratedBundleFiles {
    param([string]$Directory, [string]$ResidentName)
    foreach ($name in @(
        $ResidentName,
        'build.flags',
        'build.apps'
    )) {
        $path = Join-Path $Directory $name
        if ([IO.File]::Exists($path)) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    $system = Join-Path $Directory 'System'
    foreach ($name in @('FOCAL.APP', 'BASIC.APP', 'WBMP.APP', 'CHIP8.APP')) {
        $path = Join-Path $system $name
        if ([IO.File]::Exists($path)) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    if ([IO.Directory]::Exists($system) -and
        (Get-ChildItem -LiteralPath $system -Force).Count -eq 0) {
        Remove-Item -LiteralPath $system
    }
    $apps = Join-Path $Directory 'Apps'
    if ([IO.Directory]::Exists($apps)) {
        Remove-Item -LiteralPath $apps -Recurse -Force
    }
}

try {
    $ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
    $BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
    $OutputDir = [IO.Path]::GetFullPath($OutputDir)
    $fileSystemRoot = [IO.Path]::GetPathRoot($BuildRoot)
    if ($BuildRoot.TrimEnd(
            [IO.Path]::DirectorySeparatorChar,
            [IO.Path]::AltDirectorySeparatorChar
        ).Equals(
            $fileSystemRoot.TrimEnd(
                [IO.Path]::DirectorySeparatorChar,
                [IO.Path]::AltDirectorySeparatorChar),
            [StringComparison]::OrdinalIgnoreCase) -or
        $BuildRoot.Equals(
            $ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-NativeBuild "unsafe build root: $BuildRoot"
    }
    $code = Join-Path $ProjectRoot 'code'
    $systemAppsRoot = Join-Path $ProjectRoot 'system_apps'
    $systemAppsTool = Join-Path (
        Join-Path $systemAppsRoot '.tool') 'build.ps1'
    $systemAppsRequested = (
        $Focal -eq '1' -or $Basic -eq '1' -or $Wbmp -eq '1' -or
        $Chip8 -eq '1')
    Test-RequiredFile (Join-Path $code 'mk61s-M.ino') 'resident sketch'
    if ($systemAppsRequested) {
        Test-RequiredFile $systemAppsTool 'standalone System APP builder'
    }

    $sketchRoot = Join-Path $BuildRoot 'sketch'
    $sketch = Join-Path $sketchRoot 'mk61s-M'
    $residentBuild = Join-Path $BuildRoot 'resident'
    $stageRoot = Join-Path $BuildRoot 'bundle'
    foreach ($generated in @($sketchRoot, $residentBuild, $stageRoot)) {
        if ([IO.Directory]::Exists($generated)) {
            Remove-Item -LiteralPath $generated -Recurse -Force
        }
    }
    [IO.Directory]::CreateDirectory($sketch) | Out-Null
    [IO.Directory]::CreateDirectory($residentBuild) | Out-Null
    Copy-Item -Path (Join-Path $code '*') -Destination $sketch `
        -Recurse -Force

    Invoke-NativeTool $ArduinoCli @(
        'compile',
        '--fqbn', $script:Fqbn,
        '--build-path', $residentBuild,
        '--build-property', "compiler.cpp.extra_flags=$CompileFlags",
        $sketch
    )

    $projectName = 'mk61s-M.ino'
    $residentElf = Join-Path $residentBuild "$projectName.elf"
    $residentBin = Join-Path $residentBuild "$projectName.bin"
    $compileDatabase = Join-Path $residentBuild 'compile_commands.json'
    Test-RequiredFile $residentElf 'resident ELF'
    Test-RequiredFile $residentBin 'resident BIN'
    if ($systemAppsRequested) {
        Test-RequiredFile $compileDatabase 'Arduino compile database'
    }
    $powerShell = Get-CurrentPowerShell

    $temporaryBundle = Join-Path $stageRoot $Bundle
    [IO.Directory]::CreateDirectory($temporaryBundle) | Out-Null
    Copy-Item -LiteralPath $residentBin `
        -Destination (Join-Path $temporaryBundle "$Bundle.bin")
    [IO.File]::WriteAllText(
        (Join-Path $temporaryBundle 'build.flags'),
        $CompileFlags + [Environment]::NewLine,
        $script:Utf8NoBom)
    [IO.File]::WriteAllText(
        (Join-Path $temporaryBundle 'build.apps'),
        'format 1' + [Environment]::NewLine,
        $script:Utf8NoBom)

    if ($systemAppsRequested) {
        $system = Join-Path $temporaryBundle 'System'
        Invoke-NativeTool $powerShell (
            Get-PowerShellScriptArguments $systemAppsTool @(
                '-BuildPath', $residentBuild,
                '-ResidentElf', $residentElf,
                '-ResidentBin', $residentBin,
                '-CompileCommands', $compileDatabase,
                '-OutputDirectory', $system,
                '-Focal', $Focal,
                '-Basic', $Basic,
                '-Wbmp', $Wbmp,
                '-Chip8', $Chip8
            ))
    }

    [IO.Directory]::CreateDirectory($OutputDir) | Out-Null
    $outputBundle = Join-Path $OutputDir $Bundle
    [IO.Directory]::CreateDirectory($outputBundle) | Out-Null
    Remove-GeneratedBundleFiles $outputBundle "$Bundle.bin"
    Copy-Item -Path (Join-Path $temporaryBundle '*') `
        -Destination $outputBundle -Recurse -Force

    [Console]::WriteLine("Built native F401 bundle: $outputBundle")
    [Console]::WriteLine("Profile: $Profile ($Platform + $Display)")
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
