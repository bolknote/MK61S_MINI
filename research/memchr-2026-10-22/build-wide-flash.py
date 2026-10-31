#!/usr/bin/env python3
"""Freeze exact wide-matrix bodies in an unused candidate Flash extension."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zlib

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(HERE))
from check_stm32_vectors import ElfImage
from proof import body
from run import FLASH_PATTERN

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--app-build',type=Path,required=True)
    p.add_argument('--cpu',choices=('m4','m0'),default='m4')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--arm-toolchain-bin',type=Path,required=True)
    a=p.parse_args();src=a.app_build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    base=0x08062000 if a.cpu=='m4' else 0x101e0000;data_offset=4096;tc=a.arm_toolchain_bin
    names=['baseline','libc_search','byte_search','own4','own16','own64','pair16','balanced16','pair64','balanced64']+\
        (['dsp16','dsp32','compact8'] if a.cpu=='m4' else ['fast16','fast64'])
    libc_bytes=160 if a.cpu=='m4' else 124
    objects=[f for f in (src/'app').glob('*.o') if 'baseline.c' in f.name or 'candidates.S' in f.name]+[src/'libc.o']
    arch=['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard'] if a.cpu=='m4' else ['-mcpu=cortex-m0plus','-mthumb']
    command=[str(tc/'arm-none-eabi-gcc'),*arch,'-nostdlib',
        '-Wl,--gc-sections,-Ttext='+hex(base+64)+',-e,baseline,--defsym,libc_search_end=libc_search+'+str(libc_bytes)+''.join(',-u,'+n for n in names),
        *map(str,objects),'-o',str(out/'kernels.elf')]
    subprocess.run(command,check=True)
    subprocess.run([str(tc/'arm-none-eabi-objcopy'),'-O','binary','-j','.text',str(out/'kernels.elf'),str(out/'code.bin')],check=True)
    code=(out/'code.bin').read_bytes();assert len(code)<=data_offset-64
    elf=ElfImage(out/'kernels.elf');app=ElfImage(src/'app/CHRBEN.elf');functions={}
    for name in names:
        size=libc_bytes if name=='libc_search' else elf.sizes[name];raw=body(elf,name,size)
        assert raw==body(app,name,size),(name,'Flash/APP identity differs')
        functions[name]=dict(address=elf.symbols[name]|1,bytes=size,sha256=hashlib.sha256(raw).hexdigest())
    data=bytes(FLASH_PATTERN);total=data_offset+len(data)
    header=struct.pack('<8s14I',b'MCHRFL4\0',4,total,data_offset,len(code),len(names),zlib.crc32(code),zlib.crc32(data),*([0]*7))
    payload=header+code+b'\xff'*(data_offset-64-len(code))+data;(out/'payload.bin').write_bytes(payload)
    layout=dict(cpu=a.cpu,base=base,bytes=total,data=base+data_offset,code_bytes=len(code),sha256=hashlib.sha256(payload).hexdigest(),crc32=f'{zlib.crc32(payload):08X}',
        elf_sha256=hashlib.sha256((out/'kernels.elf').read_bytes()).hexdigest(),functions=functions,command=command)
    (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    (out/'flash-layout.h').write_text('#define PAYLOAD_BASE '+hex(base)+'u\n#define PAYLOAD_BYTES '+str(total)+'u\n#define PAYLOAD_DATA '+hex(base+data_offset)+'u\n#define PAYLOAD_CRC 0x'+layout['crc32']+'u\n'+
        ''.join('#define FLASH_'+n.upper()+' '+hex(v['address'])+'u\n' for n,v in functions.items()))
    print(json.dumps(layout,indent=2))

if __name__=='__main__':main()
