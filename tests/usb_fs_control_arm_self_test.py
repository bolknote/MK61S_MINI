#!/usr/bin/env python3
"""Compile and execute real EP0/descriptor/queue sources with a fake USB wire."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import (UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_R0, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
    UC_CPU_ARM_CORTEX_M4)
from check_stm32_vectors import ElfImage


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('compile_commands',type=Path)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    entries=json.loads(args.compile_commands.read_text())
    command=next(e for e in entries if Path(e['file']).name=='stm32f4_usbd_core.c')
    raw=command.get('arguments') or shlex.split(command['command'])
    flags=[];i=1
    while i<len(raw):
        if raw[i].startswith(('-D','-I','-mcpu=','-mthumb','-mfpu=','-mfloat-abi=')):
            flags.append(raw[i])
        elif raw[i]=='-include':flags.extend(raw[i:i+2]);i+=1
        i+=1
    sources=['tests/usb_fs_control_fixture.c','code/stm32f4_usbd_core.c',
             'code/stm32f4_usbd_ioreq.c','code/stm32f4_usbd_ctlreq.c',
             'code/stm32f4_usbd_desc.c','code/stm32f4_cdc_queue.c',
             'code/system_memory.c','code/system_memory_fill_move.c']
    with tempfile.TemporaryDirectory(prefix='mk61-usb-fs-') as folder:
        folder=Path(folder);objects=[]
        for index,source in enumerate(sources):
            obj=folder/f'{index}.o';objects.append(str(obj))
            subprocess.run([raw[0],*flags,'-DMK61_USB_BUILD_CTLREQ=1','-Os',
                '-Wall','-Wextra','-Werror','-fno-builtin','-ffunction-sections','-fdata-sections','-std=gnu11',
                '-c',str(root/source),'-o',str(obj)],check=True)
        linker=folder/'test.ld'
        linker.write_text('MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1M\n'
            'RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K }\n'
            'SECTIONS { .text : { *(.text*) *(.rodata*) } > FLASH\n'
            '.data : { *(.data*) } > RAM AT> FLASH\n'
            '.bss : { *(.bss*) *(COMMON) } > RAM }\n')
        elf=folder/'test.elf'
        subprocess.run([raw[0],'-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16',
            '-mfloat-abi=hard','-nostdlib',*objects,'-Wl,-T,'+str(linker),
            '-o',str(elf)],check=True)
        image=ElfImage(elf)
        for function in ['test_control','test_descriptors','test_queues']:
            u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
            u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
            u.mem_map(0x08000000,0x100000);u.mem_map(0x20000000,0x20000)
            u.mem_map(0x1fff7000,0x1000)
            # Matches the Classic CDC identity, including its legacy UID encoding.
            import struct
            u.mem_write(0x1fff7a10,struct.pack('<III',0x1068336b,0x47310000,0x10000000))
            image.load(u);stop=0x080ff000;sp=0x2001fff0
            u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,stop|1)
            u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
            u.emu_start(image.symbols[function]|1,stop,count=100000000)
            line=u.reg_read(UC_ARM_REG_R0)
            assert u.reg_read(UC_ARM_REG_PC)==stop and not line,(function,'fixture line',line,hex(u.reg_read(UC_ARM_REG_PC)))
            assert u.reg_read(UC_ARM_REG_SP)==sp
            print(function,'PASS')
    print('EP0 enumeration/segmentation/ZLP/reset/suspend, bounded descriptors, 50000 queue transitions PASS')

if __name__=='__main__':main()
