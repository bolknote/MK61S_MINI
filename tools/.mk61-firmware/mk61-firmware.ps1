#requires -Version 5.1

<#
  Interactive firmware builder/uploader for MK61S_MINI.
  The UI is implemented with System.Console; no dialog module is required.
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$script:Escape = [char]27
try {
    [Console]::OutputEncoding = $script:Utf8NoBom
    $OutputEncoding = $script:Utf8NoBom
} catch {}

function Get-EnvironmentOrDefault {
    param([string]$Name, [string]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

$script:ScriptDir = $PSScriptRoot
$script:ProjectRoot = (Resolve-Path (Join-Path $script:ScriptDir '../..')).Path
$script:ArduinoCli = Get-EnvironmentOrDefault 'MK61_ARDUINO_CLI' 'arduino-cli'
$script:BuildRoot = Get-EnvironmentOrDefault 'MK61_BUILD_ROOT' (Join-Path $script:ProjectRoot '.build/mk61-firmware')
$script:OutputDir = Get-EnvironmentOrDefault 'MK61_OUTPUT_DIR' (Join-Path $script:ProjectRoot 'binary')
$script:ConfigFile = Get-EnvironmentOrDefault 'MK61_CONFIG_FILE' (Join-Path $script:ProjectRoot '.mk61-firmware.conf')
$script:LegacySelectionFile = Join-Path $script:BuildRoot 'selected-profile'
$script:LastLog = Join-Path $script:BuildRoot 'last.log'

$script:Stm32CoreVersion = '2.12.0'
$script:Stm32PackageUrl = 'https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json'
$script:Fqbn = 'STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'

$script:IsWindowsHost = $env:OS -eq 'Windows_NT'
$script:IsMacHost = $false
try {
    $script:IsWindowsHost = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [Runtime.InteropServices.OSPlatform]::Windows)
    $script:IsMacHost = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [Runtime.InteropServices.OSPlatform]::OSX)
} catch {
    $script:IsMacHost = -not $script:IsWindowsHost -and (uname -s 2>$null) -eq 'Darwin'
}

function Initialize-TuiGlyphs {
    if ($script:IsWindowsHost) {
        # Windows 10 conhost with Consolas replaces several ballot/radio glyphs
        # with the same question-box.  Keep the Norton-style UI unambiguous in
        # both Windows PowerShell 5.1 and PowerShell 7.
        $script:Glyphs = @{
            Selector = '>'; RadioOff = '( )'; RadioOn = '(*)'; RadioDisabled = '(-)'
            CheckOff = '[ ]'; CheckOn = '[x]'
            MenuUpload = '^'; MenuBuild = '#'; MenuChoice = 'o'; MenuOptions = '[x]'
            MenuDetect = '?'; MenuCheck = '+'; MenuInstall = 'v'; MenuLog = '='; MenuQuit = 'x'
        }
    } else {
        $script:Glyphs = @{
            Selector = '▶'; RadioOff = '○'; RadioOn = '◉'; RadioDisabled = '⊘'
            CheckOff = '☐'; CheckOn = '☑'
            MenuUpload = '▲'; MenuBuild = '⚒'; MenuChoice = '◉'; MenuOptions = '☑'
            MenuDetect = '⌕'; MenuCheck = '✓'; MenuInstall = '↓'; MenuLog = '≡'; MenuQuit = '×'
        }
    }
}

Initialize-TuiGlyphs

$script:State = [ordered]@{
    Profile = ''
    Platform = ''
    Screen = ''
    CliProfile = $false
    EnableFocal = 1
    EnableTinyBasic = 1
    EnableWbmp = 1
    EnableUsbScreen = 0
    EnableFonts = 0
    EnableExplorer = 1
    EnableCoreMath = 0
    DeviceStatus = 'не проверялось'
    DfuPath = ''
    CubeProgrammerPath = ''
    DfuStatus = 'не найден'
    DetectedPort = ''
    DetectedVersion = ''
    Interactive = $false
}

$script:ActiveJob = $null
$script:ScreenActive = $false
$script:ListFirstRow = 0
$script:ProgressTitle = ''
$script:ProgressVisible = $false
$script:OriginalForeground = [ConsoleColor]::Gray
$script:OriginalBackground = [ConsoleColor]::Black
$script:OriginalCursorVisible = $true
$script:ConsoleColumns = 80
$script:ConsoleRows = 24
$script:WindowWidth = 76
$script:TextWidth = 72
$script:MarginWidth = 2
$script:UseColor = (Get-EnvironmentOrDefault 'MK61_COLOR' 'always') -ne 'never'

$script:Styles = @{
    Outside  = @([ConsoleColor]::Gray,     [ConsoleColor]::Black)
    Window   = @([ConsoleColor]::White,    [ConsoleColor]::DarkBlue)
    Border   = @([ConsoleColor]::Cyan,     [ConsoleColor]::DarkBlue)
    Muted    = @([ConsoleColor]::DarkCyan, [ConsoleColor]::DarkBlue)
    Selected = @([ConsoleColor]::Black,    [ConsoleColor]::Cyan)
    Yellow   = @([ConsoleColor]::Yellow,   [ConsoleColor]::DarkBlue)
    Red      = @([ConsoleColor]::Red,      [ConsoleColor]::DarkBlue)
    White    = @([ConsoleColor]::White,    [ConsoleColor]::DarkBlue)
    Cyan     = @([ConsoleColor]::Cyan,     [ConsoleColor]::DarkBlue)
}
$script:AnsiStyles = @{
    Outside  = '[0m'
    Window   = '[0;37;44m'
    Border   = '[1;36;44m'
    Muted    = '[0;36;44m'
    Selected = '[30;46m'
    Yellow   = '[1;33;44m'
    Red      = '[1;31;44m'
    White    = '[1;37;44m'
    Cyan     = '[1;36;44m'
}

$script:Profiles = [ordered]@{
    'mini-v3-a00' = @{
        Label = 'mini V3 · LCD1602 A00'; Platform = 'mini-v3'; Screen = 'lcd1602-a00'
        Flags = '-DMK61_LCD1602_A00'; Artifact = 'mk61s-M-mini-v3-lcd1602-a00-f411.bin'
    }
    'mini-v3-a02' = @{
        Label = 'mini V3 · LCD1602 A02'; Platform = 'mini-v3'; Screen = 'lcd1602-a02'
        Flags = '-DMK61_LCD1602_A02'; Artifact = 'mk61s-M-mini-v3-lcd1602-a02-f411.bin'
    }
    'mini-v2-a00' = @{
        Label = 'mini V2 · LCD1602 A00'; Platform = 'mini-v2'; Screen = 'lcd1602-a00'
        Flags = '-DREVISION_V2 -DMK61_LCD1602_A00'; Artifact = 'mk61s-M-mini-v2-lcd1602-a00-f411.bin'
    }
    'mini-v2-a02' = @{
        Label = 'mini V2 · LCD1602 A02'; Platform = 'mini-v2'; Screen = 'lcd1602-a02'
        Flags = '-DREVISION_V2 -DMK61_LCD1602_A02'; Artifact = 'mk61s-M-mini-v2-lcd1602-a02-f411.bin'
    }
    'classic-v2' = @{
        Label = 'Classic V2 · UC1609 192×64'; Platform = 'classic-v2'; Screen = 'uc1609'
        Flags = '-DMK61_BOARD_CLASSIC_V2'; Artifact = 'mk61s-M-classic-v2-uc1609-f411.bin'
    }
    'classic-v3' = @{
        Label = 'Classic V3 · UC1609 192×64'; Platform = 'classic-v3'; Screen = 'uc1609'
        Flags = '-DMK61_BOARD_CLASSIC_V3'; Artifact = 'mk61s-M-classic-v3-uc1609-f411.bin'
    }
    '40th' = @{
        Label = 'MK61s 40th · UC1609 192×64'; Platform = '40th'; Screen = 'uc1609'
        Flags = '-DMK61_BOARD_40TH'; Artifact = 'mk61s-M-40th-f411.bin'
    }
}

$script:PlatformLabels = [ordered]@{
    'mini-v3' = 'mini V3'
    'mini-v2' = 'mini V2'
    'classic-v2' = 'Classic V2'
    'classic-v3' = 'Classic V3'
    '40th' = 'MK61s 40th'
}

$script:ScreenLabels = [ordered]@{
    'lcd1602-a00' = 'LCD1602 · CGROM A00'
    'lcd1602-a02' = 'LCD1602 · CGROM A02'
    'uc1609' = 'UC1609 · 192×64'
}

function Test-Profile { param([string]$Id) return $script:Profiles.Contains($Id) }
function Test-Platform { param([string]$Id) return $script:PlatformLabels.Contains($Id) }
function Test-Screen { param([string]$Id) return $script:ScreenLabels.Contains($Id) }

function Test-HardwareCompatible {
    param([string]$Platform, [string]$Screen)
    switch ("$Platform`:$Screen") {
        'mini-v3:lcd1602-a00' { return $true }
        'mini-v3:lcd1602-a02' { return $true }
        'mini-v2:lcd1602-a00' { return $true }
        'mini-v2:lcd1602-a02' { return $true }
        'classic-v2:uc1609' { return $true }
        'classic-v3:uc1609' { return $true }
        '40th:uc1609' { return $true }
    }
    return $false
}

function Get-ProfileFromHardware {
    param([string]$Platform, [string]$Screen)
    foreach ($id in $script:Profiles.Keys) {
        $item = $script:Profiles[$id]
        if ($item.Platform -eq $Platform -and $item.Screen -eq $Screen) { return $id }
    }
    return ''
}

function Set-HardwareFromProfile {
    param([string]$Profile)
    if (-not (Test-Profile $Profile)) { return $false }
    $script:State.Platform = $script:Profiles[$Profile].Platform
    $script:State.Screen = $script:Profiles[$Profile].Screen
    return $true
}

function Sync-ProfileFromHardware {
    $script:State.Profile = Get-ProfileFromHardware $script:State.Platform $script:State.Screen
}

function Get-PlatformLabel {
    param([string]$Id)
    if (Test-Platform $Id) { return $script:PlatformLabels[$Id] }
    return 'не выбрана'
}

function Get-ScreenLabel {
    param([string]$Id)
    if (Test-Screen $Id) { return $script:ScreenLabels[$Id] }
    return 'не выбран'
}

function Get-ProfileLabel {
    param([string]$Id)
    if (Test-Profile $Id) { return $script:Profiles[$Id].Label }
    return 'не выбрано'
}

function Get-CompileOptionFlags {
    return @(
        "-DMK61_ENABLE_FOCAL=$($script:State.EnableFocal)"
        "-DMK61_ENABLE_TINYBASIC=$($script:State.EnableTinyBasic)"
        "-DMK61_ENABLE_WBMP_VIEWER=$($script:State.EnableWbmp)"
        "-DMK61_ENABLE_USB_SCREEN=$($script:State.EnableUsbScreen)"
        "-DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$($script:State.EnableFonts)"
        "-DMK61_USER_EXPLORER_SHORTCUT=$($script:State.EnableExplorer)"
        "-DMK61_MATH_BACKEND=$($script:State.EnableCoreMath)"
    ) -join ' '
}

function Get-AllCompileFlags {
    param([string]$Profile)
    if (-not (Test-Profile $Profile)) { throw "Unsupported profile: $Profile" }
    return "$($script:Profiles[$Profile].Flags) $(Get-CompileOptionFlags)"
}

function Get-Checkbox {
    param([int]$Value)
    if ($Value -eq 1) { return $script:Glyphs.CheckOn }
    return $script:Glyphs.CheckOff
}

