#!/usr/bin/env python3
"""Build a bounded Flash extension with full memset dispatchers for comparison."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'.build/stm32f411-rom-20261021/flash-experiment'
TC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
BASE=0x08062000


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    variants=[('resident',None,0),('rom',None,0),('style','local_bulk_style',0),
              ('edges','local_bulk_edges',0),('loop','local_bulk_edges_loop',0),
              ('style4','local_bulk_style',4),('edges4','local_bulk_edges',4),
              ('loop4','local_bulk_edges_loop',4)]
    asm=['.syntax unified','.cpu cortex-m4','.thumb','.section .text,"ax",%progbits']
    for name,symbol,shift in variants[1:]:
        asm += ['.balign 16',f'.global full_{name}',f'.type full_{name},%function','.thumb_func',f'full_{name}:',
                'cbz r2,1f','cmp r2,#3','bhi 2f','b.w 0x080088b0',
                '2: cmp r2,#15','bhi 3f','b.w 0x080088c0',f'3: b.w bulk_{name}',
                '1: bx lr',f'.size full_{name},.-full_{name}',
                '.balign 16',f'.space {shift},0' if shift else '',f'.global bulk_{name}',f'.type bulk_{name},%function',
                '.thumb_func',f'bulk_{name}:']
        if name=='rom':
            asm += ['mov r3,r2','mov r2,r1','mov r1,r3','ldr r3,4f','bx r3',
                    '.balign 4','4: .word 0x1fff3bd5']
        else:
            code=(HERE/(symbol+'.bin')).read_bytes()
            assert hashlib.sha256(code).hexdigest()==next(x['sha256'] for x in json.loads((HERE/'local-validation.json').read_text()) if x['symbol']==symbol)
            asm += ['.byte '+','.join(str(b) for b in code)]
        asm += [f'.size bulk_{name},.-bulk_{name}']
    source=OUT/'payload.S';source.write_text('\n'.join(asm)+'\n')
    subprocess.run([TC/'arm-none-eabi-as','-mcpu=cortex-m4','-mthumb',source,'-o',OUT/'payload.o'],check=True)
    subprocess.run([TC/'arm-none-eabi-ld','-Ttext='+hex(BASE),'-e','full_rom',OUT/'payload.o','-o',OUT/'payload.elf'],check=True)
    subprocess.run([TC/'arm-none-eabi-objcopy','-O','binary',OUT/'payload.elf',OUT/'payload.bin'],check=True)
    symbols={}
    for line in subprocess.check_output([TC/'arm-none-eabi-nm','-S',OUT/'payload.elf'],text=True).splitlines():
        fields=line.split()
        if len(fields)==4:symbols[fields[-1]]={'address':int(fields[0],16)|1,'bytes':int(fields[1],16)}
    raw=(OUT/'payload.bin').read_bytes();assert len(raw)<=4096
    entries=[{'name':'resident','address':0x08008A21,'bulk_address':0x08008935,'bulk_bytes':88}]
    for name,_,_ in variants[1:]:
        entries.append({'name':name,**symbols['full_'+name],
                        'bulk_address':symbols['bulk_'+name]['address'],'bulk_bytes':symbols['bulk_'+name]['bytes']})
    layout={'base':BASE,'bytes':len(raw),'crc32':zlib.crc32(raw),'sha256':hashlib.sha256(raw).hexdigest(),'entries':entries}
    (OUT/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    (OUT/'flash-layout.h').write_text(f'#define PAYLOAD_BASE {BASE}u\n#define PAYLOAD_BYTES {len(raw)}u\n#define PAYLOAD_CRC {zlib.crc32(raw)}u\n#define VARIANTS {len(entries)}\nstatic const uintptr_t entry_addresses[VARIANTS]={{'+','.join(str(e['address'])+'u' for e in entries)+'};\n')
    (HERE/'flash-payload.S').write_text(subprocess.check_output([TC/'arm-none-eabi-objdump','-d',OUT/'payload.elf'],text=True))
    print(json.dumps(layout,indent=2))


if __name__=='__main__':main()
