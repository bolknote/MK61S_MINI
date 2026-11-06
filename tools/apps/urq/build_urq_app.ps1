#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Toolchain,
    [Parameter(Mandatory = $true)][string]$BuildDirectory,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [string]$LibraryOutput,
    [string]$LicensesOutput
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
. (Join-Path $root 'tools/firmware/stm32/sdk.ps1')
$utf8 = New-Object Text.UTF8Encoding($false)
$reports = @()
try {
    $powerShell = (Get-Process -Id $PID).Path
    foreach ($part in @(@('urq', 'URQ'), @('urq-ui', 'URQUI'))) {
        $name = $part[1]
        $directory = Join-Path $BuildDirectory $name
        & $powerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File `
            (Join-Path $root 'tools/apps/portable/build-portable-app.ps1') `
            -System $part[0] -ArmToolchainBin $Toolchain -OutputDirectory $directory
        if ($LASTEXITCODE -ne 0) { throw "$name build failed ($LASTEXITCODE)" }
        $report = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $directory "$name.json")))
        if ($report.memory_bytes -gt 20480) { throw "$name exceeds the 20 KiB APP arena" }
        $stack = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $directory 'stack-usage.json')))
        $report | Add-Member -NotePropertyName app_sha256 -NotePropertyValue `
            (Get-NativeFileSha256 (Join-Path $directory "$name.APP"))
        $report | Add-Member -NotePropertyName resources -NotePropertyValue ([ordered]@{
            workspace_limit = 8192; shell_limit = 1600; optional_history = 0
            page_cache_in_workspace = 512; expression_scratch_in_workspace = 1536
            maximum_frame = $stack.max_frame
        })
        $reports += $report
    }
    # Publish only when both APPs have passed compilation, stack and packing.
    [void][IO.Directory]::CreateDirectory($OutputDirectory)
    foreach ($name in @('URQ', 'URQUI')) {
        foreach ($extension in @('APP', 'json')) {
            Copy-Item -LiteralPath (Join-Path (Join-Path $BuildDirectory $name) "$name.$extension") `
                -Destination (Join-Path $OutputDirectory "$name.$extension") -Force
        }
    }
    [IO.File]::WriteAllText((Join-Path $OutputDirectory 'urq-build.json'),
        (ConvertTo-Json -InputObject $reports -Depth 8) + [Environment]::NewLine, $utf8)
    if (-not [string]::IsNullOrWhiteSpace($LibraryOutput) -or -not [string]::IsNullOrWhiteSpace($LicensesOutput)) {
        & (Join-Path $PSScriptRoot 'copy_urq_library.ps1') -ProjectRoot $root `
            -LibraryOutput $LibraryOutput -LicensesOutput $LicensesOutput
    }
} catch {
    [Console]::Error.WriteLine("URQ APP build: $($_.Exception.Message)")
    exit 1
}
