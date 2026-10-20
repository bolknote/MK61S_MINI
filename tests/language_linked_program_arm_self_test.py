#!/usr/bin/env python3
"""Actual M4 code: raw/paged, unaligned images and relocated continuations.

This is a bare ARM fixture, not an APP-size qualification or hardware timing.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from check_stm32_vectors import ElfImage

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain-bin',type=Path,required=True)
    a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='mk61-linked-arm-') as temporary:
        work=Path(temporary)
        sources=('5 Z=10;GOTO Z\n10 A=0;FOR I=1 TO 100;A=A+I;NEXT I;INPUT C;.RE=2;END\n',
                 '1.10 S A=7;S .RE=3;E\n',
                 '10 B=A+C;Z=30;GOTO Z\n20 END\n30 .RE=0;END\n')
        manifest={'entry':1,'members':[]}
        for i,source in enumerate(sources):
            path=work/f'{i}.txt';path.write_text(source)
            manifest['members'].append({'symbol':i+1,'language':'focal' if i==1 else 'basic','path':path.name})
        (work/'members.json').write_text(json.dumps(manifest))
        package=work/'program.lvp'
        subprocess.run([sys.executable,str(ROOT/'tools/build_vm_program.py'),str(work/'members.json'),'-o',str(package),'--compiler','clang++'],check=True)
        flags=['-std=c++17','-Os','-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard',
            '-fno-builtin','-fno-exceptions','-fno-rtti','-fno-lto','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-ffunction-sections','-fdata-sections','-DMK61_NATIVE_RUNTIME=1','-DMK61_USE_NATIVE_EABI=1',
            '-DMK61_USE_COMPACT_LIBM=1','-DMK61_BUILD_LANGUAGE_VM_MODULE','-I'+str(ROOT/'code')]
        files=['tests/fixtures/language_linked_program_arm.cpp','code/language_linked_program.cpp',
            'code/language_bytecode.cpp','code/language_vm.cpp','code/native_eabi.cpp','code/native_eabi_arm.S','code/native_eabi_fixed.S']
        objects=[]
        for i,file in enumerate(files):
            out=work/f'{i}.o';subprocess.run([str(a.toolchain_bin/'arm-none-eabi-g++'),*flags,'-c',str(ROOT/file),'-o',str(out)],check=True);objects.append(str(out))
        elf_path=work/'probe.elf'
        subprocess.run([str(a.toolchain_bin/'arm-none-eabi-g++'),*flags,'-nostdlib','-Wl,--gc-sections,-Ttext=0x08000000,-Tdata=0x20000000,--entry=linked_probe',*objects,'-o',str(elf_path)],check=True)
        elf=ElfImage(elf_path);image=package.read_bytes();stop=0x080FF000
        for mode in range(8):
            for shift in (0,1):
                uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
                uc.mem_map(0x08000000,0x100000);uc.mem_map(0x20000000,0x20000)
                uc.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
                elf.load(uc);address=0x20010000+shift;uc.mem_write(address,image)
                low=0x2001FFF0
                def write(machine,access,at,size,value,user):
                    nonlocal low
                    del machine,access,value,user
                    assert (0x20000000<=at and at+size<=0x20008000) or (0x2001C000<=at and at+size<=0x2001FFF0),(hex(at),size)
                    if at>=0x2001C000:low=min(low,at)
                uc.hook_add(UC_HOOK_MEM_WRITE,write)
                for reg,val in ((UC_ARM_REG_R0,address),(UC_ARM_REG_R1,len(image)),(UC_ARM_REG_R2,mode),
                    (UC_ARM_REG_SP,0x2001FFF0),(UC_ARM_REG_LR,stop|1)):uc.reg_write(reg,val)
                uc.emu_start(elf.symbols['linked_probe'],stop,timeout=180000000,count=500000000)
                result=uc.reg_read(UC_ARM_REG_R0)
                assert uc.reg_read(UC_ARM_REG_PC)==stop and result==0x61A0,(mode,shift,hex(result),hex(uc.reg_read(UC_ARM_REG_PC)))
                assert bytes(uc.mem_read(address,len(image)))==image
                print('linked ARM mode',mode,'unaligned',shift,'stack bytes',0x2001FFF0-low,'PASS',flush=True)
        print('Actual ARM linked VM: 16 configurations, generic/whole entry, INPUT/budget relocation, dynamic jumps and immutable images PASS')

if __name__=='__main__':main()
