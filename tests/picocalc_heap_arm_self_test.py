#!/usr/bin/env python3
"""Exercise Pico's heap initialization with the actual ARM newlib allocator."""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_CPU_ARM_CORTEX_M0,UC_ARM_REG_R0,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
from check_stm32_vectors import ElfImage

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc import compiler_bin

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain',type=Path);parser.add_argument('--json',type=Path)
    parser.add_argument('--firmware',type=Path,help='Use the actual linked heap bounds instead of the original regression addresses')
    args=parser.parse_args();toolchain=compiler_bin(args.toolchain)
    heap_start,heap_limit=0x2002fba8,0x20038000
    if args.firmware:
        firmware=ElfImage(args.firmware)
        heap_start,heap_limit=(firmware.symbols[name] for name in ('__end__','__HeapLimit'))
        assert 0x20000000<=heap_start<heap_limit<=0x20038000
    with tempfile.TemporaryDirectory(prefix='picocalc-heap-') as directory:
        work=Path(directory);linker=work/'heap.ld';elf=work/'heap.elf'
        linker.write_text('''MEMORY {
 FLASH (rx) : ORIGIN = 0x10000000, LENGTH = 2M
 RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 256K
}
SECTIONS {
 .text : { *(.text*) *(.rodata*) } > FLASH
 .data : { *(.data*) } > RAM
 .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
 __end__ = 0x2002fba8;
 __HeapLimit = 0x20038000;
 ASSERT(. < __end__, "test globals overlap heap")
}
'''.replace('0x2002fba8',hex(heap_start)).replace('0x20038000',hex(heap_limit)))
        command=[str(toolchain/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-Os',
            '-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections',
            '-DPICO_ON_DEVICE=1','-DMK61_USE_M0_EABI=0','-I'+str(ROOT/'code'),'-I'+str(ROOT/'ports/picocalc'),
            str(ROOT/'tests/fixtures/picocalc_heap_probe.cpp'),str(ROOT/'ports/picocalc/native_runtime.cpp'),
            '-nostartfiles','-Wl,--gc-sections,-e,heap_trial','-T'+str(linker),'-o',str(elf)]
        built=subprocess.run(command,capture_output=True,text=True)
        assert built.returncode==0,built.stdout+built.stderr
        image=ElfImage(elf);results=[]
        for initialize in (0,1):
            uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
            uc.mem_map(0x10000000,0x200000);uc.mem_map(0x20000000,0x40000);image.load(uc)
            def guard(uc,access,address,size,value,user):
                assert 0x20000000<=address and address+size<=heap_start or \
                    heap_start<=address and address+size<=heap_limit or \
                    0x20039000<=address and address+size<=0x2003fff0,('write outside SRAM objects/heap/stack',hex(address),size)
            uc.hook_add(UC_HOOK_MEM_WRITE,guard)
            uc.reg_write(UC_ARM_REG_R0,initialize);uc.reg_write(UC_ARM_REG_SP,0x2003fff0)
            uc.reg_write(UC_ARM_REG_LR,0x101ff001);uc.reg_write(UC_ARM_REG_XPSR,0x01000000)
            uc.emu_start(image.symbols['heap_trial']|1,0x101ff000,count=2000000)
            assert uc.reg_read(UC_ARM_REG_PC)==0x101ff000,'trial did not return'
            assert uc.reg_read(UC_ARM_REG_SP)==0x2003fff0,'stack not restored'
            results.append(uc.reg_read(UC_ARM_REG_R0))
        report=dict(passed=results[1]==60 and (args.firmware is not None or results[0]==32),heap_bytes=heap_limit-heap_start,
            heap_start=hex(heap_start),heap_limit=hex(heap_limit),
            without_initialization=results[0],with_initialization=results[1],
            initialized_checks=dict(markdown_allocated=bool(results[1]&4),image_allocated=bool(results[1]&8),
                large_app_allocated=bool(results[1]&16),all_released=bool(results[1]&32)),
            required_allocations=dict(markdown_bytes=15296,image_bytes=8326,app_bytes=30000),
            writes_bounded=True)
        if args.json:
            args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        assert report['passed'],results

if __name__=='__main__':main()
