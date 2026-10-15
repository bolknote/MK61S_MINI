#!/usr/bin/env python3
"""Execute real MSC/BOT/SCSI with a fake wire/disk, for F411 and F401."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import (UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_R0, UC_ARM_REG_IPSR, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_CPU_ARM_CORTEX_M4)
from check_stm32_vectors import ElfImage


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('compile_commands',type=Path)
    p.add_argument('--json',type=Path)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    entries=json.loads(a.compile_commands.read_text())
    command=next(e for e in entries if Path(e['file']).name=='usbd_msc.c')
    raw=command.get('arguments') or shlex.split(command['command'])
    flags=[];i=1
    while i<len(raw):
        if raw[i].startswith(('-D','-I','-mcpu=','-mthumb','-mfpu=','-mfloat-abi=')):
            if not raw[i].startswith(('-DSTM32F411xE','-DSTM32F401xC')):flags.append(raw[i])
        elif raw[i]=='-include':flags.extend(raw[i:i+2]);i+=1
        i+=1
    sources=['tests/msc_bot_scsi_fixture.c','code/usbd_msc.c','code/usbd_msc_bot.c',
             'code/usbd_msc_scsi.c','code/usbd_msc_data.c',
             'code/system_memory.c','code/system_memory_fill_move.c']
    results=[]
    with tempfile.TemporaryDirectory(prefix='mk61-msc-') as folder:
        folder=Path(folder)
        for target in ['STM32F411xE','STM32F401xC']:
            ram_bytes=0x20000 if target=='STM32F411xE' else 0x10000
            objects=[]
            for index,source in enumerate(sources):
                obj=folder/f'{index}.o';objects.append(str(obj))
                subprocess.run([raw[0],*flags,'-D'+target,'-Os','-Wall','-Wextra','-Werror',
                    '-fno-builtin','-ffunction-sections','-fdata-sections','-std=gnu11',
                    '-c',str(root/source),'-o',str(obj)],check=True)
            linker=folder/'test.ld'
            linker.write_text('MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1M\n'
                f'RAM (rwx) : ORIGIN = 0x20000000, LENGTH = {ram_bytes} }}\n'
                'SECTIONS { .text : { *(.text*) *(.rodata*) } > FLASH\n'
                '.data : { *(.data*) } > RAM AT> FLASH\n'
                '.bss : { *(.bss*) *(COMMON) } > RAM }\n')
            elf=folder/'test.elf'
            subprocess.run([raw[0],'-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16',
                '-mfloat-abi=hard','-nostdlib',*objects,'-Wl,-T,'+str(linker),
                '-o',str(elf)],check=True)
            image=ElfImage(elf)
            functions=sorted(n for n in image.symbols if n.startswith('test_msc_'))
            for name in functions:
                u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
                u.mem_map(0x08000000,0x100000);u.mem_map(0x20000000,ram_bytes);image.load(u)
                stop=0x080ff000;sp=0x20000000+ram_bytes-16
                u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,stop|1)
                u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
                if name == 'test_msc_session_in_irq':
                    u.emu_start(image.symbols['msc_prepare_irq_test']|1,stop,count=100000000)
                    assert u.reg_read(UC_ARM_REG_R0)==0
                    u.reg_write(UC_ARM_REG_LR,stop|1)
                    u.reg_write(UC_ARM_REG_IPSR,16)
                u.emu_start(image.symbols[name]|1,stop,count=100000000)
                line=u.reg_read(UC_ARM_REG_R0)
                assert u.reg_read(UC_ARM_REG_PC)==stop and not line,(target,name,'fixture line',line,hex(u.reg_read(UC_ARM_REG_PC)))
                assert u.reg_read(UC_ARM_REG_SP)==sp
                results.append(dict(target=target,test=name,status='PASS'));print(target,name,'PASS',flush=True)
    if a.json:a.json.write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
