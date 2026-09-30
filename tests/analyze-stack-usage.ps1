#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CompileCommands,
    [string[]]$SourceRoot = @(),
    [string[]]$Source = @(),
    [ValidateRange(1, 128)]
    [int]$Jobs = [Math]::Min([Environment]::ProcessorCount, 8),
    [ValidateRange(1, 1048576)]
    [int]$MaxFrame = 5120,
    [ValidateRange(0, 100)]
    [int]$Top = 5,
    [string]$SummaryJson
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
$ValueOptions = @('-o', '-MF', '-MT', '-MQ', '-MJ')
$DropOptions = @(
    '-MMD', '-MD', '-MP', '-MG', '-ffat-lto-objects',
    '-fno-fat-lto-objects', '-fstack-usage', '-fno-lto')

function Split-PosixCommandLine {
    param([string]$Command)
    $result = New-Object 'System.Collections.Generic.List[string]'
    $current = New-Object Text.StringBuilder
    $quote = [char]0
    $escaped = $false
    $started = $false
    foreach ($character in $Command.ToCharArray()) {
        if ($escaped) {
            [void]$current.Append($character)
            $escaped = $false; $started = $true; continue
        }
        if ($quote -eq "'") {
            if ($character -eq "'") { $quote = [char]0 }
            else { [void]$current.Append($character) }
            $started = $true; continue
        }
        if ($quote -eq '"') {
            if ($character -eq '"') { $quote = [char]0 }
            elseif ($character -eq '\') { $escaped = $true }
            else { [void]$current.Append($character) }
            $started = $true; continue
        }
        if ($character -eq '\') { $escaped = $true; $started = $true; continue }
        if ($character -eq "'" -or $character -eq '"') {
            $quote = $character; $started = $true; continue
        }
        if ([char]::IsWhiteSpace($character)) {
            if ($started) {
                $result.Add($current.ToString())
                [void]$current.Clear(); $started = $false
            }
            continue
        }
        [void]$current.Append($character); $started = $true
    }
    if ($escaped) { [void]$current.Append('\') }
    if ($quote -ne [char]0) { throw 'unterminated quote in compile command' }
    if ($started) { $result.Add($current.ToString()) }
    return $result.ToArray()
}

function Initialize-WindowsCommandLineParser {
    if ('Mk61NativeCommandLine' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class Mk61NativeCommandLine {
    [DllImport("shell32.dll", SetLastError = true)]
    private static extern IntPtr CommandLineToArgvW(
        [MarshalAs(UnmanagedType.LPWStr)] string commandLine,
        out int argumentCount);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr LocalFree(IntPtr memory);

    public static string[] Split(string commandLine) {
        int count;
        IntPtr values = CommandLineToArgvW(commandLine, out count);
        if (values == IntPtr.Zero) {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        try {
            string[] result = new string[count];
            for (int index = 0; index < count; ++index) {
                IntPtr value = Marshal.ReadIntPtr(values, index * IntPtr.Size);
                result[index] = Marshal.PtrToStringUni(value);
            }
            return result;
        } finally {
            LocalFree(values);
        }
    }
}
'@
}

function Get-EntryArguments {
    param([object]$Entry)
    $arguments = $Entry.PSObject.Properties['arguments']
    if ($null -ne $arguments -and @($arguments.Value).Count -gt 0) {
        return [string[]]@($arguments.Value)
    }
    $commandProperty = $Entry.PSObject.Properties['command']
    if ($null -eq $commandProperty -or
        [string]::IsNullOrWhiteSpace([string]$commandProperty.Value)) {
        throw 'compile database entry has no arguments or command'
    }
    if ($env:OS -eq 'Windows_NT') {
        Initialize-WindowsCommandLineParser
        return [Mk61NativeCommandLine]::Split(
            [string]$commandProperty.Value)
    }
    return Split-PosixCommandLine ([string]$commandProperty.Value)
}

function Resolve-EntryPath {
    param([string]$Path, [string]$Directory)
    if ([IO.Path]::IsPathRooted($Path)) {
        return [IO.Path]::GetFullPath($Path)
    }
    return [IO.Path]::GetFullPath((Join-Path $Directory $Path))
}

function Test-PathBelow {
    param([string]$Path, [string]$Root)
    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar)
    $parent = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar)
    if ($candidate.Equals($parent, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $candidate.StartsWith(
        $parent + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)
}

function Quote-WindowsArgument {
    param([string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $result = New-Object Text.StringBuilder
    [void]$result.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $backslashes++; continue }
        if ($character -eq '"') {
            [void]$result.Append(('\' * (2 * $backslashes + 1)))
            [void]$result.Append('"'); $backslashes = 0; continue
        }
        if ($backslashes -gt 0) {
            [void]$result.Append(('\' * $backslashes)); $backslashes = 0
        }
        [void]$result.Append($character)
    }
    if ($backslashes -gt 0) {
        [void]$result.Append(('\' * (2 * $backslashes)))
    }
    [void]$result.Append('"')
    return $result.ToString()
}

function Start-AnalysisCompile {
    param([object]$Work)
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $Work.Compiler
    $start.Arguments = (@($Work.Arguments | ForEach-Object {
        Quote-WindowsArgument ([string]$_)
    }) -join ' ')
    $start.WorkingDirectory = $Work.Directory
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    if (-not $process.Start()) {
        throw "cannot start stack analysis compiler: $($Work.Compiler)"
    }
    # Drain both pipes while the compiler runs. Reading only after HasExited
    # can deadlock when a diagnostic fills an OS pipe buffer.
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    return [pscustomobject]@{
        Process = $process; Work = $Work
        Stdout = $stdout; Stderr = $stderr
    }
}

function Write-AtomicText {
    param([string]$Path, [string]$Text)
    $full = [IO.Path]::GetFullPath($Path)
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($full)) |
        Out-Null
    $temporary = "$full.$PID.tmp"
    [IO.File]::WriteAllText($temporary, $Text, $Utf8NoBom)
    Move-Item -LiteralPath $temporary -Destination $full -Force
}

try {
    $databasePath = [IO.Path]::GetFullPath($CompileCommands)
    if (-not [IO.File]::Exists($databasePath)) {
        throw "compile database not found: $databasePath"
    }
    if ($SourceRoot.Count -eq 0 -and $Source.Count -eq 0) {
        throw 'at least one -SourceRoot or -Source is required'
    }
    [string[]]$roots = @($SourceRoot | ForEach-Object {
        [IO.Path]::GetFullPath($_)
    })
    $exact = @{}
    foreach ($path in $Source) {
        $exact[[IO.Path]::GetFullPath($path)] = $true
    }
    $entries = @(ConvertFrom-Json -InputObject (
        [IO.File]::ReadAllText($databasePath, [Text.Encoding]::UTF8)))
    $selected = New-Object 'System.Collections.Generic.List[object]'
    $seen = @{}
    foreach ($entry in $entries) {
        $fileProperty = $entry.PSObject.Properties['file']
        $directoryProperty = $entry.PSObject.Properties['directory']
        if ($null -eq $fileProperty -or $null -eq $directoryProperty) {
            continue
        }
        $directory = [IO.Path]::GetFullPath([string]$directoryProperty.Value)
        $sourcePath = Resolve-EntryPath ([string]$fileProperty.Value) $directory
        $included = $exact.ContainsKey($sourcePath)
        if (-not $included) {
            foreach ($root in $roots) {
                if (Test-PathBelow $sourcePath $root) {
                    $included = $true; break
                }
            }
        }
        if (-not $included) { continue }
        $arguments = Get-EntryArguments $entry
        if ($arguments.Count -eq 0) {
            throw "empty compiler command for $sourcePath"
        }
        $identity = $sourcePath + [char]0 + ($arguments -join [char]0)
        if ($seen.ContainsKey($identity)) { continue }
        $seen[$identity] = $true
        $selected.Add([pscustomobject]@{
            Source = $sourcePath; Directory = $directory
            Original = $arguments
        })
    }
    if ($selected.Count -eq 0) {
        throw 'no selected translation units in compile database'
    }

    $workRoot = Join-Path ([IO.Path]::GetDirectoryName($databasePath)) (
        '.mk61-stack-analysis-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($workRoot) | Out-Null
    $running = $null
    try {
        $queue = New-Object 'System.Collections.Generic.Queue[object]'
        for ($unit = 0; $unit -lt $selected.Count; $unit++) {
            $entry = $selected[$unit]
            $rewritten = New-Object 'System.Collections.Generic.List[string]'
            $haveCompileOnly = $false
            for ($index = 1; $index -lt $entry.Original.Count; $index++) {
                $argument = [string]$entry.Original[$index]
                if ($argument -in $ValueOptions) { $index++; continue }
                if ($argument -in $DropOptions -or $argument -like '-flto*') {
                    continue
                }
                try {
                    $argumentPath = Resolve-EntryPath $argument $entry.Directory
                    if ($argumentPath.Equals(
                            $entry.Source,
                            [StringComparison]::OrdinalIgnoreCase)) {
                        continue
                    }
                } catch { }
                if ($argument -eq '-c') { $haveCompileOnly = $true }
                $rewritten.Add($argument)
            }
            if (-not $haveCompileOnly) { $rewritten.Add('-c') }
            foreach ($argument in @(
                    '-fno-lto', '-fstack-usage', $entry.Source, '-o',
                    (Join-Path $workRoot "unit-$unit.o"))) {
                $rewritten.Add($argument)
            }
            $queue.Enqueue([pscustomobject]@{
                Compiler = [string]$entry.Original[0]
                Arguments = $rewritten.ToArray()
                Directory = $entry.Directory
                Source = $entry.Source
            })
        }
        $running = New-Object 'System.Collections.Generic.List[object]'
        while ($queue.Count -gt 0 -or $running.Count -gt 0) {
            while ($queue.Count -gt 0 -and $running.Count -lt $Jobs) {
                $running.Add((Start-AnalysisCompile $queue.Dequeue()))
            }
            $completed = $false
            for ($index = $running.Count - 1; $index -ge 0; $index--) {
                $item = $running[$index]
                if (-not $item.Process.HasExited) { continue }
                $stdout = $item.Stdout.Result
                $stderr = $item.Stderr.Result
                $exitCode = $item.Process.ExitCode
                $item.Process.Dispose()
                $running.RemoveAt($index)
                $completed = $true
                if ($exitCode -ne 0) {
                    throw "stack analysis compile failed for " +
                        "$($item.Work.Source) ($exitCode):`n$stdout$stderr"
                }
                if (-not [string]::IsNullOrWhiteSpace($stdout)) {
                    [Console]::Error.Write($stdout)
                }
                if (-not [string]::IsNullOrWhiteSpace($stderr)) {
                    [Console]::Error.Write($stderr)
                }
            }
            if (-not $completed -and $running.Count -gt 0) {
                Start-Sleep -Milliseconds 20
            }
        }

        $reports = @(Get-ChildItem -LiteralPath $workRoot -Recurse `
            -Filter '*.su' -File | Sort-Object FullName)
        if ($reports.Count -eq 0) { throw "no .su reports below $workRoot" }
        $records = New-Object 'System.Collections.Generic.List[object]'
        foreach ($report in $reports) {
            $lineNumber = 0
            foreach ($line in [IO.File]::ReadAllLines($report.FullName)) {
                $lineNumber++
                if ([string]::IsNullOrEmpty($line)) { continue }
                if ($line -notmatch '^(.*)\t([0-9]+)\t([^\t]+)$') {
                    throw "$($report.FullName):${lineNumber}: malformed stack-usage record"
                }
                $tokens = @($Matches[3] -split ',')
                foreach ($token in $tokens) {
                    if ($token -notin @('static', 'dynamic', 'bounded')) {
                        throw "$($report.FullName):${lineNumber}: unknown qualifier '$($Matches[3])'"
                    }
                }
                $dynamic = $tokens -contains 'dynamic'
                $static = $tokens -contains 'static'
                if ($dynamic -eq $static -or
                    (($tokens -contains 'bounded') -and -not $dynamic)) {
                    throw "$($report.FullName):${lineNumber}: invalid qualifier '$($Matches[3])'"
                }
                $records.Add([pscustomobject]@{
                    Report = $report.FullName; Description = $Matches[1]
                    Bytes = [int]$Matches[2]; Qualifier = $Matches[3]
                    Unbounded = $dynamic -and -not ($tokens -contains 'bounded')
                })
            }
        }
        if ($records.Count -eq 0) {
            throw "all .su reports below $workRoot are empty"
        }
        $ranked = @($records | Sort-Object `
            @{ Expression = 'Bytes'; Descending = $true }, `
            @{ Expression = 'Description'; Descending = $true })
        $failures = New-Object 'System.Collections.Generic.List[string]'
        foreach ($record in $records) {
            if ($record.Unbounded) {
                $failures.Add(
                    "unbounded dynamic frame: $($record.Description) " +
                    "($($record.Bytes) bytes, $($record.Report))")
            }
            if ($record.Bytes -gt $MaxFrame) {
                $failures.Add(
                    "frame exceeds $MaxFrame bytes: $($record.Description) " +
                    "($($record.Bytes) bytes, $($record.Report))")
            }
        }
        $bounded = @($records | Where-Object {
            $_.Qualifier -split ',' -contains 'dynamic'
        }).Count
        $description = $ranked[0].Description -replace
            '^.*[/\\](?=[^/\\]+:\d+:\d+:)', ''
        if (-not [string]::IsNullOrWhiteSpace($SummaryJson)) {
            $summary = [ordered]@{
                schema = 1; records = $records.Count
                max_frame = $ranked[0].Bytes; max_function = $description
                limit = $MaxFrame; dynamic_bounded = $bounded
                unbounded = @($records | Where-Object Unbounded).Count
                status = $(if ($failures.Count -eq 0) { 'ok' } else { 'failed' })
                compiled_units = $selected.Count
            }
            Write-AtomicText $SummaryJson `
                (($summary | ConvertTo-Json -Depth 4) + "`n")
        }
        Write-Host (
            "stack analysis: compiled=$($selected.Count) " +
            'shipping_artifact=untouched')
        for ($index = 0; $index -lt [Math]::Min($Top, $ranked.Count); $index++) {
            $record = $ranked[$index]
            Write-Host (
                "STACK frame=$($record.Bytes) qualifier=$($record.Qualifier) " +
                "function=$($record.Description)")
        }
        if ($failures.Count -gt 0) {
            foreach ($failure in $failures) {
                [Console]::Error.WriteLine("stack usage: FAIL: $failure")
            }
            exit 1
        }
        Write-Host (
            "stack usage: OK files=$($reports.Count) records=$($records.Count) " +
            "max=$($ranked[0].Bytes) limit=$MaxFrame " +
            "dynamic_bounded=$bounded")
    } finally {
        if ($null -ne $running) {
            foreach ($item in $running.ToArray()) {
                try {
                    if (-not $item.Process.HasExited) {
                        $item.Process.Kill()
                        $item.Process.WaitForExit()
                    }
                } catch { }
                try { $item.Process.Dispose() } catch { }
            }
        }
        if ([IO.Directory]::Exists($workRoot)) {
            Remove-Item -LiteralPath $workRoot -Recurse -Force
        }
    }
} catch {
    [Console]::Error.WriteLine("stack analysis: FAIL: $($_.Exception.Message)")
    exit 2
}