function Get-CompileOptionsSummary {
    return ('{0} FOCAL  {1} TinyBASIC  {2} WBMP  {3} USB  {4} шрифты  {5} USER  {6} CORE math' -f
        (Get-Checkbox $script:State.EnableFocal),
        (Get-Checkbox $script:State.EnableTinyBasic),
        (Get-Checkbox $script:State.EnableWbmp),
        (Get-Checkbox $script:State.EnableUsbScreen),
        (Get-Checkbox $script:State.EnableFonts),
        (Get-Checkbox $script:State.EnableExplorer),
        (Get-Checkbox $script:State.EnableCoreMath))
}

function Get-CompileOptionsDetails {
    $mathText = if ($script:State.EnableCoreMath -eq 1) {
        "$($script:Glyphs.CheckOn) CORE math (MK61_MATH_BACKEND=1)"
    } else {
        "$($script:Glyphs.CheckOff) CORE math (MK61_MATH_BACKEND=0, libm)"
    }
    return @(
        "$(Get-Checkbox $script:State.EnableFocal) FOCAL (MK61_ENABLE_FOCAL)"
        "$(Get-Checkbox $script:State.EnableTinyBasic) TinyBASIC (MK61_ENABLE_TINYBASIC)"
        "$(Get-Checkbox $script:State.EnableWbmp) WBMP viewer (MK61_ENABLE_WBMP_VIEWER)"
        "$(Get-Checkbox $script:State.EnableUsbScreen) USB-экран (MK61_ENABLE_USB_SCREEN)"
        "$(Get-Checkbox $script:State.EnableFonts) расширенные шрифты (MK61_ENABLE_EXTENDED_FONT_SETTINGS)"
        "$(Get-Checkbox $script:State.EnableExplorer) USER → Explorer (MK61_USER_EXPLORER_SHORTCUT)"
        $mathText
    ) -join [Environment]::NewLine
}

function Test-BooleanValue { param([string]$Value) return $Value -eq '0' -or $Value -eq '1' }

function Save-Config {
    Sync-ProfileFromHardware
    $parent = Split-Path -Parent $script:ConfigFile
    if (-not [string]::IsNullOrEmpty($parent)) { [void](New-Item -ItemType Directory -Force -Path $parent) }
    $temporary = "$($script:ConfigFile).tmp"
    $lines = @(
        '# Generated by tools/mk61-firmware.cmd. Safe to edit while the tool is closed.'
        "PLATFORM=$($script:State.Platform)"
        "SCREEN=$($script:State.Screen)"
        "DFU_UTIL_PATH=$($script:State.DfuPath)"
        "STM32_CUBE_PROGRAMMER_PATH=$($script:State.CubeProgrammerPath)"
        "MK61_ENABLE_FOCAL=$($script:State.EnableFocal)"
        "MK61_ENABLE_TINYBASIC=$($script:State.EnableTinyBasic)"
        "MK61_ENABLE_WBMP_VIEWER=$($script:State.EnableWbmp)"
        "MK61_ENABLE_USB_SCREEN=$($script:State.EnableUsbScreen)"
        "MK61_ENABLE_EXTENDED_FONT_SETTINGS=$($script:State.EnableFonts)"
        "MK61_USER_EXPLORER_SHORTCUT=$($script:State.EnableExplorer)"
        "MK61_MATH_BACKEND=$($script:State.EnableCoreMath)"
    )
    [IO.File]::WriteAllLines($temporary, $lines, $script:Utf8NoBom)
    Move-Item -LiteralPath $temporary -Destination $script:ConfigFile -Force
}

function Load-Config {
    if (-not (Test-Path -LiteralPath $script:ConfigFile -PathType Leaf)) {
        if ($script:State.CliProfile) {
            [void](Set-HardwareFromProfile $script:State.Profile)
        } elseif (Test-Path -LiteralPath $script:LegacySelectionFile -PathType Leaf) {
            $legacy = ([IO.File]::ReadAllText($script:LegacySelectionFile)).Trim()
            if (Test-Profile $legacy) {
                $script:State.Profile = $legacy
                [void](Set-HardwareFromProfile $legacy)
            }
        }
        if ((Test-Platform $script:State.Platform) -or (Test-Screen $script:State.Screen)) {
            Save-Config
        }
        return
    }

    $savedProfile = ''
    $savedPlatform = ''
    $savedScreen = ''
    foreach ($line in [IO.File]::ReadAllLines($script:ConfigFile)) {
        $index = $line.IndexOf('=')
        if ($index -lt 1) { continue }
        $key = $line.Substring(0, $index)
        $value = $line.Substring($index + 1).TrimEnd("`r")
        switch ($key) {
            'PROFILE' { if (Test-Profile $value) { $savedProfile = $value } }
            'PLATFORM' { if (Test-Platform $value) { $savedPlatform = $value } }
            'SCREEN' { if (Test-Screen $value) { $savedScreen = $value } }
            'DFU_UTIL_PATH' { $script:State.DfuPath = $value }
            'STM32_CUBE_PROGRAMMER_PATH' { $script:State.CubeProgrammerPath = $value }
            'MK61_ENABLE_FOCAL' { if (Test-BooleanValue $value) { $script:State.EnableFocal = [int]$value } }
            'MK61_ENABLE_TINYBASIC' { if (Test-BooleanValue $value) { $script:State.EnableTinyBasic = [int]$value } }
            'MK61_ENABLE_WBMP_VIEWER' { if (Test-BooleanValue $value) { $script:State.EnableWbmp = [int]$value } }
            'MK61_ENABLE_USB_SCREEN' { if (Test-BooleanValue $value) { $script:State.EnableUsbScreen = [int]$value } }
            'MK61_ENABLE_EXTENDED_FONT_SETTINGS' { if (Test-BooleanValue $value) { $script:State.EnableFonts = [int]$value } }
            'MK61_USER_EXPLORER_SHORTCUT' { if (Test-BooleanValue $value) { $script:State.EnableExplorer = [int]$value } }
            'MK61_MATH_BACKEND' { if (Test-BooleanValue $value) { $script:State.EnableCoreMath = [int]$value } }
        }
    }

    if ($script:State.CliProfile) {
        [void](Set-HardwareFromProfile $script:State.Profile)
        return
    }

    $script:State.Platform = $savedPlatform
    $script:State.Screen = $savedScreen
    if ([string]::IsNullOrEmpty($savedPlatform) -and [string]::IsNullOrEmpty($savedScreen) -and
        (Test-Profile $savedProfile)) {
        $script:State.Profile = $savedProfile
        [void](Set-HardwareFromProfile $savedProfile)
        Sync-ProfileFromHardware
        Save-Config
        return
    }
    Sync-ProfileFromHardware
}

function Set-ConsoleStyle {
    param([string]$Name)
    if (-not $script:UseColor) {
        return
    }
    [Console]::Write("$($script:Escape)$($script:AnsiStyles[$Name])")
}

function Write-Styled {
    param([string]$Text, [string]$Style = 'Window')
    Set-ConsoleStyle $Style
    [Console]::Write($Text)
}

function Update-Layout {
    try {
        $script:ConsoleColumns = [Console]::WindowWidth
        $script:ConsoleRows = [Console]::WindowHeight
    } catch {
        $script:ConsoleColumns = 80
        $script:ConsoleRows = 24
    }
    if ($script:ConsoleColumns -ge 42) {
        $script:WindowWidth = [Math]::Min(84, $script:ConsoleColumns - 4)
        $script:WindowWidth = [Math]::Max(38, $script:WindowWidth)
    } else {
        $script:WindowWidth = [Math]::Max(20, $script:ConsoleColumns - 1)
    }
    $script:TextWidth = [Math]::Max(16, $script:WindowWidth - 4)
    $script:MarginWidth = [Math]::Max(0, [int](($script:ConsoleColumns - $script:WindowWidth) / 2))
}

function Set-RowStart {
    param([int]$Row)
    try { [Console]::SetCursorPosition(0, $Row) } catch {}
    Write-Styled (' ' * $script:MarginWidth) 'Outside'
}

function Complete-Row {
    $used = $script:MarginWidth + $script:WindowWidth
    $rest = [Math]::Max(0, $script:ConsoleColumns - $used)
    Write-Styled (' ' * $rest) 'Outside'
}

function Clip-Text {
    param([string]$Text, [int]$Width)
    if ($null -eq $Text) { return '' }
    if ($Text.Length -le $Width) { return $Text }
    if ($Width -le 1) { return '' }
    return $Text.Substring(0, $Width - 1) + '…'
}

function Clear-View {
    Update-Layout
    Set-ConsoleStyle 'Outside'
    try { [Console]::Clear() } catch {
        [Console]::Write("$($script:Escape)[2J$($script:Escape)[H")
    }
    $script:ProgressVisible = $false
    $script:ProgressTitle = ''
}

function Enter-Tui {
    if ($script:ScreenActive) { return }
    try {
        $script:OriginalForeground = [Console]::ForegroundColor
        $script:OriginalBackground = [Console]::BackgroundColor
        $script:OriginalCursorVisible = [Console]::CursorVisible
    } catch {}
    [Console]::Write("$($script:Escape)[?1049h$($script:Escape)[?25l")
    try { [Console]::CursorVisible = $false } catch {}
    $script:ScreenActive = $true
    Clear-View
}

function Exit-Tui {
    if (-not $script:ScreenActive) { return }
    try {
        [Console]::ForegroundColor = $script:OriginalForeground
        [Console]::BackgroundColor = $script:OriginalBackground
        [Console]::CursorVisible = $script:OriginalCursorVisible
    } catch {}
    [Console]::Write("$($script:Escape)[0m$($script:Escape)[?25h$($script:Escape)[?1049l")
    $script:ScreenActive = $false
}

function Write-TopBorder {
    param([string]$Title)
    $titleText = Clip-Text $Title ($script:WindowWidth - 6)
    $rest = [Math]::Max(0, $script:WindowWidth - $titleText.Length - 5)
    Set-RowStart 0
    Write-Styled '┌─ ' 'Border'
    Write-Styled $titleText 'White'
    Write-Styled (' ' + ('─' * $rest) + '┐') 'Border'
    Complete-Row
}

function Write-BottomBorder {
    param([int]$Row, [string]$Hint)
    $hintText = Clip-Text $Hint ($script:WindowWidth - 6)
    $rest = [Math]::Max(0, $script:WindowWidth - $hintText.Length - 5)
    Set-RowStart $Row
    Write-Styled '└─ ' 'Border'
    Write-Styled $hintText 'Muted'
    Write-Styled (' ' + ('─' * $rest) + '┘') 'Border'
    Complete-Row
}

function Write-BoxLine {
    param([int]$Row, [string]$Text = '', [string]$Style = 'White')
    $shown = Clip-Text $Text $script:TextWidth
    $padding = [Math]::Max(0, $script:TextWidth - $shown.Length)
    Set-RowStart $Row
    Write-Styled '│' 'Border'
    Write-Styled ' ' 'Window'
    Write-Styled $shown $Style
    Write-Styled ((' ' * $padding) + ' ') 'Window'
    Write-Styled '│' 'Border'
    Complete-Row
}

function Get-TextStyle {
    param([string]$Text)
    if ($Text -match 'Ошибка|НЕ НАЙДЕН|не найден|несовместим') { return 'Red' }
    if ($Text -match '^(Платформа|Экран|Оборудование|Профиль):') { return 'Cyan' }
    if ($Text -match '^Ключи:') { return 'Yellow' }
    if ($Text -match '^(Цель|Контроллер|Метод):') { return 'Muted' }
    if ($Text -match '^DFU:') { return 'Yellow' }
    if ($Text -match '^Устройство:.*не проверялось') { return 'Muted' }
    if ($Text -match '^Устройство:|Готово') { return 'Yellow' }
    return 'White'
}

