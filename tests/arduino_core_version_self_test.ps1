#requires -Version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$hook = Join-Path $root 'tools/arduino/hardware/mk61/stm32/tools/mk61-app-postbuild.ps1'
$powerShell = (Get-Process -Id $PID).Path
$work = Join-Path ([IO.Path]::GetTempPath()) ('mk61 core check ' + [Guid]::NewGuid().ToString('N'))
$core = Join-Path $work 'cores/arduino'
[IO.Directory]::CreateDirectory($core) | Out-Null
try {
    foreach ($version in @('2.12.0', '3.0.0', '2.11.0', '')) {
        [IO.File]::WriteAllText((Join-Path $work 'platform.txt'), "version=$version`r`n")
        $previousAction = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $output = & $powerShell -NoLogo -NoProfile -File $hook check-profile `
            -Platform classic-v2 -Display uc1609 -Sketch (Join-Path $root 'code') `
            -CorePath $core 2>&1
        $status = $LASTEXITCODE
        $ErrorActionPreference = $previousAction
        if ($status -ne 0) {
            throw "Core version '$version' caused an unsupported prebuild rejection: $output"
        }
    }
    Remove-Item -LiteralPath (Join-Path $work 'platform.txt')
    $ErrorActionPreference = 'Continue'
    $output = & $powerShell -NoLogo -NoProfile -File $hook check-profile `
        -Platform classic-v2 -Display uc1609 -Sketch (Join-Path $root 'code') `
        -CorePath $core 2>&1
    $status = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($status -ne 0) {
        throw "Legacy CorePath metadata caused a prebuild rejection: $output"
    }
    Write-Host 'arduino_core_version_self_test: OK'
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force
}
