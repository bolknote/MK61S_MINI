#!/usr/bin/env python3
"""Execute every SDK trampoline on M0+/M4; preserve arguments and tail returns."""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR,
    UC_ARM_REG_PC, UC_ARM_REG_XPSR)
from check_stm32_vectors import ElfImage

ROOT=Path(__file__).resolve().parents[1]
BASE=0x20000000
TABLE=BASE+0x8000
TARGET=BASE+0x9000
STOP=BASE+0xA000
SP=BASE+0xF000

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    compiler=shutil.which('arm-none-eabi-gcc')
    tc=args.arm_toolchain_bin or (Path(compiler).parent if compiler else None)
    assert tc is not None,'Pass --arm-toolchain-bin'
    slots=re.findall(r'^MK61_RUNTIME(_ISO_C)?\((\w+)',(ROOT/'code/loadable_system_runtime.def').read_text(),re.M)
    results=[]
    with tempfile.TemporaryDirectory(prefix='mk61-runtime-arm-') as temporary:
        work=Path(temporary);source=work/'pointer.c';elf=work/'runtime.elf'
        source.write_text('void *mk61_app_runtime;\n')
        for cpu,model in [('cortex-m0plus',UC_CPU_ARM_CORTEX_M0),('cortex-m4',UC_CPU_ARM_CORTEX_M4)]:
            subprocess.run([str(tc/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-Os','-nostdlib',
                '-DMK61_RUNTIME_POINTER=mk61_app_runtime','-I'+str(ROOT/'code'),str(source),
                str(ROOT/'sdk/portable/system/runtime.S'),'-Wl,-Ttext=0x20000000,-e,__aeabi_dadd',
                '-o',str(elf)],check=True)
            image=ElfImage(elf)
            uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);uc.ctl_set_cpu_model(model)
            uc.mem_map(BASE,0x10000);image.load(uc)
            uc.mem_write(image.symbols['mk61_app_runtime'],struct.pack('<I',TABLE))
            for slot in range(len(slots)):
                uc.mem_write(TABLE+4*slot,struct.pack('<I',(TARGET+16*slot)|1))
                # Set all four result registers; uldivmod returns through r0-r3.
                uc.mem_write(TARGET+16*slot,bytes.fromhex('11202221332244237047'))
            for slot,(iso,name) in enumerate(slots):
                preserved={r:(0xA75D184B+r*0x1321)&0xFFFFFFFF for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
                args_regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
                arguments={r:0x12345678+i*0x11111111 for i,r in enumerate(args_regs)}
                for r,v in (preserved|arguments|{UC_ARM_REG_SP:SP,UC_ARM_REG_LR:STOP|1,UC_ARM_REG_XPSR:0x01000000}).items():uc.reg_write(r,v)
                target=TARGET+16*slot
                uc.emu_start(image.symbols[name]|1,target,count=30)
                assert uc.reg_read(UC_ARM_REG_PC)==target,(cpu,name,'wrong slot')
                for r in args_regs[:3 if iso else 4]:assert uc.reg_read(r)==arguments[r],(cpu,name,'argument')
                assert uc.reg_read(UC_ARM_REG_SP)==SP and uc.reg_read(UC_ARM_REG_LR)==STOP|1
                assert all(uc.reg_read(r)==v for r,v in preserved.items())
                uc.emu_start(target|1,STOP,count=10)
                assert uc.reg_read(UC_ARM_REG_PC)==STOP and uc.reg_read(UC_ARM_REG_SP)==SP
                assert [uc.reg_read(r) for r in args_regs]==[0x11,0x22,0x33,0x44],(cpu,name,'result')
                assert all(uc.reg_read(r)==v for r,v in preserved.items())
            row=dict(cpu=cpu,slots=len(slots),status='PASS',memset_trampoline_bytes=image.sizes['memset'])
            results.append(row);print(json.dumps(row),flush=True)
    if args.output:args.output.write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