function Split-WrappedText {
    param([string]$Text, [int]$Width)
    $result = New-Object 'System.Collections.Generic.List[string]'
    foreach ($sourceLine in [regex]::Split([string]$Text, "\r?\n")) {
        $line = $sourceLine
        if ($line.Length -eq 0) {
            $result.Add('')
            continue
        }
        while ($line.Length -gt $Width) {
            $split = $line.LastIndexOf(' ', $Width - 1, $Width)
            if ($split -le 0) { $split = $Width }
            $result.Add($line.Substring(0, $split).TrimEnd())
            $line = $line.Substring($split).TrimStart()
        }
        $result.Add($line)
    }
    return $result.ToArray()
}

function Write-BoxText {
    param([int]$StartRow, [string]$Text)
    $lines = @(Split-WrappedText $Text $script:TextWidth)
    for ($index = 0; $index -lt $lines.Count; $index++) {
        Write-BoxLine ($StartRow + $index) $lines[$index] (Get-TextStyle $lines[$index])
    }
    return $lines.Count
}

function Get-MenuStyle {
    param([string]$Label)
    foreach ($prefix in @($script:Glyphs.MenuChoice, $script:Glyphs.MenuOptions, $script:Glyphs.MenuDetect)) {
        if ($Label.StartsWith("$prefix ")) { return 'Cyan' }
    }
    if ($Label.StartsWith("$($script:Glyphs.MenuInstall) ")) { return 'Yellow' }
    if ($Label.StartsWith("$($script:Glyphs.MenuQuit) ")) { return 'Red' }
    return 'White'
}

function Draw-MenuItem {
    param([int]$Index, [int]$Selected, [object[]]$Items)
    $item = $Items[$Index]
    if ($Index -eq $Selected) {
        Write-BoxLine ($script:ListFirstRow + $Index) ("$($script:Glyphs.Selector) " + $item.Label) 'Selected'
    } else {
        Write-BoxLine ($script:ListFirstRow + $Index) ("  " + $item.Label) (Get-MenuStyle $item.Label)
    }
}

function Draw-MenuPage {
    param([string]$Title, [string]$Text, [int]$Selected, [object[]]$Items)
    Clear-View
    Write-TopBorder $Title
    Write-BoxLine 1
    $count = Write-BoxText 2 $Text
    Write-BoxLine (2 + $count)
    $script:ListFirstRow = 3 + $count
    for ($index = 0; $index -lt $Items.Count; $index++) {
        Draw-MenuItem $index $Selected $Items
    }
    Write-BoxLine ($script:ListFirstRow + $Items.Count)
    Write-BottomBorder ($script:ListFirstRow + $Items.Count + 1) '↑↓ выбрать · Enter подтвердить · Esc назад'
}

function Get-MenuInitialIndex {
    param([object[]]$Items, [string]$InitialTag)
    for ($index = 0; $index -lt $Items.Count; $index++) {
        if ($Items[$index].Tag -eq $InitialTag) { return $index }
    }
    return 0
}

function Show-Menu {
    param([string]$Title, [string]$Text, [object[]]$Items, [string]$InitialTag = '')
    $selected = Get-MenuInitialIndex $Items $InitialTag
    Draw-MenuPage $Title $Text $selected $Items
    while ($true) {
        $key = [Console]::ReadKey($true)
        $previous = $selected
        switch ($key.Key) {
            'UpArrow' { $selected--; if ($selected -lt 0) { $selected = $Items.Count - 1 } }
            'DownArrow' { $selected++; if ($selected -ge $Items.Count) { $selected = 0 } }
            'Home' { $selected = 0 }
            'End' { $selected = $Items.Count - 1 }
            'Enter' { return $Items[$selected].Tag }
            'Spacebar' { return $Items[$selected].Tag }
            'Escape' { return $null }
            'Q' { return $null }
        }
        if ([char]::IsDigit($key.KeyChar)) {
            $number = [int][string]$key.KeyChar
            if ($number -ge 1 -and $number -le $Items.Count) { return $Items[$number - 1].Tag }
        }
        if ($selected -ne $previous) {
            Draw-MenuItem $previous $selected $Items
            Draw-MenuItem $selected $selected $Items
        }
    }
}

function Draw-RadioItem {
    param([int]$Index, [int]$Selected, [int]$Current, [object[]]$Items)
    $item = $Items[$Index]
    $marker = $script:Glyphs.RadioOff
    $style = 'Yellow'
    if ($item.State -eq 'disabled') { $marker = $script:Glyphs.RadioDisabled; $style = 'Red' }
    elseif ($Index -eq $Current) { $marker = $script:Glyphs.RadioOn; $style = 'Yellow' }
    $text = "$marker  $($item.Label)"
    if ($Index -eq $Selected) { Write-BoxLine ($script:ListFirstRow + $Index) ("$($script:Glyphs.Selector) " + $text) 'Selected' }
    else { Write-BoxLine ($script:ListFirstRow + $Index) ("  " + $text) $style }
}

function Show-RadioList {
    param([string]$Title, [string]$Text, [object[]]$Items)
    $current = -1
    for ($i = 0; $i -lt $Items.Count; $i++) { if ($Items[$i].State -eq 'on') { $current = $i } }
    $selected = $current
    if ($selected -lt 0 -or $Items[$selected].State -eq 'disabled') {
        $selected = 0
        while ($selected -lt $Items.Count -and $Items[$selected].State -eq 'disabled') { $selected++ }
    }
    if ($selected -ge $Items.Count) { return $null }

    Clear-View
    Write-TopBorder $Title
    Write-BoxLine 1
    $count = Write-BoxText 2 $Text
    Write-BoxLine (2 + $count)
    $script:ListFirstRow = 3 + $count
    for ($i = 0; $i -lt $Items.Count; $i++) { Draw-RadioItem $i $selected $current $Items }
    Write-BoxLine ($script:ListFirstRow + $Items.Count)
    Write-BottomBorder ($script:ListFirstRow + $Items.Count + 1) '↑↓ выбрать · Space отметить · Enter сохранить · Esc назад'

    while ($true) {
        $key = [Console]::ReadKey($true)
        $oldSelected = $selected
        $oldCurrent = $current
        switch ($key.Key) {
            'UpArrow' {
                do { $selected--; if ($selected -lt 0) { $selected = $Items.Count - 1 } }
                while ($Items[$selected].State -eq 'disabled')
            }
            'DownArrow' {
                do { $selected++; if ($selected -ge $Items.Count) { $selected = 0 } }
                while ($Items[$selected].State -eq 'disabled')
            }
            'Home' {
                $selected = 0
                while ($Items[$selected].State -eq 'disabled') { $selected++ }
            }
            'End' {
                $selected = $Items.Count - 1
                while ($Items[$selected].State -eq 'disabled') { $selected-- }
            }
            'Spacebar' { if ($Items[$selected].State -ne 'disabled') { $current = $selected } }
            'Enter' { if ($Items[$selected].State -ne 'disabled') { return $Items[$selected].Tag } }
            'Escape' { return $null }
            'Q' { return $null }
        }
        if ($selected -ne $oldSelected -or $current -ne $oldCurrent) {
            $redraw = @($oldSelected, $oldCurrent, $selected, $current) | Where-Object { $_ -ge 0 } | Select-Object -Unique
            foreach ($index in $redraw) { Draw-RadioItem $index $selected $current $Items }
        }
    }
}

function Draw-CheckItem {
    param([int]$Index, [int]$Selected, [object[]]$Items, [bool[]]$Checked)
    $marker = if ($Checked[$Index]) { $script:Glyphs.CheckOn } else { $script:Glyphs.CheckOff }
    $style = 'Yellow'
    $text = "$marker  $($Items[$Index].Label)"
    if ($Index -eq $Selected) { Write-BoxLine ($script:ListFirstRow + $Index) ("$($script:Glyphs.Selector) " + $text) 'Selected' }
    else { Write-BoxLine ($script:ListFirstRow + $Index) ("  " + $text) $style }
}

function Get-TuiKeyName {
    param([ConsoleKeyInfo]$Key)
    if ($Key.KeyChar -eq ' ') { return 'Spacebar' }
    return [string]$Key.Key
}

function Show-Checklist {
    param([string]$Title, [string]$Text, [object[]]$Items)
    [bool[]]$checked = @($Items | ForEach-Object { $_.State -eq 'on' })
    $selected = 0
    Clear-View
    Write-TopBorder $Title
    Write-BoxLine 1
    $count = Write-BoxText 2 $Text
    Write-BoxLine (2 + $count)
    $script:ListFirstRow = 3 + $count
    for ($i = 0; $i -lt $Items.Count; $i++) { Draw-CheckItem $i $selected $Items $checked }
    Write-BoxLine ($script:ListFirstRow + $Items.Count)
    Write-BottomBorder ($script:ListFirstRow + $Items.Count + 1) '↑↓ выбрать · Space переключить · Enter сохранить · Esc назад'

    while ($true) {
        $key = [Console]::ReadKey($true)
        $keyName = Get-TuiKeyName $key
        $previous = $selected
        switch ($keyName) {
            'UpArrow' { $selected--; if ($selected -lt 0) { $selected = $Items.Count - 1 } }
            'DownArrow' { $selected++; if ($selected -ge $Items.Count) { $selected = 0 } }
            'Home' { $selected = 0 }
            'End' { $selected = $Items.Count - 1 }
            'Spacebar' { $checked[$selected] = -not $checked[$selected]; Draw-CheckItem $selected $selected $Items $checked }
            'X' { $checked[$selected] = -not $checked[$selected]; Draw-CheckItem $selected $selected $Items $checked }
            'Enter' {
                $values = New-Object 'System.Collections.Generic.List[string]'
                for ($i = 0; $i -lt $Items.Count; $i++) { if ($checked[$i]) { $values.Add($Items[$i].Tag) } }
                return [pscustomobject]@{ Cancelled = $false; Values = $values.ToArray() }
            }
            'Escape' { return [pscustomobject]@{ Cancelled = $true; Values = @() } }
            'Q' { return [pscustomobject]@{ Cancelled = $true; Values = @() } }
        }
        if ($selected -ne $previous) {
            Draw-CheckItem $previous $selected $Items $checked
            Draw-CheckItem $selected $selected $Items $checked
        }
    }
}

function Show-YesNo {
    param([string]$Title, [string]$Text)
    $selected = 1
    Clear-View
    Write-TopBorder $Title
    Write-BoxLine 1
    $count = Write-BoxText 2 $Text
    Write-BoxLine (2 + $count)
    $first = 3 + $count
    Write-BoxLine $first '  Да, продолжить' 'White'
    Write-BoxLine ($first + 1) "$($script:Glyphs.Selector) Отмена" 'Selected'
    Write-BoxLine ($first + 2)
    Write-BottomBorder ($first + 3) '←→ выбрать · Enter подтвердить · Esc отменить'
    while ($true) {
        $key = [Console]::ReadKey($true)
        $previous = $selected
        switch ($key.Key) {
            { $_ -in @('UpArrow','DownArrow','LeftArrow','RightArrow') } { $selected = 1 - $selected }
            'Y' { return $true }
            'N' { return $false }
            'Escape' { return $false }
            'Q' { return $false }
            'Enter' { return $selected -eq 0 }
            'Spacebar' { return $selected -eq 0 }
        }
        if ($selected -ne $previous) {
            if ($selected -eq 0) {
                Write-BoxLine $first "$($script:Glyphs.Selector) Да, продолжить" 'Selected'
                Write-BoxLine ($first + 1) '  Отмена' 'White'
            } else {
                Write-BoxLine $first '  Да, продолжить' 'White'
                Write-BoxLine ($first + 1) "$($script:Glyphs.Selector) Отмена" 'Selected'
            }
        }
    }
}

