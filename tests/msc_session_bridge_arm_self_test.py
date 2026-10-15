#!/usr/bin/env python3
"""Run the real foreground MSC resource lifecycle on an emulated Cortex-M4."""
import argparse,json,shlex,subprocess,tempfile
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_CPU_ARM_CORTEX_M4
from check_stm32_vectors import ElfImage

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('compile_commands',type=Path);p.add_argument('--json',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];entries=json.loads(a.compile_commands.read_text())
    e=next(e for e in entries if Path(e['file']).name=='usb_mass_storage.cpp');raw=e.get('arguments') or shlex.split(e['command'])
    flags=[];i=1
    while i<len(raw):
        if raw[i].startswith(('-D','-I','-mcpu=','-mthumb','-mfpu=','-mfloat-abi=')):
            flags.append(raw[i])
        elif raw[i]=='-include':flags.extend(raw[i:i+2]);i+=1
        i+=1
    assert '-DSTM32F411xE' in flags,'This fixture qualifies the temporary F411 transport'
    sources=['tests/msc_session_bridge_fixture.cpp','code/shared_memory.cpp','code/exclusive_buffer.cpp',
             'code/usbd_msc.c','code/usbd_msc_bot.c','code/usbd_msc_scsi.c','code/usbd_msc_data.c',
             'code/system_memory.c','code/system_memory_fill_move.c']
    results=[]
    with tempfile.TemporaryDirectory(prefix='mk61-msc-bridge-') as tmp:
        tmp=Path(tmp);objects=[]
        for n,name in enumerate(sources):
            obj=tmp/f'{n}.o';objects.append(str(obj));cpp=name.endswith('.cpp')
            subprocess.run([raw[0] if cpp else raw[0].replace('g++','gcc'),*flags,'-Os','-Wall','-Wextra','-Werror','-fno-builtin',
                '-ffunction-sections','-fdata-sections',*(['-fno-exceptions','-fno-rtti','-fno-use-cxa-atexit','-std=gnu++17'] if cpp else ['-std=gnu11']),
                '-c',str(root/name),'-o',str(obj)],check=True)
        linker=tmp/'test.ld';linker.write_text('MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 512K\nRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K }\n'
            'SECTIONS { .text : { *(.text*) *(.rodata*) } > FLASH\n.data : { *(.data*) } > RAM AT> FLASH\n'
            '.bss : { *(.bss*) *(COMMON) } > RAM\n_end = .; __mk61_dynamic_begin = ALIGN(8); __mk61_dynamic_end = 0x2001BF00; }\n')
        elf=tmp/'test.elf';subprocess.run([raw[0],'-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-nostdlib',*objects,
            '-Wl,--gc-sections,-u,test_msc_bridge_cycles,-u,test_msc_bridge_failures,-u,test_msc_bridge_oom,-u,test_msc_bridge_pending_cancel,-u,test_msc_bridge_reset_during_io,-T,'+str(linker),'-o',str(elf)],check=True)
        image=ElfImage(elf)
        for name in sorted(n for n in image.symbols if n.startswith('test_msc_bridge_')):
            u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
            u.mem_map(0x08000000,0x80000);u.mem_map(0x20000000,0x20000);image.load(u)
            stop=0x0807F000;sp=0x2001FFF0;u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,stop|1)
            u.emu_start(image.symbols[name]|1,stop,count=100000000)
            line=u.reg_read(UC_ARM_REG_R0);assert u.reg_read(UC_ARM_REG_PC)==stop and not line,(name,line,hex(u.reg_read(UC_ARM_REG_PC)))
            assert u.reg_read(UC_ARM_REG_SP)==sp
            results.append(dict(test=name,status='PASS'));print(name,'PASS',flush=True)
    if a.json:a.json.write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
