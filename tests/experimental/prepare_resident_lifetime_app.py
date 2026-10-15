#!/usr/bin/env python3
"""Bind a read-only lifetime probe to one verified sealed production image."""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from hil_packbits_firmware import firmware_info
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bin',type=Path,required=True);p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    info=firmware_info(a.bin);elf=ElfImage(a.elf)
    with tempfile.TemporaryDirectory(prefix='mk61-lifetime-pair-') as d:
        flat=Path(d)/'resident.bin'
        subprocess.run([str(a.arm_toolchain_bin/'arm-none-eabi-objcopy'),'-O','binary',str(a.elf),str(flat)],check=True)
        assert flat.read_bytes()==a.bin.read_bytes(),'ELF/BIN mismatch'
    s=elf.symbols
    assert elf.sizes['_ZN13shared_memory12_GLOBAL__N_1L6arenasE']==5*92
    head=s.get('_ZN13shared_memory12_GLOBAL__N_1L16lifetime_buffersE',0)
    if head:
        assert elf.sizes['_ZN13shared_memory12_GLOBAL__N_1L16lifetime_buffersE']==4
        for name in ('_ZN8m61_textL15runtime_storageE',
                     '_ZN17storage_workspace12_GLOBAL__N_1L5bytesE'):
            assert elf.sizes[name]==16,'LifetimeBuffer qualification layout changed'

    values={'BUILD':int(info['build'],16),'FOOTER':0x08000000+info['footer'],
            'HEAP':s['_ZN13shared_memory12_GLOBAL__N_1L11heap_cursorE'],
            'END':s['__mk61_dynamic_end'],'ARENAS':s['_ZN13shared_memory12_GLOBAL__N_1L6arenasE'],'HEAD':head}
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'resident_lifetime.hpp').write_text('// Exact sealed diagnostic image; never distribute this APP.\n'+
        ''.join(f'#define LIFE_PROBE_{k} 0x{v:08X}U\n' for k,v in values.items()))
    info['probe']=values;(out/'resident.json').write_text(json.dumps(info,indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'tools/build_portable_app.py'),'--name','LIFERAM','--shared-runtime',
        '--source',str(ROOT/'tests/experimental/resident_lifetime_hil.cpp'),'--include',str(out),
        '--arm-toolchain-bin',str(a.arm_toolchain_bin),'--output-dir',str(out)],check=True)
if __name__=='__main__':main()