function Show-Message {
    param([string]$Title, [string]$Text)
    Clear-View
    Write-TopBorder $Title
    Write-BoxLine 1
    $count = Write-BoxText 2 $Text
    Write-BoxLine (2 + $count)
    Write-BoxLine (3 + $count) '                         [  OK  ]' 'Selected'
    Write-BoxLine (4 + $count)
    Write-BottomBorder (5 + $count) 'Enter или Esc закрыть'
    while ($true) {
        $key = [Console]::ReadKey($true)
        if ($key.Key -in @('Enter','Escape','Spacebar')) { return }
    }
}

function Draw-InputValue {
    param([int]$Row, [string]$Value)
    $limit = [Math]::Max(8, $script:TextWidth - 7)
    $shown = $Value
    if ($shown.Length -gt $limit) { $shown = '…' + $shown.Substring($shown.Length - $limit + 1) }
    Write-BoxLine $Row ("Путь: $shown" + '█') 'Selected'
}

function Show-InputDialog {
    param([string]$Title, [string]$Text, [string]$Initial = '')
    $value = $Initial
    Clear-View
    Write-TopBorder $Title
    Write-BoxLine 1
    $count = Write-BoxText 2 $Text
    Write-BoxLine (2 + $count)
    $inputRow = 3 + $count
    Draw-InputValue $inputRow $value
    Write-BoxLine ($inputRow + 1)
    Write-BottomBorder ($inputRow + 2) 'Вставьте полный путь · Enter сохранить · Esc пропустить'
    while ($true) {
        $key = [Console]::ReadKey($true)
        switch ($key.Key) {
            'Enter' { return [pscustomobject]@{ Cancelled = $false; Value = $value } }
            'Escape' { return [pscustomobject]@{ Cancelled = $true; Value = '' } }
            'Backspace' { if ($value.Length -gt 0) { $value = $value.Substring(0, $value.Length - 1) } }
            default {
                if (-not [char]::IsControl($key.KeyChar)) { $value += $key.KeyChar }
            }
        }
        Draw-InputValue $inputRow $value
    }
}

function Show-Log {
    param([string]$Title, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Get-Item -LiteralPath $Path).Length -eq 0) {
        Show-Message $Title 'Журнал пуст.'
        return
    }
    $text = [IO.File]::ReadAllText($Path).Replace("`r", "`n")
    $text = [regex]::Replace($text, "$($script:Escape)\[[0-9;?]*[ -/]*[@-~]", '?')
    $lines = @($text -split "`n")
    $visible = [Math]::Min(18, [Math]::Max(6, $script:ConsoleRows - 7))
    $offset = [Math]::Max(0, $lines.Count - $visible)
    while ($true) {
        Clear-View
        Write-TopBorder $Title
        Write-BoxLine 1
        for ($i = 0; $i -lt $visible; $i++) {
            $index = $offset + $i
            if ($index -lt $lines.Count) { Write-BoxLine (2 + $i) $lines[$index] 'White' }
            else { Write-BoxLine (2 + $i) }
        }
        Write-BoxLine (2 + $visible)
        $last = [Math]::Min($lines.Count, $offset + $visible)
        Write-BottomBorder (3 + $visible) "↑↓ прокрутка · $($offset + 1)–$last из $($lines.Count) · Esc закрыть"
        $key = [Console]::ReadKey($true)
        switch ($key.Key) {
            'UpArrow' { if ($offset -gt 0) { $offset-- } }
            'DownArrow' { if ($offset + $visible -lt $lines.Count) { $offset++ } }
            'Home' { $offset = 0 }
            'End' { $offset = [Math]::Max(0, $lines.Count - $visible) }
            { $_ -in @('Enter','Escape','Q') } { return }
        }
    }
}

function Draw-Progress {
    param([string]$Title, [string]$Message, [int]$Percent)
    $Percent = [Math]::Max(0, [Math]::Min(100, $Percent))
    if (-not $script:ProgressVisible -or $script:ProgressTitle -ne $Title) {
        Clear-View
        Write-TopBorder $Title
        Write-BoxLine 1
        Write-BoxLine 2 $Message (Get-TextStyle $Message)
        Write-BoxLine 3
        $script:ProgressVisible = $true
        $script:ProgressTitle = $Title
    } else {
        Write-BoxLine 2 $Message (Get-TextStyle $Message)
    }
    $barWidth = [Math]::Max(12, $script:TextWidth - 7)
    $filled = [int][Math]::Floor($barWidth * $Percent / 100)
    $empty = $barWidth - $filled
    $bar = '[' + ('█' * $filled) + ('░' * $empty) + ('] {0,3}%' -f $Percent)
    Write-BoxLine 4 $bar 'Yellow'
    Write-BoxLine 5
    $hint = if ($Percent -eq 100) { '✓ Готово' }
        elseif ($Message -match '^Ошибка') { '× Ошибка · подробности в журнале' }
        else { 'Операция выполняется…' }
    Write-BottomBorder 6 $hint
}

function Resolve-Executable {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($Command)) { return '' }
    if (Test-Path -LiteralPath $Command -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Command).Path
    }
    $resolved = Get-Command $Command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $resolved) { return '' }
    return $resolved.Source
}

function Test-CommandAvailable {
    param([string]$Command)
    return -not [string]::IsNullOrEmpty((Resolve-Executable $Command))
}

function Invoke-NativeCapture {
    param([string]$Executable, [string[]]$Arguments = @())
    $resolved = Resolve-Executable $Executable
    if ([string]::IsNullOrEmpty($resolved)) {
        return [pscustomobject]@{ ExitCode = 127; Output = "Executable not found: $Executable" }
    }
    try {
        $output = & $resolved @Arguments 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) { $exitCode = if ($?) { 0 } else { 1 } }
        return [pscustomobject]@{ ExitCode = [int]$exitCode; Output = [string]$output }
    } catch {
        return [pscustomobject]@{ ExitCode = 1; Output = $_.Exception.Message }
    }
}

function Get-LogPercent {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return -1 }
    try { $text = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop } catch { return -1 }
    if ($null -eq $text) { return -1 }
    $matches = [regex]::Matches([string]$text, '(\d+)%')
    if ($matches.Count -eq 0) { return -1 }
    return [int]$matches[$matches.Count - 1].Groups[1].Value
}

function Invoke-ExternalWithProgress {
    param(
        [string]$Title,
        [string]$Message,
        [string]$LogFile,
        [string]$Mode,
        [string]$Executable,
        [string[]]$Arguments,
        [switch]$Append
    )
    $resolved = Resolve-Executable $Executable
    $parent = Split-Path -Parent $LogFile
    if (-not [string]::IsNullOrEmpty($parent)) { [void](New-Item -ItemType Directory -Force -Path $parent) }
    if (-not $Append) { [IO.File]::WriteAllText($LogFile, '', $script:Utf8NoBom) }
    if ([string]::IsNullOrEmpty($resolved)) {
        [IO.File]::AppendAllText($LogFile, "Executable not found: $Executable`n", $script:Utf8NoBom)
        return $false
    }

    $worker = {
        param([string]$NativeExecutable, [object[]]$NativeArguments, [string]$NativeLog, [bool]$AppendLog)
        $ErrorActionPreference = 'Continue'
        if ($AppendLog) { & $NativeExecutable @NativeArguments *>> $NativeLog }
        else { & $NativeExecutable @NativeArguments *> $NativeLog }
        $successful = $?
        $nativeExit = $LASTEXITCODE
        if ($null -eq $nativeExit) { if ($successful) { return 0 } else { return 1 } }
        return [int]$nativeExit
    }

    try {
        $script:ActiveJob = Start-Job -ScriptBlock $worker -ArgumentList @(
            $resolved, [object[]]$Arguments, $LogFile, [bool]$Append)
    } catch {
        [IO.File]::AppendAllText($LogFile, $_.Exception.Message + "`n", $script:Utf8NoBom)
        return $false
    }

    $percent = 5
    if ($script:State.Interactive) { Draw-Progress $Title $Message $percent }
    else { [Console]::Error.WriteLine("$Message…") }

    while ($script:ActiveJob.State -in @('NotStarted','Running')) {
        if ($Mode -eq 'measured') {
            $measured = Get-LogPercent $LogFile
            if ($measured -ge 0 -and $measured -le 95) { $percent = $measured }
        } elseif ($percent -lt 90) {
            $percent = [Math]::Min(90, $percent + 2)
        }
        if ($script:State.Interactive) { Draw-Progress $Title $Message $percent }
        Start-Sleep -Milliseconds 200
    }

    [void](Wait-Job -Job $script:ActiveJob)
    $result = @(Receive-Job -Job $script:ActiveJob -ErrorAction SilentlyContinue)
    $exitCode = 1
    if ($result.Count -gt 0) {
        try { $exitCode = [int]$result[$result.Count - 1] } catch { $exitCode = 1 }
    }
    Remove-Job -Job $script:ActiveJob -Force -ErrorAction SilentlyContinue
    $script:ActiveJob = $null

    if ($script:State.Interactive) {
        if ($exitCode -eq 0) { Draw-Progress $Title 'Готово' 100 }
        else { Draw-Progress $Title 'Ошибка — подробности в журнале' $percent }
        Start-Sleep -Milliseconds 350
    }
    return $exitCode -eq 0
}

function Test-ArduinoCoreReady {
    if (-not (Test-CommandAvailable $script:ArduinoCli)) { return $false }
    $result = Invoke-NativeCapture $script:ArduinoCli @('core','list')
    if ($result.ExitCode -ne 0) { return $false }
    return $result.Output -match "(?m)^STMicroelectronics:stm32\s+$([regex]::Escape($script:Stm32CoreVersion))(\s|$)"
}

function Test-ArduinoLibrariesReady {
    if (-not (Test-CommandAvailable $script:ArduinoCli)) { return $false }
    $result = Invoke-NativeCapture $script:ArduinoCli @('lib','list')
    if ($result.ExitCode -ne 0) { return $false }
    return ($result.Output -match '(?m)^LiquidCrystal\s+1\.0\.7(\s|$)') -and
        ($result.Output -match '(?m)^STM32duino RTC\s+1\.9\.0(\s|$)')
}

function Test-BuildDependenciesReady {
    return (Test-ArduinoCoreReady) -and (Test-ArduinoLibrariesReady)
}

function Get-DependencyReport {
    $lines = New-Object 'System.Collections.Generic.List[string]'
    if (Test-CommandAvailable $script:ArduinoCli) {
        $version = Invoke-NativeCapture $script:ArduinoCli @('version')
        $firstLine = @($version.Output -split "\r?\n")[0]
        $lines.Add("arduino-cli: $firstLine")
    } else {
        $lines.Add('arduino-cli: НЕ НАЙДЕН')
    }
    if (Test-ArduinoCoreReady) { $lines.Add("STM32 Arduino Core: $($script:Stm32CoreVersion)") }
    else { $lines.Add("STM32 Arduino Core: нужен $($script:Stm32CoreVersion)") }
    if (Test-ArduinoLibrariesReady) {
        $lines.Add('LiquidCrystal: 1.0.7')
        $lines.Add('STM32duino RTC: 1.9.0')
    } else {
        $lines.Add('Библиотеки: нужны LiquidCrystal 1.0.7 и STM32duino RTC 1.9.0')
    }
    if ($script:IsWindowsHost) {
        if (Find-Stm32CubeProgrammer) {
            $lines.Add("DFU uploader: arduino-cli → $script:CubeProgrammerExecutable")
        } else {
            $lines.Add('DFU uploader: нужен STM32CubeProgrammer')
        }
    } elseif (Find-DfuUtil) {
        $lines.Add("DFU uploader: $script:DfuExecutable")
    } else {
        $lines.Add('DFU uploader: dfu-util не найден (появится вместе с STM32 Core)')
    }
    return $lines -join [Environment]::NewLine
}

