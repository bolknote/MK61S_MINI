#!/usr/bin/env python3
"""Link complete memmove candidates into a verified unused Classic Flash span."""
import argparse,hashlib,json,subprocess,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
p.add_argument('--arm-toolchain-bin',type=Path,required=True)
a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True)
TC=a.arm_toolchain_bin
base=0x08062000
source=out/'baseline.c';source.write_text('#include "'+str(HERE/'baseline-memory.h')+'"\n__attribute__((noipa)) void* baseline(void*d,const void*s,size_t n){return mk61_memory_move(d,s,n);}\n')
common=[str(TC/'arm-none-eabi-gcc'),'-mcpu=cortex-m4','-mthumb','-Os','-fno-builtin','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'code')]
for src,name in ((source,'baseline'),(HERE/'candidates.S','candidates'),(ROOT/'sdk/portable/memory.c','sdk')):
 subprocess.run(common+['-c',str(src),'-o',str(out/(name+'.o'))],check=True)
subprocess.run(common+['-nostdlib','-Wl,--gc-sections,-Ttext='+hex(base)+',-e,own16,-u,own64,-u,baseline,-u,memmove']+[str(out/(n+'.o')) for n in ('baseline','candidates','sdk')]+['-o',str(out/'payload.elf')],check=True)
subprocess.run([TC/'arm-none-eabi-objcopy','-O','binary',out/'payload.elf',out/'payload.bin'],check=True)
e=ElfImage(out/'payload.elf');raw=(out/'payload.bin').read_bytes();assert len(raw)<=8192
names={'BASELINE':'baseline','OWN16':'own16','OWN64':'own64','SDK':'memmove'}
layout=dict(base=base,bytes=len(raw),crc32=zlib.crc32(raw),sha256=hashlib.sha256(raw).hexdigest(),entries={k:dict(symbol=v,address=e.symbols[v]|1,bytes=e.sizes[v]) for k,v in names.items()})
(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
(out/'flash-layout.h').write_text('\n'.join(f'#define FLASH_{k} {e.symbols[v]|1}u' for k,v in names.items())+f'\n#define PAYLOAD_BASE {base}u\n#define PAYLOAD_BYTES {len(raw)}u\n#define PAYLOAD_CRC {zlib.crc32(raw)}u\n')
(out/'payload-disassembly.txt').write_text(subprocess.check_output([TC/'arm-none-eabi-objdump','-d',out/'payload.elf'],text=True))
print(json.dumps(layout,indent=2))
