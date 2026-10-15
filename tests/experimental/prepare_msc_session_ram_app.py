#!/usr/bin/env python3
"""Build a read-only allocator probe against an exact sealed firmware pair."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from hil_packbits_firmware import firmware_info
from check_stm32_vectors import ElfImage

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bin',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();fixture=firmware_info(a.bin);elf=ElfImage(a.elf)
    with tempfile.TemporaryDirectory(prefix='mk61-msc-pair-') as tmp:
        flat=Path(tmp)/'resident.bin'
        subprocess.run([str(a.arm_toolchain_bin/'arm-none-eabi-objcopy'),'-O','binary',str(a.elf),str(flat)],check=True)
        assert flat.read_bytes()==a.bin.read_bytes(),'ELF/BIN pair does not match'
    heap=elf.symbols['_ZN13shared_memory12_GLOBAL__N_1L11heap_cursorE']
    prepared=elf.symbols['prepared_handle'];end=elf.symbols['__mk61_dynamic_end']
    arenas=elf.symbols['_ZN13shared_memory12_GLOBAL__N_1L6arenasE']
    assert elf.sizes['_ZN13shared_memory12_GLOBAL__N_1L6arenasE']==5*92,'ArenaState qualification layout changed'
    assert all(0x20000000<=v<end and v%4==0 for v in (heap,prepared))
    values={'BUILD':int(fixture['build'],16),'FOOTER':0x08000000+fixture['footer'],
            'HEAP':heap,'END':end,'PREPARED':prepared,
            'SESSION':elf.symbols.get('mk61_session_msc_bytes',0),'ARENAS':arenas,'STRIDE':92}
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'msc_session_resident.hpp').write_text('// Exact sealed qualification image; never ship this APP.\n'+
        ''.join(f'#define MSC_PROBE_{k} 0x{v:08X}U\n' for k,v in values.items()))
    fixture['probe']=values;fixture['report_words']=9;(out/'resident.json').write_text(json.dumps(fixture,indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),
        '--name','MSCRAM','--shared-runtime','--source',str(ROOT/'tests/experimental/msc_session_ram_hil.cpp'),
        '--include',str(out),'--arm-toolchain-bin',str(a.arm_toolchain_bin),'--output-dir',str(out)],check=True)
if __name__=='__main__':main()