function Install-ArduinoDependencies {
    if (-not (Test-CommandAvailable $script:ArduinoCli)) {
        if ($script:State.Interactive) {
            Show-Message 'Зависимости' 'arduino-cli не найден. Сначала установите Arduino CLI, затем снова запустите это меню.'
        } else { [Console]::Error.WriteLine('Error: arduino-cli is not installed.') }
        return $false
    }
    $logParent = Split-Path -Parent $script:LastLog
    if (-not [string]::IsNullOrEmpty($logParent)) {
        [void](New-Item -ItemType Directory -Force -Path $logParent)
    }
    $steps = @(
        [pscustomobject]@{ Message = 'Обновляю индекс STM32 Core'; Args = @('core','update-index','--additional-urls',$script:Stm32PackageUrl) }
        [pscustomobject]@{ Message = 'Устанавливаю STM32 Arduino Core'; Args = @('core','install',"STMicroelectronics:stm32@$($script:Stm32CoreVersion)",'--additional-urls',$script:Stm32PackageUrl) }
        [pscustomobject]@{ Message = 'Обновляю индекс библиотек'; Args = @('lib','update-index') }
        [pscustomobject]@{ Message = 'Устанавливаю LiquidCrystal 1.0.7'; Args = @('lib','install','LiquidCrystal@1.0.7') }
        [pscustomobject]@{ Message = 'Устанавливаю STM32duino RTC 1.9.0'; Args = @('lib','install','STM32duino RTC@1.9.0') }
    )
    [IO.File]::WriteAllText($script:LastLog, '', $script:Utf8NoBom)
    foreach ($step in $steps) {
        if (-not (Invoke-ExternalWithProgress 'Зависимости' $step.Message $script:LastLog 'indeterminate' `
            $script:ArduinoCli $step.Args -Append)) {
            if ($script:State.Interactive) { Show-Log 'Ошибка установки' $script:LastLog }
            return $false
        }
    }
    if ($script:State.Interactive) {
        Show-Message 'Зависимости' 'STM32 Core 2.12.0 и библиотеки установлены.'
    }
    return $true
}

$script:DfuExecutable = ''
$script:CubeProgrammerExecutable = ''

function Set-Stm32CubeProgrammer {
    param([string]$Candidate)
    $resolved = Resolve-Executable $Candidate
    if ([string]::IsNullOrEmpty($resolved) -or
        [IO.Path]::GetFileName($resolved) -notmatch '^(?i:STM32_Programmer_CLI\.exe)$') { return $false }
    $script:CubeProgrammerExecutable = $resolved

    # The STM32 Core upload recipe starts its helper in a child process and
    # resolves STM32_Programmer_CLI.exe through PATH.  This also makes a path
    # selected by the user available to that helper.
    $directory = Split-Path -Parent $resolved
    $processPath = [Environment]::GetEnvironmentVariable('Path', 'Process')
    $entries = if ([string]::IsNullOrEmpty($processPath)) { @() } else { @($processPath -split [regex]::Escape([string][IO.Path]::PathSeparator)) }
    if (-not @($entries | Where-Object { $_.TrimEnd('\','/') -ieq $directory.TrimEnd('\','/') }).Count) {
        [Environment]::SetEnvironmentVariable('Path', "$directory$([IO.Path]::PathSeparator)$processPath", 'Process')
    }
    return $true
}

function Find-Stm32CubeProgrammer {
    if (-not [string]::IsNullOrEmpty($script:CubeProgrammerExecutable) -and
        (Test-Path -LiteralPath $script:CubeProgrammerExecutable -PathType Leaf)) { return $true }
    $script:CubeProgrammerExecutable = ''
    $override = [Environment]::GetEnvironmentVariable('MK61_STM32_PROGRAMMER')
    if (-not [string]::IsNullOrWhiteSpace($override) -and (Set-Stm32CubeProgrammer $override)) { return $true }
    if (-not [string]::IsNullOrWhiteSpace($script:State.CubeProgrammerPath) -and
        (Set-Stm32CubeProgrammer $script:State.CubeProgrammerPath)) { return $true }
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    $candidates.Add('STM32_Programmer_CLI.exe')
    foreach ($rootName in @('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)')) {
        $root = [Environment]::GetEnvironmentVariable($rootName)
        if (-not [string]::IsNullOrWhiteSpace($root)) {
            $candidates.Add((Join-Path $root 'STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe'))
        }
    }
    foreach ($candidate in $candidates) {
        if (Set-Stm32CubeProgrammer $candidate) { return $true }
    }
    return $false
}

function Configure-Stm32CubeProgrammer {
    if (Find-Stm32CubeProgrammer) {
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable('MK61_STM32_PROGRAMMER')) -and
            $script:State.CubeProgrammerPath -ne $script:CubeProgrammerExecutable) {
            $script:State.CubeProgrammerPath = $script:CubeProgrammerExecutable
            Save-Config
        }
        return $true
    }

    $help = "STM32CubeProgrammer не найден. Укажите полный путь к STM32_Programmer_CLI.exe.`n`nОбычно: C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe."
    while ($true) {
        $answer = Show-InputDialog 'DFU uploader' $help
        if ($answer.Cancelled -or [string]::IsNullOrWhiteSpace($answer.Value)) { return $false }
        $expanded = Expand-EnteredPath $answer.Value
        if (Set-Stm32CubeProgrammer $expanded) {
            $script:State.CubeProgrammerPath = $script:CubeProgrammerExecutable
            Save-Config
            Show-Message 'DFU uploader' "STM32CubeProgrammer найден и сохранён:`n`n$($script:State.CubeProgrammerPath)"
            return $true
        }
        Show-Message 'DFU uploader' "Ожидался файл STM32_Programmer_CLI.exe:`n`n$expanded"
    }
}

function Get-DfuLocationLabel {
    param([string]$Executable)
    $match = [regex]::Match($Executable, 'STM32Tools[\\/](?<version>[^\\/]+)')
    if ($match.Success) {
        $hostName = if ($Executable -match '[\\/]win[\\/]') { 'Windows' }
            elseif ($Executable -match '[\\/]macosx[\\/]') { 'macOS' }
            elseif ($Executable -match '[\\/]linux') { 'Linux' }
            elseif ($script:IsWindowsHost) { 'Windows' }
            elseif ($script:IsMacHost) { 'macOS' }
            else { 'Linux' }
        return "Arduino STM32Tools $($match.Groups['version'].Value) · $hostName"
    }
    if ($Executable -match '(homebrew|linuxbrew|\.linuxbrew)') {
        if ($Executable -match '(linuxbrew|\.linuxbrew)') { return 'Linuxbrew' }
        return 'Homebrew'
    }
    return $Executable
}

function Set-DfuExecutable {
    param([string]$Candidate)
    $resolved = Resolve-Executable $Candidate
    if ([string]::IsNullOrEmpty($resolved)) { return $false }
    $name = [IO.Path]::GetFileName($resolved)
    if ($name -notmatch '^(?i:dfu-util(?:\.exe|\.sh)?)$') { return $false }
    $script:DfuExecutable = $resolved
    $script:State.DfuStatus = "найден · $(Get-DfuLocationLabel $resolved)"
    return $true
}

function Find-DfuUtil {
    if (-not [string]::IsNullOrEmpty($script:DfuExecutable) -and
        (Test-Path -LiteralPath $script:DfuExecutable -PathType Leaf)) { return $true }
    $script:DfuExecutable = ''
    $script:State.DfuStatus = 'не найден'

    $override = [Environment]::GetEnvironmentVariable('MK61_DFU_UTIL')
    if (-not [string]::IsNullOrWhiteSpace($override) -and (Set-DfuExecutable $override)) { return $true }
    if (-not [string]::IsNullOrWhiteSpace($script:State.DfuPath) -and (Set-DfuExecutable $script:State.DfuPath)) { return $true }
    if (Set-DfuExecutable 'dfu-util') { return $true }
    if (Set-DfuExecutable 'dfu-util.exe') { return $true }

    $fixed = @(
        '/opt/homebrew/bin/dfu-util'
        '/opt/homebrew/opt/dfu-util/bin/dfu-util'
        '/usr/local/bin/dfu-util'
        '/usr/local/opt/dfu-util/bin/dfu-util'
        '/opt/local/bin/dfu-util'
        '/usr/bin/dfu-util'
        '/bin/dfu-util'
        '/home/linuxbrew/.linuxbrew/bin/dfu-util'
        '/home/linuxbrew/.linuxbrew/opt/dfu-util/bin/dfu-util'
        'C:\ProgramData\chocolatey\bin\dfu-util.exe'
    )
    $userHome = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    if (-not [string]::IsNullOrEmpty($userHome)) {
        $fixed += (Join-Path $userHome 'scoop/shims/dfu-util.exe')
        $fixed += (Join-Path $userHome '.linuxbrew/bin/dfu-util')
        $fixed += (Join-Path $userHome '.linuxbrew/opt/dfu-util/bin/dfu-util')
    }
    foreach ($candidate in $fixed) { if (Set-DfuExecutable $candidate) { return $true } }

    $patterns = New-Object 'System.Collections.Generic.List[string]'
    if (-not [string]::IsNullOrEmpty($env:LOCALAPPDATA)) {
        $patterns.Add((Join-Path $env:LOCALAPPDATA 'Arduino*/packages/STMicroelectronics/tools/STM32Tools/*/win/dfu-util.exe'))
    }
    if (-not [string]::IsNullOrEmpty($userHome)) {
        foreach ($relative in @(
            'AppData/Local/Arduino*/packages/STMicroelectronics/tools/STM32Tools/*/win/dfu-util.exe'
            '.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/win/dfu-util.exe'
            'Library/Arduino*/packages/STMicroelectronics/tools/STM32Tools/*/macosx/dfu-util'
            'Library/Arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh'
            '.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh'
            '.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/dfu-util'
            '.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util'
            '.local/share/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/dfu-util'
            '.local/share/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util'
            '.var/app/*/data/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh'
            '.var/app/*/data/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util'
            'snap/arduino*/current/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh'
            'snap/arduino*/current/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util'
        )) { $patterns.Add((Join-Path $userHome $relative)) }
    }

    $matches = New-Object 'System.Collections.Generic.List[string]'
    foreach ($pattern in $patterns) {
        try {
            foreach ($file in @(Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue)) {
                $matches.Add($file.FullName)
            }
        } catch {}
    }
    foreach ($candidate in @($matches | Sort-Object)) {
        [void](Set-DfuExecutable $candidate)
    }
    if (-not [string]::IsNullOrEmpty($script:DfuExecutable)) { return $true }
    return $false
}

function Expand-EnteredPath {
    param([string]$Path)
    $expanded = [Environment]::ExpandEnvironmentVariables($Path.Trim())
    if ($expanded.StartsWith('~/') -or $expanded.StartsWith('~\')) {
        $userHomePath = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
        $expanded = Join-Path $userHomePath $expanded.Substring(2)
    }
    return $expanded
}

function Configure-DfuUtil {
    if (Find-DfuUtil) {
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable('MK61_DFU_UTIL')) -and
            $script:State.DfuPath -ne $script:DfuExecutable) {
            $script:State.DfuPath = $script:DfuExecutable
            Save-Config
        }
        return $true
    }

    $help = if ($script:IsWindowsHost) {
        "Утилита dfu-util не найдена. Укажите полный путь к исполняемому файлу.`n`nWindows: %LOCALAPPDATA%\Arduino15\packages\STMicroelectronics\tools\STM32Tools\<version>\win\dfu-util.exe. Также проверяются PATH, Scoop и Chocolatey."
    } elseif ($script:IsMacHost) {
        "Утилита dfu-util не найдена. Укажите полный путь к исполняемому файлу.`n`nmacOS: /opt/homebrew/bin/dfu-util, /usr/local/bin/dfu-util или ~/Library/Arduino15/packages/STMicroelectronics/tools/STM32Tools/<version>/macosx/dfu-util."
    } else {
        "Утилита dfu-util не найдена. Укажите полный путь к исполняемому файлу.`n`nLinux: /usr/bin/dfu-util, /usr/local/bin/dfu-util или ~/.arduino15/packages/STMicroelectronics/tools/STM32Tools/<version>/linux/<arch>/dfu-util."
    }
    while ($true) {
        $answer = Show-InputDialog 'DFU uploader' $help
        if ($answer.Cancelled -or [string]::IsNullOrWhiteSpace($answer.Value)) { return $false }
        $expanded = Expand-EnteredPath $answer.Value
        if (Set-DfuExecutable $expanded) {
            $script:State.DfuPath = $script:DfuExecutable
            Save-Config
            Show-Message 'DFU uploader' "dfu-util найден и сохранён:`n`n$($script:State.DfuPath)"
            return $true
        }
        Show-Message 'DFU uploader' "Это не исполняемый dfu-util или dfu-util.exe:`n`n$expanded"
    }
}

function Configure-DfuUploader {
    if ($script:IsWindowsHost) {
        $hasCli = Test-CommandAvailable $script:ArduinoCli
        $hasProgrammer = Configure-Stm32CubeProgrammer
        if ($hasCli -and $hasProgrammer) {
            $script:State.DfuStatus = 'Arduino CLI · STM32CubeProgrammer'
            return $true
        }
        if (-not $hasCli -and -not $hasProgrammer) { $script:State.DfuStatus = 'нужны arduino-cli и STM32CubeProgrammer' }
        elseif (-not $hasCli) { $script:State.DfuStatus = 'arduino-cli не найден' }
        else { $script:State.DfuStatus = 'STM32CubeProgrammer не найден' }
        return $false
    }
    return Configure-DfuUtil
}

function Get-DfuListing {
    if (-not (Find-DfuUtil)) { return '' }
    $result = Invoke-NativeCapture $script:DfuExecutable @('-l')
    return $result.Output
}

function Get-ObjectPropertyValue {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Test-DfuHardwareId {
    param([string]$InstanceId)
    return -not [string]::IsNullOrWhiteSpace($InstanceId) -and
        $InstanceId -match '(?i)VID_0483&PID_DF11'
}

function Get-WindowsDfuDevices {
    if (-not $script:IsWindowsHost) { return @() }
    $candidates = @()
    $enumerated = $false

    if ($null -ne (Get-Command Get-PnpDevice -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
        try {
            $candidates = @(Get-PnpDevice -PresentOnly -ErrorAction Stop)
            $enumerated = $true
        } catch {}
    }
    if (-not $enumerated -and
        $null -ne (Get-Command Get-CimInstance -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
        try {
            $candidates = @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop)
            $enumerated = $true
        } catch {}
    }
    if (-not $enumerated -and
        $null -ne (Get-Command Get-WmiObject -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
        try {
            $candidates = @(Get-WmiObject -Class Win32_PnPEntity -ErrorAction Stop)
            $enumerated = $true
        } catch {}
    }

    $found = New-Object 'System.Collections.Generic.List[object]'
    $seen = @{}
    foreach ($device in $candidates) {
        $instanceId = [string](Get-ObjectPropertyValue $device 'InstanceId')
        if ([string]::IsNullOrEmpty($instanceId)) {
            $instanceId = [string](Get-ObjectPropertyValue $device 'PNPDeviceID')
        }
        if (-not (Test-DfuHardwareId $instanceId) -or $seen.ContainsKey($instanceId)) { continue }
        $present = Get-ObjectPropertyValue $device 'Present'
        if ($null -ne $present -and -not [bool]$present) { continue }
        $errorCode = Get-ObjectPropertyValue $device 'ConfigManagerErrorCode'
        if ($null -ne $errorCode -and [int]$errorCode -eq 45) { continue }
        $name = [string](Get-ObjectPropertyValue $device 'FriendlyName')
        if ([string]::IsNullOrWhiteSpace($name)) { $name = [string](Get-ObjectPropertyValue $device 'Name') }
        if ([string]::IsNullOrWhiteSpace($name)) { $name = 'STM32 BOOTLOADER' }
        $seen[$instanceId] = $true
        $found.Add([pscustomobject]@{
            InstanceId = $instanceId
            Name = $name
            Status = [string](Get-ObjectPropertyValue $device 'Status')
        })
    }
    return $found.ToArray()
}

function Test-DfuPresent {
    if ($script:IsWindowsHost) {
        return @(Get-WindowsDfuDevices).Count -gt 0
    }
    $listing = Get-DfuListing
    return $listing -match '(?i)(\[0483:df11\]|0483:df11)'
}

function Get-CdcPorts {
    $ports = New-Object 'System.Collections.Generic.List[string]'
    if (-not (Test-CommandAvailable $script:ArduinoCli)) { return $ports.ToArray() }
    $result = Invoke-NativeCapture $script:ArduinoCli @('board','list','--format','json')
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Output)) { return $ports.ToArray() }
    try { $data = $result.Output | ConvertFrom-Json } catch { return $ports.ToArray() }
    $detectedPorts = Get-ObjectPropertyValue $data 'detected_ports'
    foreach ($entry in @($detectedPorts)) {
        $port = Get-ObjectPropertyValue $entry 'port'
        if ($null -eq $port) { continue }
        $properties = Get-ObjectPropertyValue $port 'properties'
        $vendorId = [string](Get-ObjectPropertyValue $properties 'vid')
        $productId = [string](Get-ObjectPropertyValue $properties 'pid')
        $address = [string](Get-ObjectPropertyValue $port 'address')
        $vendorId = $vendorId -replace '^0[xX]', ''
        $productId = $productId -replace '^0[xX]', ''
        if ($vendorId -ieq '0483' -and $productId -ieq '5740' -and -not [string]::IsNullOrEmpty($address)) {
            $ports.Add($address)
        }
    }
    return $ports.ToArray()
}

function ConvertTo-NativeCommandLine {
    param([string[]]$Arguments)
    $quoted = foreach ($argument in $Arguments) {
        if ($argument -notmatch '[\s"]') { $argument }
        else { '"' + ($argument -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"' }
    }
    return $quoted -join ' '
}

function New-NativeProcessStartInfo {
    param([string]$Executable, [string[]]$Arguments)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = Resolve-Executable $Executable
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    if ($null -ne $info.PSObject.Properties['ArgumentList']) {
        foreach ($argument in $Arguments) { [void]$info.ArgumentList.Add($argument) }
    } else {
        $info.Arguments = ConvertTo-NativeCommandLine $Arguments
    }
    return $info
}

function Invoke-MonitorExchange {
    param([string]$Port, [string]$Command)
    if (-not (Test-CommandAvailable $script:ArduinoCli)) { return '' }
    $info = New-NativeProcessStartInfo $script:ArduinoCli @(
        'monitor','--quiet','--port',$Port,'--config','baudrate=115200')
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        Start-Sleep -Milliseconds 150
        $process.StandardInput.WriteLine($Command)
        $process.StandardInput.Flush()
        Start-Sleep -Milliseconds 1000
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(4000)) { $process.Kill() }
        $process.WaitForExit()
        return ([string]$stdout.Result) + ([string]$stderr.Result)
    } catch {
        try { if (-not $process.HasExited) { $process.Kill() } } catch {}
        return ''
    } finally {
        $process.Dispose()
    }
}

function Get-RecognizedProfile {
    param([string]$VersionText)
    if ($VersionText -match 'MK61s-Classic-V2') { return 'classic-v2' }
    if ($VersionText -match 'MK61s-Classic-V3') { return 'classic-v3' }
    if ($VersionText -match 'MK61s-40th') { return '40th' }
    return ''
}

function Detect-Device {
    $script:State.DetectedPort = ''
    $script:State.DetectedVersion = ''
    if ($script:IsWindowsHost) {
        $dfuDevices = @(Get-WindowsDfuDevices)
        if ($dfuDevices.Count -gt 0) {
            $script:State.DeviceStatus = "STM32 DFU 0483:df11 · Windows · $($dfuDevices[0].Name)"
            return $true
        }
    } elseif (Test-DfuPresent) {
        $script:State.DeviceStatus = 'STM32 DFU 0483:df11 · готов к загрузке'
        return $true
    }
    foreach ($port in @(Get-CdcPorts)) {
        if ([string]::IsNullOrWhiteSpace($port)) { continue }
        $response = Invoke-MonitorExchange $port 'ver'
        if ($response -notmatch 'MK61s') { continue }
        $script:State.DetectedPort = $port
        $lines = @($response -split "\r?\n" | Where-Object { $_ -match 'MK61s' })
        if ($lines.Count -gt 0) { $script:State.DetectedVersion = $lines[$lines.Count - 1] }
        $profile = Get-RecognizedProfile $response
        if (-not [string]::IsNullOrEmpty($profile)) {
            $script:State.Profile = $profile
            [void](Set-HardwareFromProfile $profile)
            Save-Config
            $script:State.DeviceStatus = "MK61s на $port · $(Get-ProfileLabel $profile)"
        } else {
            $script:State.DeviceStatus = "MK61s на $port · mini-профиль не кодируется в ver"
        }
        return $true
    }
    $script:State.DeviceStatus = 'устройство не найдено'
    return $false
}

function Choose-Platform {
    $items = foreach ($id in $script:PlatformLabels.Keys) {
        [pscustomobject]@{
            Tag = $id
            Label = $script:PlatformLabels[$id]
            State = if ($script:State.Platform -eq $id) { 'on' } else { 'off' }
        }
    }
    $chosen = Show-RadioList 'Платформа' 'Выберите ревизию платы. Экран выбирается отдельно:' @($items)
    if ([string]::IsNullOrEmpty($chosen)) { return $false }
    $script:State.Platform = $chosen
    Sync-ProfileFromHardware
    Save-Config
    return $true
}

function Choose-Screen {
    $items = foreach ($id in $script:ScreenLabels.Keys) {
        $state = 'off'
        if ((Test-Platform $script:State.Platform) -and
            -not (Test-HardwareCompatible $script:State.Platform $id)) { $state = 'disabled' }
        elseif ($script:State.Screen -eq $id) { $state = 'on' }
        [pscustomobject]@{ Tag = $id; Label = $script:ScreenLabels[$id]; State = $state }
    }
    $chosen = Show-RadioList 'Экран' "Выберите дисплей. Символ $($script:Glyphs.RadioDisabled) означает, что экран не совместим с выбранной платформой:" @($items)
    if ([string]::IsNullOrEmpty($chosen)) { return $false }
    if ((Test-Platform $script:State.Platform) -and
        -not (Test-HardwareCompatible $script:State.Platform $chosen)) {
        Show-Message 'Несовместимая пара' "$(Get-PlatformLabel $script:State.Platform) не поддерживает $(Get-ScreenLabel $chosen)."
        return $false
    }
    $script:State.Screen = $chosen
    Sync-ProfileFromHardware
    Save-Config
    return $true
}

function Choose-CompileOptions {
    $items = @(
        [pscustomobject]@{ Tag = 'focal'; Label = 'FOCAL · MK61_ENABLE_FOCAL'; State = if ($script:State.EnableFocal) { 'on' } else { 'off' } }
        [pscustomobject]@{ Tag = 'tinybasic'; Label = 'TinyBASIC · MK61_ENABLE_TINYBASIC'; State = if ($script:State.EnableTinyBasic) { 'on' } else { 'off' } }
        [pscustomobject]@{ Tag = 'wbmp'; Label = 'WBMP viewer · MK61_ENABLE_WBMP_VIEWER'; State = if ($script:State.EnableWbmp) { 'on' } else { 'off' } }
        [pscustomobject]@{ Tag = 'usb_screen'; Label = 'USB-экран · MK61_ENABLE_USB_SCREEN'; State = if ($script:State.EnableUsbScreen) { 'on' } else { 'off' } }
        [pscustomobject]@{ Tag = 'fonts'; Label = 'Расширенные настройки шрифта'; State = if ($script:State.EnableFonts) { 'on' } else { 'off' } }
        [pscustomobject]@{ Tag = 'explorer'; Label = 'Клавиша USER открывает Explorer'; State = if ($script:State.EnableExplorer) { 'on' } else { 'off' } }
        [pscustomobject]@{ Tag = 'core_math'; Label = 'Математика CORE вместо libm'; State = if ($script:State.EnableCoreMath) { 'on' } else { 'off' } }
    )
    $result = Show-Checklist 'Ключи компиляции' `
        'Пробелом включайте и выключайте независимые функции. Все значения явно передаются Arduino CLI как -Dключи:' $items
    if ($result.Cancelled) { return $false }
    $script:State.EnableFocal = [int]($result.Values -contains 'focal')
    $script:State.EnableTinyBasic = [int]($result.Values -contains 'tinybasic')
    $script:State.EnableWbmp = [int]($result.Values -contains 'wbmp')
    $script:State.EnableUsbScreen = [int]($result.Values -contains 'usb_screen')
    $script:State.EnableFonts = [int]($result.Values -contains 'fonts')
    $script:State.EnableExplorer = [int]($result.Values -contains 'explorer')
    $script:State.EnableCoreMath = [int]($result.Values -contains 'core_math')
    Save-Config
    return $true
}

function Ensure-HardwareProfile {
    if (-not (Test-Platform $script:State.Platform)) {
        if ($script:State.Interactive) { if (-not (Choose-Platform)) { return $false } }
        else { [Console]::Error.WriteLine('Error: select hardware with --profile ID.'); return $false }
    }
    if (-not (Test-Screen $script:State.Screen)) {
        if ($script:State.Interactive) { if (-not (Choose-Screen)) { return $false } }
        else { [Console]::Error.WriteLine('Error: select hardware with --profile ID.'); return $false }
    }
    Sync-ProfileFromHardware
    if (Test-Profile $script:State.Profile) { return $true }
    if ($script:State.Interactive) {
        Show-Message 'Несовместимое оборудование' "Платформа: $(Get-PlatformLabel $script:State.Platform)`nЭкран: $(Get-ScreenLabel $script:State.Screen)`n`nВыберите совместимый экран."
        if (-not (Choose-Screen)) { return $false }
        Sync-ProfileFromHardware
        return Test-Profile $script:State.Profile
    }
    [Console]::Error.WriteLine('Error: incompatible platform/screen selection.')
    return $false
}

function Get-FlagsSignature {
    param([string]$Flags)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Flags)
        $hash = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hash).Replace('-', '').Substring(0, 12).ToLowerInvariant())
    } finally { $sha.Dispose() }
}

