#requires -Version 5.1
param(
    [Parameter(Mandatory = $true)][string]$InputFile,
    [string]$Programmer
)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'dfu.ps1')
    Invoke-Mk61ResidentDfu -InputFile $InputFile -Programmer $Programmer
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
