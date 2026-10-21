#!/usr/bin/env python3
"""Execute ARMv6-M memset: exact bounds, alignment, value, return and AAPCS.

Optional research ELF/ROM mode validates the actual benchmark candidates before
loading the APP on hardware. Unicorn is used for correctness, never timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_ARM_REG_R0,
    UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR)
from check_stm32_vectors import ElfImage

ROOT=Path(__file__).resolve().parents[1]
RAM=0x20000000
DEST=RAM+0x10000
SP=RAM+0x41000
STOP=0x10000000

def verify(elf, names, rom=None):
    image=ElfImage(elf)
    uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
    uc.mem_map(RAM,0x42000);uc.mem_map(STOP,4096)
    image.load(uc)
    if rom:
        raw=rom.read_bytes()
        assert hashlib.sha256(raw).hexdigest()=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
        uc.mem_map(0,65536);uc.mem_write(0,raw)
        image.symbols['bootrom_memset']=0x26B9
        names=names+['bootrom_memset']
    rng=random.Random(0x6102040)
    cases=[(DEST+a,n,v) for n in range(258) for a in range(8)
           for v in (0,1,0x1234,0xffffffff)]
    cases += [(DEST+rng.randrange(32),rng.randrange(8193),rng.getrandbits(32)) for _ in range(2000)]
    cases += [(DEST+a,n,v) for n in (16384,32767,32768,32769,65535,65536)
              for a in range(8) for v in (0,0x1234)]
    cases += [(0,0,0xffffffff)]
    saved={r:0xA75D184B+r*0x1321 for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    active=[0,0]
    def store(cpu,access,address,size,value,user):
        del cpu,access,value,user
        assert size in (1,2,4) and address%size==0,('unaligned store',hex(address),size)
        assert (active[0]<=address and address+size<=active[1]) or (SP-32<=address and address+size<=SP),('out of bounds',hex(address),size,active)
    uc.hook_add(UC_HOOK_MEM_WRITE,store)
    results=[]
    for name in names:
        for dest,n,value in cases:
            active[:]=[dest,dest+n]
            start=dest-16 if dest else DEST
            uc.mem_write(start,b'\x5A'*(n+32))
            for r,v in saved.items():uc.reg_write(r,v)
            for r,v in ((UC_ARM_REG_R0,dest),(UC_ARM_REG_R1,value),(UC_ARM_REG_R2,n),
                        (UC_ARM_REG_SP,SP),(UC_ARM_REG_LR,STOP|1),(UC_ARM_REG_XPSR,0x01000000)):
                uc.reg_write(r,v)
            uc.emu_start(image.symbols[name]|1,STOP,count=1000000)
            assert uc.reg_read(UC_ARM_REG_PC)==STOP,(name,dest,n,value,'return')
            assert uc.reg_read(UC_ARM_REG_R0)==dest and uc.reg_read(UC_ARM_REG_SP)==SP
            assert all(uc.reg_read(r)==v for r,v in saved.items()),(name,'callee-saved')
            assert uc.mem_read(start,n+32)==b'\x5A'*16+bytes([value&255])*n+b'\x5A'*16,(name,dest,n,value,'content')
        result=dict(name=name,cases=len(cases),status='PASS',bytes=image.sizes.get(name))
        results.append(result);print(json.dumps(result),flush=True)
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path)
    p.add_argument('--benchmark-elf',type=Path)
    p.add_argument('--rom',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args();results=[]
    if args.benchmark_elf:
        image=ElfImage(args.benchmark_elf)
        results=verify(args.benchmark_elf,[n for n in ('byte_fill','own16','own64','own_fast') if n in image.symbols],args.rom)
    else:
        compiler=shutil.which('arm-none-eabi-gcc')
        tc=args.arm_toolchain_bin or (Path(compiler).parent if compiler else None)
        assert tc is not None,'Pass --arm-toolchain-bin'
        with tempfile.TemporaryDirectory(prefix='mk61-memset-m0-') as temporary:
            elf=Path(temporary)/'fill.elf'
            for lto in (False,True):
                command=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-Os','-std=c11',
                    '-Wall','-Wextra','-Werror','-fno-builtin','-ffunction-sections',
                    *(['-flto'] if lto else []),str(ROOT/'sdk/portable/memory.c'),'-I'+str(ROOT/'code'),
                    '-nostdlib','-Wl,--gc-sections,-Ttext=0x20000000,-e,memset','-o',str(elf)]
                subprocess.run(command,check=True)
                rows=verify(elf,['memset']);results.extend(dict(lto=lto,**row) for row in rows)
    if args.output:args.output.write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
