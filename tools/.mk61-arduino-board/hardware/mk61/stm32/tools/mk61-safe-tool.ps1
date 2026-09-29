# Keep this script parameter-free. GNU Arm options such as -o must reach the
# child process verbatim instead of being interpreted as PowerShell options.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

if ($args.Count -lt 2) {
    [Console]::Error.WriteLine(
        'MK61s Arduino tool wrapper: expected TEMP directory and tool path')
    exit 64
}

$safeTemp = [IO.Path]::GetFullPath([string]$args[0])
$tool = [string]$args[1]
$toolArguments = @()
if ($args.Count -gt 2) {
    $toolArguments = @($args[2..($args.Count - 1)])
}

[IO.Directory]::CreateDirectory($safeTemp) | Out-Null
$env:TEMP = $safeTemp
$env:TMP = $safeTemp
$env:TMPDIR = $safeTemp

& $tool @toolArguments
exit $LASTEXITCODE
