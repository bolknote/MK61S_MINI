#!/usr/bin/env python3
"""Build isolated ARM memchr candidates, including this toolchain's newlib."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage

def build(tc,out,cpu,base=0x20000000):
    out.mkdir(parents=True,exist_ok=True)
    gcc=str(tc/'arm-none-eabi-gcc')
    common=[gcc,'-mcpu='+('cortex-m0plus' if cpu=='m0' else 'cortex-m4'),'-mthumb']
    if cpu=='m4':common+=['-mfpu=fpv4-sp-d16','-mfloat-abi=hard']
    flags=['-Os','-fno-builtin','-ffunction-sections','-fdata-sections']
    archive=Path(subprocess.check_output(common+['-print-file-name=libc.a'],text=True).strip()).resolve()
    members=subprocess.check_output([tc/'arm-none-eabi-ar','t',archive],text=True).splitlines()
    member=next(n for n in members if n==('libc_a-memchr-stub.o' if cpu=='m0' else 'libc_a-memchr.o'))
    original=subprocess.check_output([tc/'arm-none-eabi-ar','p',archive,member])
    (out/'libc-original.o').write_bytes(original)
    libc_image=ElfImage(out/'libc-original.o')
    code_sections=[s for s in libc_image.sections if s[2]&4 and s[5]]
    assert len(code_sections)==1
    libc_bytes=code_sections[0][5]
    subprocess.run([tc/'arm-none-eabi-objcopy','--redefine-sym','memchr=libc_search',out/'libc-original.o',out/'libc.o'],check=True)
    for filename,name in [('candidates.S','candidates'),('baseline.c','baseline')]:
        raw=(HERE/filename).read_bytes();(out/filename).write_bytes(raw)
        subprocess.run(common+flags+['-c',str(out/filename),'-o',str(out/(name+'.o'))],check=True)
    names=['baseline','libc_search','byte_search','own4','own16','own64']
    if cpu=='m4':names+=['swar16']
    subprocess.run(common+flags+['-nostdlib','-Wl,--gc-sections,-Ttext='+hex(base)+',-e,own4,--defsym,libc_search_end=libc_search+'+str(libc_bytes)+''.join(',-u,'+n for n in names)]+[str(out/(n+'.o')) for n in ('baseline','libc','candidates')]+['-o',str(out/'kernels.elf')],check=True)
    subprocess.run([tc/'arm-none-eabi-objcopy','-O','binary',out/'kernels.elf',out/'kernels.bin'],check=True)
    disassembly=subprocess.check_output([tc/'arm-none-eabi-objdump','-d',out/'kernels.elf'],text=True)
    (out/'disassembly.txt').write_text(disassembly)
    e=ElfImage(out/'kernels.elf')
    result=dict(cpu=cpu,base=base,elf_sha256=hashlib.sha256((out/'kernels.elf').read_bytes()).hexdigest(),
        libc=dict(archive=str(archive),member=member,sha256=hashlib.sha256(original).hexdigest()),
        sources={n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ('candidates.S','baseline.c')},
        functions={n:dict(address=e.symbols[n]|1,bytes=libc_bytes if n=='libc_search' else e.sizes[n]) for n in names})
    (out/'kernels.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    p.add_argument('--cpu',choices=('m0','m4'),required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--base',type=lambda s:int(s,0),default=0x20000000)
    a=p.parse_args()
    print(json.dumps(build(a.arm_toolchain_bin,a.output,a.cpu,a.base),indent=2))
