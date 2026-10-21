#!/usr/bin/env python3
"""Execute the compiled Cortex-M4 memset, including its dispatcher and ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M4, UC_ARM_REG_R0,
    UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR)

ROOT=Path(__file__).resolve().parents[1]
BASE=0x08001000
RAM=0x20000000
RAM_SIZE=0x20000
SP=RAM+0x2000

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-toolchain-bin',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    compiler=shutil.which('arm-none-eabi-gcc')
    tc=args.arm_toolchain_bin or (Path(compiler).parent if compiler else None)
    assert tc is not None,'Pass --arm-toolchain-bin'
    rng=random.Random(0x61411)
    cases=[(RAM+0x4000+a,n,v) for n in range(257) for a in range(8)
           for v in (0,1,0x1234,0xffffffff)]
    cases += [(RAM+0x4000+rng.randrange(32),rng.randrange(8193),rng.getrandbits(32)) for _ in range(2000)]
    cases += [(RAM+0x4000+a,n,v) for n in (16384,32767,32768,32769,65535,65536)
              for a in range(8) for v in (0,0x1234)]
    cases += [(dest,n,0x1234) for n in range(257) for dest in (RAM,RAM+RAM_SIZE-n)]
    cases += [(0,0,0xffffffff)]
    results=[]
    with tempfile.TemporaryDirectory(prefix='mk61-memset-m4-') as temporary:
        work=Path(temporary)
        for lto in (False,True):
            elf=work/'fill.elf';binary=work/'fill.bin'
            command=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m4','-mthumb','-Os','-std=c11',
                '-Wall','-Wextra','-Werror','-fno-builtin','-ffunction-sections','-DARDUINO_ARCH_STM32',
                *(['-flto'] if lto else []),str(ROOT/'code/system_memory_fill_move.c'),
                '-nostdlib','-Wl,--gc-sections,-Ttext=0x08001000,-e,memset','-o',str(elf)]
            subprocess.run(command,check=True)
            subprocess.run([tc/'arm-none-eabi-objcopy','-j','.text','-O','binary',elf,binary],check=True)
            symbols={}
            for line in subprocess.check_output([tc/'arm-none-eabi-nm','-S',elf],text=True).splitlines():
                fields=line.split()
                if len(fields)==4:symbols[fields[3]]=(int(fields[0],16),int(fields[1],16))
            code=binary.read_bytes()
            uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
            uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
            uc.mem_map(0x08000000,0x10000);uc.mem_write(BASE,code)
            uc.mem_map(RAM,RAM_SIZE)
            saved={r:0xA75D184B+r*0x1321 for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
            # Unicorn 2.1.4 memory hooks misexecute this SUBS/IT/STMDB loop.
            # Compare the whole SRAM after each call instead of installing hooks.
            for dest,n,value in cases:
                uc.mem_write(RAM,b'\x5a'*RAM_SIZE)
                for r,v in saved.items():uc.reg_write(r,v)
                for r,v in ((UC_ARM_REG_R0,dest),(UC_ARM_REG_R1,value),(UC_ARM_REG_R2,n),
                            (UC_ARM_REG_SP,SP),(UC_ARM_REG_LR,0x08000001),(UC_ARM_REG_XPSR,0x01000000)):
                    uc.reg_write(r,v)
                uc.emu_start(symbols['memset'][0]|1,0x08000000,count=1000000)
                assert uc.reg_read(UC_ARM_REG_PC)==0x08000000
                assert uc.reg_read(UC_ARM_REG_R0)==dest and uc.reg_read(UC_ARM_REG_SP)==SP
                assert all(uc.reg_read(r)==v for r,v in saved.items())
                expected=bytearray(b'\x5a'*RAM_SIZE)
                if n:expected[dest-RAM:dest-RAM+n]=bytes([value&255])*n
                actual=bytearray(uc.mem_read(RAM,RAM_SIZE))
                stack=12 if 4<=n<16 else 8 if n>=16 else 0
                expected[SP-RAM-stack:SP-RAM]=actual[SP-RAM-stack:SP-RAM]
                assert actual==expected,(lto,hex(dest),n,hex(value),'bounds/content')
            address,size=symbols['mk61_memory_fill_bulk']
            assert address%4==0 and size==82
            result={'lto':lto,'cases':len(cases),'status':'PASS','bulk_bytes':size,
                'bulk_sha256':hashlib.sha256(code[address-BASE:address-BASE+size]).hexdigest()}
            results.append(result);print(json.dumps(result),flush=True)
    if args.output:args.output.write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
