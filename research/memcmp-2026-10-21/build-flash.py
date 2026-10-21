#!/usr/bin/env python3
"""Link complete memory candidates for a separately verified unused Flash span."""
import argparse,hashlib,json,subprocess,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
p.add_argument('--arm-toolchain-bin',type=Path,required=True)
p.add_argument('--cpu',choices=('m4','m0'),default='m4')
a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True)
TC=a.arm_toolchain_bin
base=0x08062000 if a.cpu=='m4' else 0x101E0000
source=out/'baseline.c';source.write_text('#include "'+str(HERE/'baseline-memory.h')+'"\n__attribute__((noipa)) int baseline(const void*d,const void*s,size_t n){return mk61_memory_compare(d,s,n);}\n')
common=[str(TC/'arm-none-eabi-gcc'),'-mcpu='+('cortex-m4' if a.cpu=='m4' else 'cortex-m0plus'),'-mthumb','-Os','-fno-builtin','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'code')]
if a.cpu=='m4':common.append('-DMK61_MEMCMP_M4_FLASH=1')
for src,name in ((source,'baseline'),(HERE/'candidates.S','candidates'),(ROOT/'sdk/portable/memory.c','sdk')):
 subprocess.run(common+['-c',str(src),'-o',str(out/(name+'.o'))],check=True)
retain=',-u,own_low64' if a.cpu=='m4' else ',-u,memcpy,-u,memmove'
subprocess.run(common+['-nostdlib','-Wl,--gc-sections,-Ttext='+hex(base)+',-e,own4,-u,own16,-u,own64,-u,baseline,-u,memcmp'+retain]+[str(out/(n+'.o')) for n in ('baseline','candidates','sdk')]+['-o',str(out/'payload.elf')],check=True)
subprocess.run([TC/'arm-none-eabi-objcopy','-O','binary',out/'payload.elf',out/'payload.bin'],check=True)
e=ElfImage(out/'payload.elf');raw=(out/'payload.bin').read_bytes();assert len(raw)<=8192
names={'BASELINE':'baseline','OWN4':'own4','OWN16':'own16','OWN64':'own64','SDK':'memcmp'}
names.update({'LOW64':'own_low64'} if a.cpu=='m4' else {'COPY':'memcpy','MOVE':'memmove'})
layout=dict(cpu=a.cpu,base=base,bytes=len(raw),crc32=zlib.crc32(raw),sha256=hashlib.sha256(raw).hexdigest(),entries={k:dict(symbol=v,address=e.symbols[v]|1,bytes=e.sizes[v]) for k,v in names.items()})
(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
(out/'flash-layout.h').write_text('\n'.join(f'#define FLASH_{k} {e.symbols[v]|1}u' for k,v in names.items())+f'\n#define PAYLOAD_BASE {base}u\n#define PAYLOAD_BYTES {len(raw)}u\n#define PAYLOAD_CRC {zlib.crc32(raw)}u\n')
(out/'payload-disassembly.txt').write_text(subprocess.check_output([TC/'arm-none-eabi-objdump','-d',out/'payload.elf'],text=True))
print(json.dumps(layout,indent=2))