function Write-LastLog {
    param([string]$Text, [switch]$Append)
    $parent = Split-Path -Parent $script:LastLog
    if (-not [string]::IsNullOrEmpty($parent)) { [void](New-Item -ItemType Directory -Force -Path $parent) }
    if ($Append) { [IO.File]::AppendAllText($script:LastLog, $Text + [Environment]::NewLine, $script:Utf8NoBom) }
    else { [IO.File]::WriteAllText($script:LastLog, $Text + [Environment]::NewLine, $script:Utf8NoBom) }
}

function Show-LastLogTail {
    param([int]$Count = 60)
    if (-not (Test-Path -LiteralPath $script:LastLog -PathType Leaf)) { return }
    foreach ($line in @(Get-Content -LiteralPath $script:LastLog -Tail $Count)) { [Console]::Error.WriteLine($line) }
}

function Build-Selected {
    if (-not (Ensure-HardwareProfile)) { return $false }
    if (-not (Test-BuildDependenciesReady)) {
        $report = Get-DependencyReport
        if ($script:State.Interactive) { Show-Message 'Не хватает зависимостей' $report }
        else { [Console]::Error.WriteLine($report) }
        return $false
    }

    $profile = $script:State.Profile
    $flags = Get-AllCompileFlags $profile
    $signature = Get-FlagsSignature $flags
    $sketchProfileRoot = Join-Path $script:BuildRoot "sketch/$profile"
    $sketchDir = Join-Path $sketchProfileRoot 'mk61s-M'
    $buildDir = Join-Path $script:BuildRoot "build/$profile-$signature"
    $artifact = Join-Path $script:OutputDir $script:Profiles[$profile].Artifact
    try {
        if (Test-Path -LiteralPath $sketchProfileRoot) { Remove-Item -LiteralPath $sketchProfileRoot -Recurse -Force }
        [void](New-Item -ItemType Directory -Force -Path $sketchDir)
        [void](New-Item -ItemType Directory -Force -Path $buildDir)
        [void](New-Item -ItemType Directory -Force -Path $script:OutputDir)
        Copy-Item -Path (Join-Path $script:ProjectRoot 'code/*') -Destination $sketchDir -Recurse -Force
    } catch {
        Write-LastLog $_.Exception.Message
        if ($script:State.Interactive) { Show-Log 'Ошибка сборки' $script:LastLog }
        else { Show-LastLogTail }
        return $false
    }

    $arguments = @(
        'compile', '--fqbn', $script:Fqbn,
        '--build-path', $buildDir,
        '--build-property', "compiler.cpp.extra_flags=$flags",
        $sketchDir)
    if (-not (Invoke-ExternalWithProgress 'Сборка прошивки' "Собираю $(Get-ProfileLabel $profile)" `
        $script:LastLog 'indeterminate' $script:ArduinoCli $arguments)) {
        if ($script:State.Interactive) { Show-Log 'Ошибка сборки' $script:LastLog }
        else { Show-LastLogTail }
        return $false
    }

    $sourceArtifact = Join-Path $buildDir 'mk61s-M.ino.bin'
    if (-not (Test-Path -LiteralPath $sourceArtifact -PathType Leaf) -or (Get-Item -LiteralPath $sourceArtifact).Length -eq 0) {
        Write-LastLog "Build succeeded but $sourceArtifact was not created." -Append
        if ($script:State.Interactive) { Show-Log 'Ошибка сборки' $script:LastLog }
        else { Show-LastLogTail }
        return $false
    }

    try {
        Copy-Item -LiteralPath $sourceArtifact -Destination "$artifact.tmp" -Force
        Move-Item -LiteralPath "$artifact.tmp" -Destination $artifact -Force
        [IO.File]::WriteAllText("$artifact.flags.tmp", $flags + [Environment]::NewLine, $script:Utf8NoBom)
        Move-Item -LiteralPath "$artifact.flags.tmp" -Destination "$artifact.flags" -Force
    } catch {
        Write-LastLog $_.Exception.Message -Append
        if ($script:State.Interactive) { Show-Log 'Ошибка сборки' $script:LastLog }
        else { Show-LastLogTail }
        return $false
    }

    $size = (Get-Item -LiteralPath $artifact).Length
    if ($script:State.Interactive) {
        Show-Message 'Сборка завершена' "Профиль: $(Get-ProfileLabel $profile)`n`n$(Get-CompileOptionsDetails)`n`nФайл: $artifact`nРазмер: $size байт"
    } else {
        [Console]::WriteLine("Built: $artifact ($size bytes)")
    }
    return $true
}

function Wait-ForDfu {
    param([int]$Seconds = 30)
    $attempts = $Seconds * 2
    for ($attempt = 0; $attempt -lt $attempts; $attempt++) {
        if (Test-DfuPresent) { return $true }
        if ($script:State.Interactive) {
            $percent = [Math]::Min(90, [int](90 * ($attempt + 1) / $attempts))
            Draw-Progress 'Поиск DFU' 'Жду STM32 DFU 0483:df11' $percent
        }
        Start-Sleep -Milliseconds 500
    }
    Write-LastLog "STM32 DFU 0483:df11 was not found within $Seconds seconds."
    return $false
}

function Ensure-DfuReady {
    if ($script:IsWindowsHost -and -not (Test-CommandAvailable $script:ArduinoCli)) {
        $message = 'На Windows для сборки и DFU-загрузки нужен arduino-cli.exe.'
        Write-LastLog $message
        if ($script:State.Interactive) { Show-Message 'Arduino CLI' $message }
        else { [Console]::Error.WriteLine($message) }
        return $false
    }
    if ($script:IsWindowsHost -and -not (Find-Stm32CubeProgrammer)) {
        $message = "STM32CubeProgrammer не найден. Установите его с сайта ST; Arduino CLI использует официальный DFU recipe STM32 Core.`nhttps://www.st.com/en/development-tools/stm32cubeprog.html"
        Write-LastLog $message
        if ($script:State.Interactive) { Show-Message 'DFU uploader' $message }
        else { [Console]::Error.WriteLine($message) }
        return $false
    }
    if (-not $script:IsWindowsHost -and -not (Find-DfuUtil)) {
        $message = "dfu-util не найден. Укажите путь при запуске меню или установите STM32 Arduino Core $($script:Stm32CoreVersion)."
        Write-LastLog $message
        if ($script:State.Interactive) { Show-Message 'DFU uploader' $message }
        else { [Console]::Error.WriteLine($message) }
        return $false
    }
    if (Test-DfuPresent) { return $true }

    [void](Detect-Device)
    if (-not [string]::IsNullOrEmpty($script:State.DetectedPort)) {
        if (-not $script:State.Interactive) {
            [Console]::WriteLine("Requesting DFU mode on $($script:State.DetectedPort)…")
        }
        [void](Invoke-MonitorExchange $script:State.DetectedPort 'dfu')
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if (Test-DfuPresent) { return $true }
            Start-Sleep -Milliseconds 250
        }
    }

    if ($script:State.Interactive) {
        Show-Message 'Нужен режим DFU' 'Зажмите ESC на калькуляторе и нажмите RESET (или подключите USB с зажатым ESC). Затем отпустите ESC. Меню будет ждать загрузчик 30 секунд.'
    } else {
        [Console]::WriteLine('Enter DFU: hold ESC and press RESET (waiting 30 seconds).')
    }
    if (Wait-ForDfu 30) {
        $script:State.DeviceStatus = 'STM32 DFU 0483:df11 · готов к загрузке'
        if ($script:State.Interactive) { Draw-Progress 'Поиск DFU' 'Готово' 100; Start-Sleep -Milliseconds 350 }
        return $true
    }
    if ($script:State.Interactive) { Show-Log 'DFU не найден' $script:LastLog }
    else { Show-LastLogTail 20 }
    return $false
}

