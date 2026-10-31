#!/usr/bin/env python3
"""Build isolated ARM kernels, with no production changes or hardware access."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,**kw):return subprocess.run([str(x) for x in cmd],check=True,**kw)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'.build/rp2040-interpolator-20261023')
    p.add_argument('--toolchain',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);tc=compiler_bin(a.toolchain)
    run([sys.executable,HERE/'generate.py','--check'],stdout=subprocess.DEVNULL)
    flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-lto','-fno-builtin',
      '-ffunction-sections','-fdata-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-I'+str(HERE)]
    objects=[]
    for name in ('kernels.cpp','divide.S','root_seed.S'):
        source=HERE/name;obj=out/(name+'.o');objects.append(obj)
        run([tc/('arm-none-eabi-g++' if name.endswith('.cpp') else 'arm-none-eabi-gcc'),*flags,
          *(['-std=c++17','-fno-exceptions','-fno-rtti'] if name.endswith('.cpp') else []),'-c',source,'-o',obj])
    ld=out/'kernels.ld';ld.write_text('SECTIONS { . = 0x10001000; .text : { *(.text*) *(.rodata*) } . = 0x20000000; .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n')
    elf=out/'kernels.elf'
    run([tc/'arm-none-eabi-gcc',*flags,'-nostdlib',*objects,'-Wl,-T,'+str(ld),'-Wl,-e,cpu_wide32','-Wl,-Map,'+str(out/'kernels.map'),'-o',elf])
    with (out/'kernels.dis').open('w') as f:run([tc/'arm-none-eabi-objdump','-d',elf],stdout=f)
    refs=[ROOT/'code/native_eabi_m0.cpp',ROOT/'code/native_eabi_m0_pow_fast.inc',ROOT/'code/native_eabi_m0_rsqrt_table.inc',
      ROOT/'code/native_eabi_m0_log70_center.inc',ROOT/'code/native_eabi_m0_log70_table.inc',ROOT/'code/native_eabi_m0.S',ROOT/'code/native_eabi_m0_sqrt64_table.inc']
    manifest=dict(status='BUILT_NOT_HARDWARE_TESTED',hardware_verified=False,elf=str(elf),elf_sha256=digest(elf),
      toolchain=str(tc),compiler=run([tc/'arm-none-eabi-gcc','--version'],capture_output=True,text=True).stdout.splitlines()[0],
      flags=flags,sources={p.name:digest(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.suffix in ('.cpp','.h','.S','.inc','.py')},
      references={str(p.relative_to(ROOT)):digest(p) for p in refs})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status=manifest['status'],elf=str(elf),elf_sha256=manifest['elf_sha256']),indent=2))
if __name__=='__main__':main()
