#!/usr/bin/env python3
"""Check actual Cortex-M4 word/DSP instructions and bounds, without cycle claims."""
import argparse
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M4,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,
    UC_ARM_REG_R0,UC_ARM_REG_R4,UC_ARM_REG_R11,UC_ARM_REG_XPSR)

A,B,J,SP,STOP=0x20000000,0x20010000,0x20014000,0x2001F000,0x080FF000


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--register-copy',action='store_true',help='check the by-value cursor and short-match follow-up')
    p.add_argument('--production-encoder',action='store_true',help='check the integrated encoder kernels')
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    common=['-Os','-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard',
        '-fno-builtin','-ffunction-sections','-fdata-sections','-fstack-usage']
    if args.register_copy:common.append('-DZX0_REGISTER_COPY=1')
    if args.production_encoder:common.append('-DZX0_PRODUCTION_ENCODER=1')
    commands=[[args.arm_toolchain_bin/'arm-none-eabi-g++',*common,'-std=c++17','-Wall','-Wextra','-Werror',
        '-fno-exceptions','-fno-rtti','-I'+str(ROOT/'code'),'-c',ROOT/'tests/experimental/zx0_candidates_arm_probe.cpp','-o',out/'probe.o'],
        [args.arm_toolchain_bin/'arm-none-eabi-g++',*common,'-nostdlib','-Wl,-Ttext=0x08010000,-e,zx0_probe,--gc-sections',out/'probe.o','-o',out/'probe.elf']]
    for command in commands:subprocess.run(list(map(str,command)),check=True)
    elf=ElfImage(out/'probe.elf');u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
    u.mem_map(0x08000000,0x100000);u.mem_map(0x20000000,0x20000);elf.load(u)
    readable=[];writable=[];checks=0;minimum_stack=SP

    def access(machine,kind,address,size,value,user):
        nonlocal minimum_stack
        del machine,value,user
        if SP-2048<=address and address+size<=SP:
            minimum_stack=min(minimum_stack,address);return
        ranges=writable if kind==17 else readable
        assert any(lo<=address and address+size<=hi for lo,hi in ranges),(kind,hex(address),size)
    u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)

    def call(family,variant,data,position=0,offset=0,lcp=None):
        nonlocal readable,writable,checks
        source=bytes(data);u.mem_write(A,source)
        if lcp is not None:u.mem_write(B,struct.pack('<257H',*lcp))
        job=(family,variant,A,len(source),position,offset,B,0,0,0)
        u.mem_write(J,struct.pack('<10I',*job))
        readable=[(A,A+len(source)),(B,B+514),(J,J+40),(0x08000000,0x08100000)]
        writable=[(J+28,J+40)]
        if family==0:writable.append((A+position,A+len(source)))
        if family==2:writable.append((B,B+514))
        saved={r:(0xAC611337+r*0x1021)&0xFFFFFFFF for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
        for r,value in saved.items():u.reg_write(r,value)
        u.reg_write(UC_ARM_REG_SP,SP);u.reg_write(UC_ARM_REG_LR,STOP|1);u.reg_write(UC_ARM_REG_R0,J)
        u.reg_write(UC_ARM_REG_XPSR,0x01000000)
        u.emu_start(elf.symbols['zx0_probe']|1,STOP,count=1000000)
        assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_R0)==1 and u.reg_read(UC_ARM_REG_SP)==SP
        assert all(u.reg_read(r)==v for r,v in saved.items())
        actual=bytes(u.mem_read(A,len(source)));fields=struct.unpack('<10I',u.mem_read(J,40))
        if family!=0:assert actual==source
        checks+=1
        return actual,fields,struct.unpack('<257H',u.mem_read(B,514)) if lcp is not None else None

    rng=random.Random(0xC061F411)
    for offset in [*range(1,17),31,256,32768]:
        for n in [*range(18),31,32,127,128,512]:
            for align in range(4):
                position=offset+align;data=bytes((i*73+i//17)&255 for i in range(position+n));expected=bytearray(data)
                for i in range(n):expected[position+i]=expected[position+i-offset]
                actual,fields,_=call(0,1,data,position,offset)
                assert actual==expected and fields[7]==len(expected)
    for n in [*range(34),63,64,127,128,512]:
        for offset in [1,2,3,4,7,16,255,256]:
            for pattern in range(3):
                position=256;data=bytearray((i%offset) for i in range(position+n))
                if n and pattern:data[position+(0 if pattern==1 else n-1)]^=0x80
                expected=0
                while expected<n and data[position+expected]==data[position+expected-offset]:expected+=1
                _,fields,_=call(1,1,data,position,offset);assert fields[7]==expected
    for position in [*range(261),511,512,513]:
        for pattern in range(4):
            data=bytes((65 if pattern==0 else 65+(i==position) if pattern==1 else rng.randrange(2) if pattern==2 else rng.randrange(256)) for i in range(position+1))
            values=[rng.randrange(8192) for _ in range(257)];expected=list(values)
            for offset in range(1,257):expected[offset]=values[offset]+1 if offset<=position and data[position]==data[position-offset] else 0
            for variant in (1,2):
                _,fields,actual=call(2,variant,data,position,lcp=values)
                assert actual==tuple(expected) and fields[8]==max(expected[1:129]) and fields[9]==max(expected[129:])
    for mask in range(16):
        for value in range(1,256):
            difference=sum(value<<(lane*8) for lane in range(4) if mask&(1<<lane))
            wanted=sum(255<<(lane*8) for lane in range(4) if not mask&(1<<lane))
            _,fields,_=call(3,2,b'',offset=difference);assert fields[7]==wanted
    result=dict(status='PASS',checks=checks,register_copy=args.register_copy,production_encoder=args.production_encoder,maximum_stack_access_bytes=SP-minimum_stack,
        scope='Actual Cortex-M4 ISA; exact normal-memory reads/writes, immutable sources, SP and callee-saved registers. No hardware cycle claim.',
        commands=[[str(x) for x in command] for command in commands])
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Cortex-M4 ZX0 word/DSP kernels:',checks,'checks PASS; no speed claim')


if __name__=='__main__':main()
