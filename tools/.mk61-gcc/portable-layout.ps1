#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Source,
    [Parameter(Mandatory = $true, Position = 1)]
    [string]$Output
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try {
    $sourcePath = [IO.Path]::GetFullPath($Source)
    $outputPath = [IO.Path]::GetFullPath($Output)
    if (-not [IO.File]::Exists($sourcePath)) {
        throw "linker script not found: $sourcePath"
    }
    $text = [IO.File]::ReadAllText($sourcePath).
        Replace("`r`n", "`n").Replace("`r", "`n")
    if ([regex]::Matches($text, [regex]::Escape("SECTIONS`n{")).Count -ne 1 -or
        $text -notmatch 'PROVIDE\s*\(\s*_end\s*=\s*\.\s*\)' -or
        [regex]::Matches($text, [regex]::Escape("    *(.bss)`n")).Count -ne 1) {
        throw 'unsupported STM32 startup/heap layout'
    }
    $text = $text.Replace(
        "SECTIONS`n{",
        "SECTIONS`n{`n  .mk61_help 0 (INFO) : { KEEP(*(.mk61_help)) }")
    $text += @'

__mk61_dynamic_begin = ALIGN(_end, 8);
__mk61_dynamic_end = ORIGIN(RAM) + LENGTH(RAM)
                    - (LENGTH(RAM) == 64K ? 6K : 16K) - 256;
ASSERT(LENGTH(RAM) == 64K || LENGTH(RAM) == 128K,
       "portable APP requires an F401/F411 SRAM profile")
ASSERT(_edata <= _sbss && _ebss <= _end &&
       __mk61_dynamic_begin <= __mk61_dynamic_end,
       "portable APP static data overlaps the stack guard")
ASSERT(!DEFINED(mk61_module_overlay),
       "portable APP must not reserve a fixed SRAM overlay")
'@
    $text += "`n"
    $parent = [IO.Path]::GetDirectoryName($outputPath)
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    [IO.File]::WriteAllText(
        $outputPath, $text, [Text.UTF8Encoding]::new($false))
} catch {
    [Console]::Error.WriteLine(
        "portable layout: $($_.Exception.Message)")
    exit 1
}
