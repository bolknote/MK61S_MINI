# Replace only the physical serial boundary in disposable script copies.
# Identity selection, validation, C6 transfer and readback remain unmodified.
function Set-Mk61E2eSerialAdapter {
    param([string]$Path, [ValidateSet('Uploader', 'Installer')][string]$Kind,
        [switch]$NonWindowsHost)
    $source = [IO.File]::ReadAllText($Path)
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw "Invalid PowerShell input: $Path" }
    $functions = @($ast.FindAll({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst]
    }, $false))
    $constructor = if ($Kind -eq 'Installer') { 'New-ConfiguredSerialPort' } else { 'New-Mk61UploadProbeSerialPort' }
    $ports = if ($Kind -eq 'Installer') { 'Get-CdcPorts' } else { 'Get-Mk61UploadSerialPorts' }
    $changes = @()
    foreach ($name in @($constructor, $ports)) {
        $found = @($functions | Where-Object { $_.Name -ceq $name })
        if ($found.Count -ne 1) { throw "Expected exactly one $name in $Path" }
        $function = $found[0]
        if ($name -eq $constructor) {
            $needle = 'New-Object System.IO.Ports.SerialPort'
            if ([regex]::Matches($function.Extent.Text, [regex]::Escape($needle)).Count -ne 1) {
                throw "Serial constructor changed in $Path"
            }
            $replacement = $function.Extent.Text.Replace($needle, '(New-Mk61E2eSerial $PortName)')
        } else {
            $replacement = "function $name { Initialize-Mk61E2eDevice; return @([Mk61.ArduinoE2E.Device]::Ports()) }"
        }
        $changes += [pscustomobject]@{ Start = $function.Extent.StartOffset; Length = $function.Extent.Text.Length; Text = $replacement }
    }
    if ($Kind -eq 'Installer' -and $NonWindowsHost) {
        $found = @($functions | Where-Object { $_.Name -ceq 'Test-UseDirectSerialTransport' })
        if ($found.Count -ne 1) { throw 'Missing transport selection function' }
        $changes += [pscustomobject]@{ Start = $found[0].Extent.StartOffset; Length = $found[0].Extent.Text.Length;
            Text = 'function Test-UseDirectSerialTransport { return $true }' }
    }
    foreach ($change in @($changes | Sort-Object Start -Descending)) {
        $source = $source.Remove($change.Start, $change.Length).Insert($change.Start, $change.Text)
    }
    # Insert after the script parameter block, before the first function.
    $loader = @'
function Initialize-Mk61E2eDevice {
    if ($null -eq ('Mk61.ArduinoE2E.Device' -as [type])) {
        Add-Type -Path $env:MK61_E2E_DEVICE_SOURCE
    }
}
function New-Mk61E2eSerial {
    param([string]$PortName)
    Initialize-Mk61E2eDevice
    return [Mk61.ArduinoE2E.Serial]::new($PortName)
}

'@
    $source = $source.Insert(($functions | Sort-Object { $_.Extent.StartOffset } | Select-Object -First 1).Extent.StartOffset, $loader)
    [IO.File]::WriteAllText($Path, $source, [Text.UTF8Encoding]::new($true))
}
