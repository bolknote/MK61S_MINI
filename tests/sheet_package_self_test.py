#!/usr/bin/env python3
"""S1 demo format and binary MKC classification on both supported shells."""
import binascii
import importlib.util
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sheet_builder',ROOT/'tools/build_sheet_app.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for name in ('BUDGET.mks','CYCLE.mks'):
    data=(ROOT/'programs/sheets'/name).read_bytes()
    assert data[:10]==bytes.fromhex('4d4b53480110200000')+bytes((19 if name=='BUDGET.mks' else 3,))
    assert struct.unpack_from('<H',data,12)[0]==len(data)-20
    assert struct.unpack_from('<I',data,16)[0]==binascii.crc32(data[:16]+data[20:])

with tempfile.TemporaryDirectory(prefix='mk61-sheet-package-') as directory:
    work=Path(directory)
    module.examples(work)
    for name in ('BUDGET.mks','CYCLE.mks'):
        assert (work/name).read_bytes()==(ROOT/'programs/sheets'/name).read_bytes()
    commands=[['bash',str(ROOT/'tools/.mkc/mkc.sh')]]
    if shutil.which('pwsh'):
        commands.append(['pwsh','-NoLogo','-NoProfile','-File',str(ROOT/'tools/.mkc/mkc.ps1')])
    for size in (19,20,2048,2049):
        path=work/f'TEST-{size}.MKS';path.write_bytes(bytes(range(20))*(size//20)+bytes(range(size%20)))
        for command in commands:
            result=subprocess.run([*command,'--classify',str(path)],capture_output=True,text=True)
            if 20<=size<=2048:
                assert result.returncode==0 and result.stdout.strip()=='supported',(command,size,result.stdout,result.stderr)
            else:
                assert result.returncode==1 and result.stdout.startswith('unsupported:'),(command,size,result.stdout,result.stderr)
print('SHEET package: reproducible S1/CRC examples and binary MKS quota on Bash/PowerShell PASS')
