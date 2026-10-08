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
for ($index = 2; $index -lt $args.Count; ++$index) {
    $argument = [string]$args[$index]
    # -File consumes the drive colon in attached native options, e.g.
    # -LC:/build or -Wl,--script=C:/core.ld. They arrive as two arguments.
    # Rejoin only those linker path options; separate -L C:/build is intact.
    if ($argument -cmatch '^-(?:L|Wl,.*[,=])[A-Za-z]$' -and
        $index + 1 -lt $args.Count -and
        [string]$args[$index + 1] -match '^[\\/]') {
        $argument += ':' + [string]$args[++$index]
    }
    $toolArguments += $argument
}

[IO.Directory]::CreateDirectory($safeTemp) | Out-Null
$env:TEMP = $safeTemp
$env:TMP = $safeTemp
$env:TMPDIR = $safeTemp

# Windows PowerShell 5 rebuilds native command lines and can split options
# such as -LC:\path while forwarding a large splatted array. GCC response
# files avoid that legacy quoting layer. Forward slashes also keep GCC's
# response-file parser from treating Windows path separators as escapes.
$responseFile = Join-Path $safeTemp 'mk61-link.rsp'
$responseLines = foreach ($argument in $toolArguments) {
    $normalized = ([string]$argument).Replace('\', '/')
    '"' + $normalized.Replace('"', '\"') + '"'
}
[IO.File]::WriteAllLines(
    $responseFile, $responseLines, [Text.Encoding]::Default)

$responseArgument = '@' + $responseFile.Replace('\', '/')
& $tool $responseArgument
exit $LASTEXITCODE
