#!/usr/bin/env python3
"""Check .NET/Python agreement for internal and forbidden Thumb-2 branches."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from app_relocations_self_test import elf_fixture
ROOT=Path(__file__).resolve().parents[1]
if not shutil.which('pwsh'):
    print('pwsh unavailable; .NET relocation check skipped')
else:
    with tempfile.TemporaryDirectory(prefix='mk61-reloc-dotnet-') as tmp:
        work=Path(tmp)
        for name,target in [('valid',1),('undefined',0),('foreign',6),('absolute',0xFFF1)]:
            (work/(name+'.elf')).write_bytes(elf_fixture('.debug_frame',relocation_kind=51,target_section=target))
        script=work/'check.ps1'
        script.write_text('''param([string]$Source,[string]$Fixtures)
$ErrorActionPreference = 'Stop'
Add-Type -Path $Source
foreach ($name in @('valid','undefined','foreign','absolute')) {
  $accepted = $false
  try {
    $count = [Mk61.Build.AppPacker]::ExtractRelocations(
      (Join-Path $Fixtures ($name+'.elf')),0x20000000,4,8,
      (Join-Path $Fixtures ($name+'.rel')))
    if ($count -ne 0) { throw 'unexpected runtime fixup' }
    $accepted = $true
  } catch {
    if ($_.Exception.GetBaseException().Message -notmatch 'PC-relative relocation 51 leaves APP') { throw }
  }
  if ($accepted -ne ($name -eq 'valid')) { throw "incorrect branch admission: $name" }
}
''')
        subprocess.run(['pwsh','-NoLogo','-NoProfile','-File',script,
                        ROOT/'tools/.mk61-app/Mk61AppPacker.cs',work],check=True)
    print('.NET Thumb-2 conditional branch: internal accepted, undefined/foreign/absolute rejected PASS')
