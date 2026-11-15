#!/usr/bin/env python3
"""Test APP reservations/fallback against ARM newlib and actual heap bounds."""
import argparse
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_CPU_ARM_CORTEX_M0,UC_ARM_REG_R0,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
from check_stm32_vectors import ElfImage
from tools.firmware.picocalc.build_picocalc import compiler_bin

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware',type=Path,required=True)
    parser.add_argument('--toolchain',type=Path)
    args=parser.parse_args()
    firmware=ElfImage(args.firmware)
    first,last=(firmware.symbols[name] for name in ('__end__','__HeapLimit'))
    assert 0x20000000<=first<last<=0x20038000
    with tempfile.TemporaryDirectory(prefix='picocalc-app-arena-') as directory:
        work=Path(directory);linker=work/'heap.ld';elf=work/'heap.elf'
        linker.write_text(f'''MEMORY {{ FLASH (rx) : ORIGIN = 0x10000000, LENGTH = 2M
 RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 256K }}
SECTIONS {{ .text : {{ *(.text*) *(.rodata*) }} > FLASH
 .data : {{ *(.data*) }} > RAM
 .bss (NOLOAD) : {{ *(.bss*) *(COMMON) }} > RAM
 __end__ = {first:#x}; __HeapLimit = {last:#x};
 ASSERT(. < __end__, "test globals overlap heap") }}\n''')
        toolchain=compiler_bin(args.toolchain)
        command=[str(toolchain/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-Os',
                 '-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections',
                 '-DPICO_ON_DEVICE=1','-DMK61_USE_M0_EABI=0','-DMK61_CORE_STANDALONE=1',
                 '-I'+str(ROOT/'code'),'-I'+str(ROOT/'ports/picocalc'),
                 str(ROOT/'tests/fixtures/picocalc_app_arena_probe.cpp'),
                 str(ROOT/'ports/picocalc/native_runtime.cpp'),str(ROOT/'code/shared_memory_buffer.cpp'),
                 '-nostartfiles','-Wl,--gc-sections,-e,arena_trial','-T'+str(linker),'-o',str(elf)]
        subprocess.run(command,check=True,capture_output=True,text=True)
        image=ElfImage(elf);uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
        uc.mem_map(0x10000000,0x200000);uc.mem_map(0x20000000,0x40000);image.load(uc)
        def guard(uc,access,address,size,value,user):
            assert 0x20000000<=address and address+size<=first or \
                first<=address and address+size<=last or 0x20039000<=address and address+size<=0x2003fff0, \
                ('out-of-bounds write',hex(address),size)
        uc.hook_add(UC_HOOK_MEM_WRITE,guard)
        uc.reg_write(UC_ARM_REG_SP,0x2003fff0);uc.reg_write(UC_ARM_REG_LR,0x101ff001)
        uc.reg_write(UC_ARM_REG_XPSR,0x01000000)
        uc.emu_start(image.symbols['arena_trial']|1,0x101ff000,count=20000000)
        assert uc.reg_read(UC_ARM_REG_PC)==0x101ff000,'trial did not return'
        result=uc.reg_read(UC_ARM_REG_R0)
        assert result==0, f'ARM heap/arena trial failed at step {result}'
        assert uc.reg_read(UC_ARM_REG_SP)==0x2003fff0
        arena,used,blocks,top=struct.unpack('<4I',bytes(uc.mem_read(image.symbols['warm_allocator'],16)))
        assert arena==last-first and blocks==2 and top<12000
        print(f'ARM newlib APP arena, real {last-first}-byte heap: reproduced retained-timer fragmentation, '
              f'free chunks {arena-used-top} + {top} bytes, 8 clean warm runs after timer release '
              'and split fallback PASS')

if __name__=='__main__':main()
