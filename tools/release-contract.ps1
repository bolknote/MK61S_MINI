#requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('validate', 'profiles', 'resource-report')]
    [string]$Mode,
    [string]$Manifest = (Join-Path $PSScriptRoot 'release-contract.json'),
    [string]$Case,
    [string]$Elf,
    [string]$Bin,
    [string]$SizeTool,
    [string]$NmTool,
    [string]$StackSummary,
    [string]$OutputPrefix
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
$FeatureKeys = @(
    'focal', 'basic', 'wbmp', 'markdown', 'chip8', 'usb_screen',
    'ws0010_graphics', 'extended_font_settings', 'user_explorer',
    'math_backend', 'lto')

function Assert-Contract {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Get-RequiredProperty {
    param([object]$Object, [string]$Name, [string]$Where)
    Assert-Contract ($null -ne $Object) "$Where must be an object"
    $property = $Object.PSObject.Properties[$Name]
    Assert-Contract ($null -ne $property) "$Where`: missing key: $Name"
    return $property.Value
}

function Test-Identifier {
    param([object]$Value, [string]$Where)
    Assert-Contract (
        $Value -is [string] -and $Value -match '^[a-z0-9][a-z0-9-]*$') `
        "$Where`: invalid identifier '$Value'"
    return [string]$Value
}

function Test-Definition {
    param([object]$Value, [string]$Where)
    Assert-Contract (
        $Value -is [string] -and
        $Value -match '^[A-Z_][A-Z0-9_]*(?:=[A-Za-z0-9_+.,/-]+)?$') `
        "$Where`: invalid compiler definition '$Value'"
    return [string]$Value
}

function Test-Integer {
    param([object]$Value, [string]$Where, [long]$Minimum = 0)
    Assert-Contract (
        $Value -is [ValueType] -and
        $Value -isnot [bool] -and
        [long]$Value -ge $Minimum -and
        ([double]$Value -eq [long]$Value)) `
        "$Where`: expected integer >= $Minimum"
    return [long]$Value
}

function Test-Boolean {
    param([object]$Value, [string]$Where)
    Assert-Contract ($Value -is [bool]) "$Where`: expected boolean"
    return [bool]$Value
}

function Test-ReleaseContract {
    param([object]$Contract)
    Assert-Contract ($null -ne $Contract) 'manifest root must be an object'
    Assert-Contract ((Get-RequiredProperty $Contract 'schema' 'manifest') -eq 1) `
        'manifest.schema: only version 1 is supported'
    $toolchain = Get-RequiredProperty $Contract 'toolchain' 'manifest'
    foreach ($name in @(
            'arduino_cli', 'stm32_core', 'stm32_package_url', 'gnu_arm',
            'cmsis', 'cmsis_dsp')) {
        $value = Get-RequiredProperty $toolchain $name 'toolchain'
        Assert-Contract (
            $value -is [string] -and
            -not [string]::IsNullOrWhiteSpace($value)) `
            "toolchain.$name`: expected non-empty string"
    }
    $libraries = Get-RequiredProperty $toolchain 'libraries' 'toolchain'
    Assert-Contract (@($libraries.PSObject.Properties).Count -gt 0) `
        'toolchain.libraries: expected non-empty object'
    foreach ($library in $libraries.PSObject.Properties) {
        Assert-Contract (
            -not [string]::IsNullOrWhiteSpace($library.Name) -and
            $library.Value -is [string] -and
            -not [string]::IsNullOrWhiteSpace([string]$library.Value)) `
            'toolchain.libraries: invalid name/version'
    }

    $profiles = @(Get-RequiredProperty $Contract 'profiles' 'manifest')
    Assert-Contract ($profiles.Count -gt 0) `
        'profiles must be a non-empty array'
    $profileById = @{}
    for ($index = 0; $index -lt $profiles.Count; $index++) {
        $profile = $profiles[$index]
        $where = "profiles[$index]"
        $id = Test-Identifier (Get-RequiredProperty $profile 'id' $where) `
            "$where.id"
        Assert-Contract (-not $profileById.ContainsKey($id)) `
            "duplicate profile id: $id"
        $null = Test-Identifier (
            Get-RequiredProperty $profile 'platform' $where) "$where.platform"
        $null = Test-Identifier (
            Get-RequiredProperty $profile 'display' $where) "$where.display"
        $definitions = @(Get-RequiredProperty $profile 'defines' $where)
        $seenDefinitions = @{}
        foreach ($definition in $definitions) {
            $value = Test-Definition $definition "$where.defines"
            Assert-Contract (-not $seenDefinitions.ContainsKey($value)) `
                "$where.defines: duplicate definition"
            $seenDefinitions[$value] = $true
        }
        $null = Test-Boolean (
            Get-RequiredProperty $profile 'graphics' $where) "$where.graphics"
        $artifacts = Get-RequiredProperty $profile 'artifacts' $where
        $artifactNames = @($artifacts.PSObject.Properties.Name | Sort-Object)
        Assert-Contract (
            ($artifactNames -join ',') -eq 'f401,f411') `
            "$where.artifacts: exactly f401 and f411 are required"
        foreach ($mcu in @('f401', 'f411')) {
            $artifact = [string](Get-RequiredProperty $artifacts $mcu `
                "$where.artifacts")
            Assert-Contract (
                $artifact -match '^[A-Za-z0-9._-]+$') `
                "$where.artifacts.$mcu`: invalid artifact stem"
        }
        $profileById[$id] = $profile
    }

    $cases = @(Get-RequiredProperty $Contract 'cases' 'manifest')
    Assert-Contract ($cases.Count -gt 0) 'cases must be a non-empty array'
    $caseIds = @{}
    $groups = @{}
    for ($index = 0; $index -lt $cases.Count; $index++) {
        $item = $cases[$index]
        $where = "cases[$index]"
        $id = Test-Identifier (Get-RequiredProperty $item 'id' $where) `
            "$where.id"
        Assert-Contract (-not $caseIds.ContainsKey($id)) `
            "duplicate case id: $id"
        $caseIds[$id] = $true
        $caseGroups = @(Get-RequiredProperty $item 'groups' $where)
        Assert-Contract ($caseGroups.Count -gt 0) `
            "$where.groups: expected non-empty array"
        $localGroups = @{}
        foreach ($group in $caseGroups) {
            $groupId = Test-Identifier $group "$where.groups"
            Assert-Contract (-not $localGroups.ContainsKey($groupId)) `
                "$where.groups: duplicate group"
            $localGroups[$groupId] = $true
            $groups[$groupId] = $true
        }
        $mcu = [string](Get-RequiredProperty $item 'mcu' $where)
        $builder = [string](Get-RequiredProperty $item 'builder' $where)
        Assert-Contract ($mcu -in @('f401', 'f411')) `
            "$where.mcu: expected f401 or f411"
        Assert-Contract ($builder -in @('arduino', 'gcc')) `
            "$where.builder: expected arduino or gcc"
        $profileId = [string](Get-RequiredProperty $item 'profile' $where)
        Assert-Contract ($profileById.ContainsKey($profileId)) `
            "$where.profile: unknown profile '$profileId'"
        $product = Test-Boolean (
            Get-RequiredProperty $item 'product' $where) "$where.product"
        $publish = Test-Boolean (
            Get-RequiredProperty $item 'publish' $where) "$where.publish"
        Assert-Contract (-not $publish -or $product) `
            "$where`: a published case must be a product"

        $combined = New-Object 'System.Collections.Generic.List[string]'
        foreach ($definition in @($profileById[$profileId].defines)) {
            $combined.Add([string]$definition)
        }
        $definesProperty = $item.PSObject.Properties['defines']
        if ($null -ne $definesProperty) {
            foreach ($definition in @($definesProperty.Value)) {
                $combined.Add((Test-Definition $definition "$where.defines"))
            }
        }
        $defineNames = @{}
        foreach ($definition in $combined) {
            $name = $definition.Split('=')[0]
            Assert-Contract (-not $defineNames.ContainsKey($name)) `
                "$where`: compiler definition is overridden twice"
            $defineNames[$name] = $true
        }

        if ($builder -eq 'arduino') {
            $optimization = [string](Get-RequiredProperty $item `
                'optimization' $where)
            Assert-Contract ($optimization -in @('osstd', 'oslto')) `
                "$where.optimization: expected osstd or oslto"
            $expect = Get-RequiredProperty $item 'expect' $where
            $null = Test-Boolean (Get-RequiredProperty $expect `
                'usb_suspend' "$where.expect") "$where.expect.usb_suspend"
            $ws = Get-RequiredProperty $expect 'ws0010_graphics' `
                "$where.expect"
            Assert-Contract ($null -eq $ws -or $ws -is [bool]) `
                "$where.expect.ws0010_graphics: expected boolean/null"
        } else {
            $features = Get-RequiredProperty $item 'features' $where
            $actualFeatureNames = @(
                $features.PSObject.Properties.Name | Sort-Object)
            Assert-Contract (
                ($actualFeatureNames -join ',') -eq
                (($FeatureKeys | Sort-Object) -join ',')) `
                "$where.features: unexpected feature set"
            foreach ($feature in $FeatureKeys) {
                $value = Get-RequiredProperty $features $feature `
                    "$where.features"
                Assert-Contract (
                    $value -is [ValueType] -and
                    $value -isnot [bool] -and [int]$value -in @(0, 1)) `
                    "$where.features.$feature`: expected 0 or 1"
            }
        }

        $budgets = Get-RequiredProperty $item 'budgets' $where
        $flashCapacity = Test-Integer (
            Get-RequiredProperty $budgets 'flash_capacity' "$where.budgets") `
            "$where.budgets.flash_capacity" 1
        $flashHeadroom = Test-Integer (
            Get-RequiredProperty $budgets 'flash_min_headroom' `
                "$where.budgets") "$where.budgets.flash_min_headroom"
        Assert-Contract ($flashHeadroom -le $flashCapacity) `
            "$where`: Flash headroom exceeds capacity"
        $null = Test-Integer (
            Get-RequiredProperty $budgets 'stack_frame_limit' `
                "$where.budgets") "$where.budgets.stack_frame_limit" 1
        $ramCapacityProperty = $budgets.PSObject.Properties['ram_capacity']
        $ramLimitProperty = $budgets.PSObject.Properties['ram_limit']
        Assert-Contract (
            ($null -ne $ramCapacityProperty) -eq
            ($null -ne $ramLimitProperty)) `
            "$where`: RAM capacity and limit must appear together"
        if ($null -ne $ramCapacityProperty) {
            $ramCapacity = Test-Integer $ramCapacityProperty.Value `
                "$where.budgets.ram_capacity" 1
            $ramLimit = Test-Integer $ramLimitProperty.Value `
                "$where.budgets.ram_limit" 1
            Assert-Contract ($ramLimit -le $ramCapacity) `
                "$where`: RAM limit exceeds capacity"
        }
    }
    foreach ($required in @(
            'f411-release', 'f411-stop', 'f401-arduino', 'f401-product',
            'f401-capability')) {
        Assert-Contract ($groups.ContainsKey($required)) `
            "manifest is missing release group: $required"
    }
    $comparisons = Get-RequiredProperty $Contract 'comparison_budgets' `
        'manifest'
    Assert-Contract (@($comparisons.PSObject.Properties).Count -gt 0) `
        'comparison_budgets must be a non-empty object'
    foreach ($property in $comparisons.PSObject.Properties) {
        Assert-Contract ($property.Name -match '^[a-z][a-z0-9_]*$') `
            "comparison_budgets: invalid key '$($property.Name)'"
        $null = Test-Integer $property.Value `
            "comparison_budgets.$($property.Name)"
    }
}

function Invoke-TextTool {
    param([string]$Path, [string[]]$Arguments)
    Assert-Contract ([IO.File]::Exists([IO.Path]::GetFullPath($Path))) `
        "tool does not exist: $Path"
    $lines = @(& $Path @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "$([IO.Path]::GetFileName($Path)) failed ($LASTEXITCODE): " +
            (($lines | Out-String).Trim())
    }
    return ($lines | Out-String)
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

function Get-Sha256 {
    param([string]$Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { $hash = $sha.ComputeHash($stream) } finally { $stream.Dispose() }
    } finally { $sha.Dispose() }
    return (($hash | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Write-ResourceReport {
    param([object]$Contract)
    foreach ($required in @(
            @{ Name = 'Case'; Value = $Case },
            @{ Name = 'Elf'; Value = $Elf },
            @{ Name = 'Bin'; Value = $Bin },
            @{ Name = 'SizeTool'; Value = $SizeTool },
            @{ Name = 'NmTool'; Value = $NmTool },
            @{ Name = 'OutputPrefix'; Value = $OutputPrefix })) {
        Assert-Contract (-not [string]::IsNullOrWhiteSpace($required.Value)) `
            "-$($required.Name) is required for resource-report"
    }
    $selected = @($Contract.cases | Where-Object { $_.id -eq $Case })
    Assert-Contract ($selected.Count -eq 1) "unknown release case: $Case"
    $caseInfo = $selected[0]
    $elfPath = [IO.Path]::GetFullPath($Elf)
    $binPath = [IO.Path]::GetFullPath($Bin)
    Assert-Contract ([IO.File]::Exists($elfPath)) `
        "ELF does not exist: $elfPath"
    Assert-Contract ([IO.File]::Exists($binPath)) `
        "BIN does not exist: $binPath"

    $summaryText = Invoke-TextTool $SizeTool @('-d', $elfPath)
    $summaryMatch = [regex]::Match($summaryText,
        '(?m)^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+')
    Assert-Contract $summaryMatch.Success 'could not parse size summary'
    $textBytes = [long]$summaryMatch.Groups[1].Value
    $dataBytes = [long]$summaryMatch.Groups[2].Value
    $bssBytes = [long]$summaryMatch.Groups[3].Value
    $totalBytes = [long]$summaryMatch.Groups[4].Value
    Assert-Contract (($textBytes + $dataBytes + $bssBytes) -eq $totalBytes) `
        'size summary has inconsistent totals'
    $summary = [ordered]@{
        text = $textBytes; data = $dataBytes; bss = $bssBytes
        total = $totalBytes; static_ram = $dataBytes + $bssBytes
    }

    $sectionsText = Invoke-TextTool $SizeTool @('-A', '-d', $elfPath)
    $sections = New-Object 'System.Collections.Generic.List[object]'
    $sectionMap = @{}
    foreach ($line in $sectionsText -split "\r?\n") {
        if ($line -match '^\s*(\.[^\s]+)\s+(\d+)\s+') {
            $bytes = [long]$Matches[2]
            $sections.Add([ordered]@{ name = $Matches[1]; bytes = $bytes })
            $sectionMap[$Matches[1]] = $bytes
        }
    }
    Assert-Contract ($sections.Count -gt 0) 'could not parse ELF section sizes'
    [string[]]$sectionNames = @($sectionMap.Keys)
    [Array]::Sort($sectionNames, [StringComparer]::Ordinal)
    $sections = @($sectionNames | ForEach-Object {
        [ordered]@{ name = $_; bytes = [long]$sectionMap[$_] }
    })
    if ($sectionMap.ContainsKey('.data') -and $sectionMap.ContainsKey('.bss')) {
        $staticRam = $sectionMap['.data'] + $sectionMap['.bss']
        if ($sectionMap.ContainsKey('.noinit')) {
            $staticRam += $sectionMap['.noinit']
        }
        $minimum = if ($sectionMap.ContainsKey('._user_heap_stack')) {
            $sectionMap['._user_heap_stack']
        } else { 0 }
        $summary.static_ram = $staticRam
        $summary.linker_checked_ram = $staticRam + $minimum
        $summary.linker_heap_stack_minimum = $minimum
        $summary.fixed_app_reserve = 0
    }

    $symbolsText = Invoke-TextTool $NmTool @(
        '-S', '--size-sort', '--radix=d', '-C', $elfPath)
    $symbols = New-Object 'System.Collections.Generic.List[object]'
    foreach ($line in $symbolsText -split "\r?\n") {
        if ($line -match '^\s*(\d+)\s+(\d+)\s+(\S)\s+(.+)$' -and
            [long]$Matches[2] -gt 0) {
            $symbols.Add([pscustomobject]@{
                address = [long]$Matches[1]
                bytes = [long]$Matches[2]
                type = $Matches[3]
                name = $Matches[4]
            })
        }
    }
    $symbols = @($symbols | Sort-Object `
        @{ Expression = 'bytes'; Descending = $true }, `
        @{ Expression = 'name'; Descending = $false }, `
        @{ Expression = 'address'; Descending = $false } | Select-Object -First 10)

    $stack = $null
    if (-not [string]::IsNullOrWhiteSpace($StackSummary)) {
        $stack = ConvertFrom-Json -InputObject (
            [IO.File]::ReadAllText([IO.Path]::GetFullPath($StackSummary)))
        Assert-Contract ($stack.schema -eq 1) `
            'stack summary has unsupported schema'
        $null = Test-Integer $stack.max_frame 'stack summary max_frame'
    }
    $budgets = $caseInfo.budgets
    $binarySize = (Get-Item -LiteralPath $binPath).Length
    $flashFree = [long]$budgets.flash_capacity - $binarySize
    $violations = New-Object 'System.Collections.Generic.List[string]'
    if ($flashFree -lt [long]$budgets.flash_min_headroom) {
        $violations.Add(
            "Flash free $flashFree < $($budgets.flash_min_headroom)")
    }
    if ($null -ne $budgets.PSObject.Properties['ram_limit'] -and
        [long]$summary.static_ram -gt [long]$budgets.ram_limit) {
        $violations.Add(
            "static RAM $($summary.static_ram) > $($budgets.ram_limit)")
    }
    if ($null -ne $stack -and
        [long]$stack.max_frame -gt [long]$budgets.stack_frame_limit) {
        $violations.Add(
            "stack frame $($stack.max_frame) > $($budgets.stack_frame_limit)")
    }
    $profile = @($Contract.profiles | Where-Object {
        $_.id -eq $caseInfo.profile })[0]
    $artifactProperty = $caseInfo.PSObject.Properties['artifact']
    $artifact = if ($null -ne $artifactProperty -and
        -not [string]::IsNullOrWhiteSpace([string]$artifactProperty.Value)) {
        [string]$artifactProperty.Value
    } else { [string]$profile.artifacts.PSObject.Properties[$caseInfo.mcu].Value }
    $status = if ($violations.Count -eq 0) { 'ok' } else { 'failed' }
    $report = [ordered]@{
        schema = 1; case = $Case; mcu = [string]$caseInfo.mcu
        profile = [string]$caseInfo.profile; artifact = $artifact
        product = [bool]$caseInfo.product; budgets = $budgets
        binary = [ordered]@{
            bytes = $binarySize; flash_free = $flashFree
            sha256 = Get-Sha256 $binPath
        }
        elf = [ordered]@{
            summary = $summary; sections = $sections
            largest_symbols = $symbols
        }
        stack = $stack; status = $status; violations = @($violations)
    }
    Write-AtomicText "$OutputPrefix.json" `
        (($report | ConvertTo-Json -Depth 20) + "`n")
    $ramLimit = if ($null -ne $budgets.PSObject.Properties['ram_limit']) {
        [string]$budgets.ram_limit
    } else { 'reported only' }
    $ramFree = if ($null -ne $budgets.PSObject.Properties['ram_capacity']) {
        [string]([long]$budgets.ram_capacity - [long]$summary.static_ram)
    } else { 'n/a' }
    $markdown = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in @(
            "# Resource report: $Case", '', "Status: **$($status.ToUpper())**",
            '', '| Resource | Used | Capacity/limit | Free |',
            '|---|---:|---:|---:|',
            "| Sealed Flash | $binarySize | $($budgets.flash_capacity) | $flashFree |",
            "| Static RAM | $($summary.static_ram) | $ramLimit | $ramFree |")) {
        $markdown.Add($line)
    }
    if ($null -ne $stack) {
        $markdown.Add(
            "| Largest stack frame | $($stack.max_frame) | " +
            "$($budgets.stack_frame_limit) | " +
            "$([long]$budgets.stack_frame_limit - [long]$stack.max_frame) |")
    }
    foreach ($line in @('', '## Ten largest ELF symbols', '',
            '| Bytes | Type | Symbol |', '|---:|:---:|---|')) {
        $markdown.Add($line)
    }
    foreach ($symbol in $symbols) {
        $safeName = ([string]$symbol.name).Replace('|', '\|')
        $markdown.Add(
            "| $($symbol.bytes) | $($symbol.type) | ``$safeName`` |")
    }
    if ($violations.Count -gt 0) {
        $markdown.Add(''); $markdown.Add('## Violations'); $markdown.Add('')
        foreach ($violation in $violations) {
            $markdown.Add("- $violation")
        }
    }
    Write-AtomicText "$OutputPrefix.md" (($markdown -join "`n") + "`n")
    Write-Host "resource report: $($status.ToUpper()) $Case"
    return $violations.Count -eq 0
}

try {
    $manifestPath = [IO.Path]::GetFullPath($Manifest)
    Assert-Contract ([IO.File]::Exists($manifestPath)) `
        "cannot read $manifestPath"
    $contract = ConvertFrom-Json -InputObject (
        [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8))
    Test-ReleaseContract $contract
    if ($Mode -eq 'validate') {
        Write-Host (
            "release contract: OK profiles=$(@($contract.profiles).Count) " +
            "cases=$(@($contract.cases).Count)")
    } elseif ($Mode -eq 'profiles') {
        foreach ($profile in $contract.profiles) { Write-Output $profile.id }
    } elseif ($Mode -eq 'resource-report') {
        if (-not (Write-ResourceReport $contract)) { exit 1 }
    }
} catch {
    [Console]::Error.WriteLine("release contract: FAIL: $($_.Exception.Message)")
    exit 2
}