function Get-UploadInvocation {
    param([string]$Artifact)
    if ($script:IsWindowsHost) {
        return [pscustomobject]@{
            Executable = $script:ArduinoCli
            Arguments = [string[]]@('upload', '--fqbn', $script:Fqbn, '--input-file', $Artifact)
        }
    }
    return [pscustomobject]@{
        Executable = $script:DfuExecutable
        Arguments = [string[]]@('-d', '0483:df11', '-a', '0', '-s', '0x08000000:leave', '-D', $Artifact)
    }
}

function Upload-Selected {
    if (-not (Ensure-HardwareProfile)) { return $false }
    if ($script:State.Interactive) {
        $question = "Профиль: $(Get-ProfileLabel $script:State.Profile)`nКонтроллер: STM32F411CE BlackPill`nМетод: USB DFU`n`n$(Get-CompileOptionsDetails)`n`nСобрать прошивку и загрузить её в устройство?"
        if (-not (Show-YesNo 'Собрать и прошить' $question)) { return $false }
    }
    if (-not (Build-Selected)) { return $false }
    if (-not (Ensure-DfuReady)) { return $false }
    $artifact = Join-Path $script:OutputDir $script:Profiles[$script:State.Profile].Artifact
    $upload = Get-UploadInvocation $artifact
    if (Invoke-ExternalWithProgress 'Загрузка прошивки' 'Записываю и перезапускаю STM32' `
        $script:LastLog 'measured' $upload.Executable $upload.Arguments) {
        $script:State.DeviceStatus = 'прошивка загружена; устройство перезапущено'
        if ($script:State.Interactive) {
            Show-Message 'Готово' "Прошивка загружена.`n`n$(Get-ProfileLabel $script:State.Profile)"
        } else { [Console]::WriteLine("Uploaded: $artifact") }
        return $true
    }
    if ($script:State.Interactive) { Show-Log 'Ошибка загрузки' $script:LastLog }
    else { Show-LastLogTail }
    return $false
}

function Show-Dependencies {
    Show-Message 'Зависимости' (Get-DependencyReport)
}

function Show-Config {
    Sync-ProfileFromHardware
    [Console]::WriteLine("CONFIG_FILE=$($script:ConfigFile)")
    [Console]::WriteLine("PLATFORM=$($script:State.Platform)")
    [Console]::WriteLine("SCREEN=$($script:State.Screen)")
    [Console]::WriteLine("PROFILE=$($script:State.Profile)")
    [Console]::WriteLine("DFU_UTIL_PATH=$($script:State.DfuPath)")
    [Console]::WriteLine("STM32_CUBE_PROGRAMMER_PATH=$($script:State.CubeProgrammerPath)")
    [Console]::WriteLine("MK61_ENABLE_FOCAL=$($script:State.EnableFocal)")
    [Console]::WriteLine("MK61_ENABLE_TINYBASIC=$($script:State.EnableTinyBasic)")
    [Console]::WriteLine("MK61_ENABLE_WBMP_VIEWER=$($script:State.EnableWbmp)")
    [Console]::WriteLine("MK61_ENABLE_USB_SCREEN=$($script:State.EnableUsbScreen)")
    [Console]::WriteLine("MK61_ENABLE_EXTENDED_FONT_SETTINGS=$($script:State.EnableFonts)")
    [Console]::WriteLine("MK61_USER_EXPLORER_SHORTCUT=$($script:State.EnableExplorer)")
    [Console]::WriteLine("MK61_MATH_BACKEND=$($script:State.EnableCoreMath)")
    $flags = if (Test-Profile $script:State.Profile) { Get-AllCompileFlags $script:State.Profile }
        else { Get-CompileOptionFlags }
    [Console]::WriteLine("COMPILE_FLAGS=$flags")
}

function Show-Profiles {
    foreach ($id in $script:Profiles.Keys) {
        [Console]::WriteLine("$id`t$($script:Profiles[$id].Label)`t$($script:Profiles[$id].Flags)")
    }
}

function Invoke-InteractiveMain {
    $script:State.Interactive = $true
    Enter-Tui
    Load-Config
    [void](Configure-DfuUploader)
    $script:State.DeviceStatus = 'не проверялось · пункт «Найти устройство»'
    $items = @(
        [pscustomobject]@{ Tag = 'upload'; Label = "$($script:Glyphs.MenuUpload) Собрать и прошить" }
        [pscustomobject]@{ Tag = 'build'; Label = "$($script:Glyphs.MenuBuild) Только собрать .bin" }
        [pscustomobject]@{ Tag = 'platform'; Label = "$($script:Glyphs.MenuChoice) Платформа" }
        [pscustomobject]@{ Tag = 'screen'; Label = "$($script:Glyphs.MenuChoice) Экран" }
        [pscustomobject]@{ Tag = 'options'; Label = "$($script:Glyphs.MenuOptions) Ключи компиляции" }
        [pscustomobject]@{ Tag = 'detect'; Label = "$($script:Glyphs.MenuDetect) Найти устройство" }
        [pscustomobject]@{ Tag = 'deps'; Label = "$($script:Glyphs.MenuCheck) Проверить зависимости" }
        [pscustomobject]@{ Tag = 'setup'; Label = "$($script:Glyphs.MenuInstall) Установить Arduino-зависимости" }
        [pscustomobject]@{ Tag = 'log'; Label = "$($script:Glyphs.MenuLog) Последний журнал" }
        [pscustomobject]@{ Tag = 'quit'; Label = "$($script:Glyphs.MenuQuit) Выход" }
    )
    $mainSelection = 'upload'
    while ($true) {
        $platformText = Get-PlatformLabel $script:State.Platform
        $screenText = Get-ScreenLabel $script:State.Screen
        if ((Test-Platform $script:State.Platform) -and (Test-Screen $script:State.Screen) -and
            -not (Test-HardwareCompatible $script:State.Platform $script:State.Screen)) {
            $screenText += ' · несовместим'
        }
        $text = "Платформа: $platformText`nЭкран: $screenText`nКлючи: $(Get-CompileOptionsSummary)`nЦель: STM32F411CE BlackPill · USB DFU`nDFU: $($script:State.DfuStatus)`nУстройство: $($script:State.DeviceStatus)"
        $selection = Show-Menu 'MK61s · прошивка' $text $items $mainSelection
        if ([string]::IsNullOrEmpty($selection)) { break }
        $mainSelection = $selection
        switch ($selection) {
            'upload' { [void](Upload-Selected) }
            'build' { [void](Build-Selected) }
            'platform' { [void](Choose-Platform) }
            'screen' { [void](Choose-Screen) }
            'options' { [void](Choose-CompileOptions) }
            'detect' {
                if (Detect-Device) { Show-Message 'Устройство' $script:State.DeviceStatus }
                else { Show-Message 'Устройство' 'MK61s и STM32 DFU не найдены.' }
            }
            'deps' { Show-Dependencies }
            'setup' { [void](Install-ArduinoDependencies) }
            'log' { Show-Log 'Последний журнал' $script:LastLog }
            'quit' { return 0 }
        }
    }
    return 0
}

function Show-Usage {
    [Console]::WriteLine(@'
MK61s firmware builder and DFU uploader

Usage:
  tools\mk61-firmware.cmd
  tools\mk61-firmware.cmd --profile ID --build
  tools\mk61-firmware.cmd --profile ID --upload
  tools\mk61-firmware.cmd --detect
  tools\mk61-firmware.cmd --setup
  tools\mk61-firmware.cmd --list-profiles
  tools\mk61-firmware.cmd --show-config

Profiles:
  mini-v3-a00, mini-v3-a02, mini-v2-a00, mini-v2-a02,
  classic-v2, classic-v3, 40th

Environment overrides:
  MK61_ARDUINO_CLI, MK61_DFU_UTIL, MK61_STM32_PROGRAMMER, MK61_BUILD_ROOT,
  MK61_OUTPUT_DIR, MK61_CONFIG_FILE, MK61_COLOR

The Bash and PowerShell tools share .mk61-firmware.conf.
'@)
}

function Invoke-Application {
    param([string[]]$CliArguments)
    $action = 'tui'
    for ($index = 0; $index -lt $CliArguments.Count; $index++) {
        $argument = $CliArguments[$index]
        switch -Regex ($argument) {
            '^(--profile|-Profile)$' {
                if ($index + 1 -ge $CliArguments.Count) {
                    [Console]::Error.WriteLine('Error: --profile needs an ID.')
                    return 2
                }
                $index++
                $script:State.Profile = $CliArguments[$index]
                $script:State.CliProfile = $true
            }
            '^(--build|-Build)$' { $action = 'build' }
            '^(--upload|-Upload)$' { $action = 'upload' }
            '^(--detect|-Detect)$' { $action = 'detect' }
            '^(--setup|-Setup)$' { $action = 'setup' }
            '^(--list-profiles|-ListProfiles)$' { $action = 'list-profiles' }
            '^(--show-config|-ShowConfig)$' { $action = 'show-config' }
            '^(--plain|-Plain)$' { }
            '^(-h|--help|-Help)$' { Show-Usage; return 0 }
            default {
                [Console]::Error.WriteLine("Error: unknown option: $argument")
                Show-Usage
                return 2
            }
        }
    }

    if (-not [string]::IsNullOrEmpty($script:State.Profile) -and
        -not (Test-Profile $script:State.Profile)) {
        [Console]::Error.WriteLine("Error: unsupported profile: $($script:State.Profile)")
        return 2
    }

    switch ($action) {
        'tui' {
            try { $redirected = [Console]::IsInputRedirected } catch { $redirected = $false }
            if ($redirected) {
                [Console]::Error.WriteLine('Error: interactive mode needs a terminal. Use --build/--upload/--detect.')
                return 2
            }
            return Invoke-InteractiveMain
        }
        'list-profiles' { Show-Profiles; return 0 }
        'show-config' { Load-Config; Show-Config; return 0 }
        'build' {
            $script:State.Interactive = $false
            Load-Config
            if (Build-Selected) { return 0 } else { return 1 }
        }
        'upload' {
            $script:State.Interactive = $false
            Load-Config
            if (Upload-Selected) { return 0 } else { return 1 }
        }
        'detect' {
            $script:State.Interactive = $false
            Load-Config
            $found = Detect-Device
            [Console]::WriteLine($script:State.DeviceStatus)
            if (-not [string]::IsNullOrEmpty($script:State.DetectedVersion)) {
                [Console]::WriteLine($script:State.DetectedVersion)
            }
            if ($found) { return 0 } else { return 1 }
        }
        'setup' {
            $script:State.Interactive = $false
            if (Install-ArduinoDependencies) {
                [Console]::WriteLine((Get-DependencyReport))
                return 0
            }
            Show-LastLogTail
            return 1
        }
    }
    return 2
}

if ([Environment]::GetEnvironmentVariable('MK61_POWERSHELL_IMPORT_ONLY') -eq '1') { return }

$script:ExitCode = 1
try {
    $script:ExitCode = Invoke-Application @($args)
} catch {
    if ($script:ScreenActive) { Exit-Tui }
    [Console]::Error.WriteLine("Error: $($_.Exception.Message)")
    $script:ExitCode = 1
} finally {
    if ($null -ne $script:ActiveJob) {
        Stop-Job -Job $script:ActiveJob -ErrorAction SilentlyContinue
        Remove-Job -Job $script:ActiveJob -Force -ErrorAction SilentlyContinue
        $script:ActiveJob = $null
    }
    Exit-Tui
}
exit $script:ExitCode
