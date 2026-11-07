#!/usr/bin/env python3
"""Thumb updater execution plus the actual boot image's cold/forced entry.

Flash failure tests substitute Flash storage callbacks. Boot execution models
only RCC-ready and polled UART registers; it does not claim electrical timing.
"""
from pathlib import Path
import argparse,json,struct,subprocess,sys,tempfile,zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'sdk/coproc'),str(ROOT/'tools/firmware/picocalc')]
from build_picocalc import compiler_bin
from elf32 import ELF
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_PRIMASK

def cobs(data):
    out=bytearray([0]);at=0;code=1
    for b in data:
        if not b:out[at]=code;at=len(out);out.append(0);code=1
        else:
            out.append(b);code+=1
            if code==255:out[at]=code;at=len(out);out.append(0);code=1
    out[at]=code;return bytes(out)
def decode(data):
    out=bytearray();i=0
    while i<len(data):
        count=data[i];assert count;i+=1;out+=data[i:i+count-1];i+=count-1
        if count<255 and i<len(data):out.append(0)
    return bytes(out)

def core(tool,work):
    boot=ROOT/'ports/picocalc/bios/boot';elfpath=work/'test.elf'
    (work/'support.c').write_text('''#include <stddef.h>
__attribute__((noreturn,noinline)) void test_arm_fail(unsigned line,const char* p){(void)line;(void)p;for(;;)__asm volatile("nop");}
void* memcpy(void*d,const void*s,size_t n){volatile unsigned char*a=d;const unsigned char*b=s;while(n--)*a++=*b++;return d;}
void* memset(void*d,int c,size_t n){volatile unsigned char*a=d;while(n--)*a++=(unsigned char)c;return d;}
int memcmp(const void*a,const void*b,size_t n){const unsigned char*x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
int printf(const char*p,...){(void)p;return 0;}
''')
    (work/'test.ld').write_text('''ENTRY(main)
MEMORY { FLASH(rx) : ORIGIN = 0x08000000, LENGTH = 256K
RAM(rwx) : ORIGIN = 0x20000000, LENGTH = 128K }
SECTIONS { .text : { *(.text*) *(.rodata*) } >FLASH
.data : { *(.data*) } >RAM AT>FLASH
.bss (NOLOAD) : { *(.bss*) *(COMMON) } >RAM }
''')
    cmd=[str(tool/'arm-none-eabi-gcc'),'-mcpu=cortex-m3','-mthumb','-O2','-std=c11','-DM3B_ARM_TEST',
         '-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-Wall','-Wextra','-Werror',
         '-I'+str(boot),str(ROOT/'tests/picocalc_m3_boot_self_test.c'),str(boot/'update.c'),str(boot/'wire.c'),str(work/'support.c'),
         '-Wl,-T,'+str(work/'test.ld'),'-lgcc','-o',str(elfpath)]
    subprocess.run(cmd,check=True);elf=ELF(elfpath);u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    u.mem_map(0x08000000,256*1024);u.mem_map(0x20000000,128*1024)
    for seg in elf.segments:u.mem_write(seg['address'],seg['data'])
    stop=0x0803f000;u.reg_write(UC_ARM_REG_SP,0x2001f000);u.reg_write(UC_ARM_REG_LR,stop|1)
    def fail(uc,address,size,unused):
        ptr=uc.reg_read(UC_ARM_REG_R1)
        raise AssertionError((uc.reg_read(UC_ARM_REG_R0),bytes(uc.mem_read(ptr,180)).split(b'\0')[0]))
    at=elf.symbols['test_arm_fail']['value']&~1;u.hook_add(UC_HOOK_CODE,fail,begin=at,end=at)
    u.emu_start(elf.symbols['main']['value']|1,stop,count=200_000_000)
    assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_R0)==0
    return 'CORTEX_M3_UPDATE_FAULT_MODEL_PASS'

def actual_boot(folder):
    binary=(folder/'bootstrap.bin').read_bytes();app=0x08002000
    sp,entry=struct.unpack_from('<II',binary,8192);out={}
    raw=struct.pack('<BBHHH',0x42,1,17,0,0);packet=b'\0'+cobs(raw+struct.pack('<I',zlib.crc32(raw)))+b'\0'
    for case in ['valid','invalid','forced','resident_entry']:
        u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        u.mem_map(0x08000000,65536);u.mem_map(0x20000000,20480)
        u.mem_map(0x40000000,0x30000);u.mem_map(0xe000e000,0x2000)
        u.mem_write(0x08000000,binary)
        if case=='invalid':u.mem_write(0x0800f420,b'\0\0\0\0')
        if case=='forced':u.mem_write(0x20004fe0,struct.pack('<II',0x5542334d,0xaabdccb2))
        queue=list(packet);transmit=bytearray();arrived=[]
        def read(uc,access,address,size,value,unused):
            if address==0x40021000:uc.mem_write(address,struct.pack('<I',3))
            if address==0x40004800:
                uc.mem_write(address,struct.pack('<I',0xc0|(0x20 if queue else 0)))
            if address==0x40004804 and queue:uc.mem_write(address,struct.pack('<I',queue.pop(0)))
        def write(uc,access,address,size,value,unused):
            if address==0x40004804:
                transmit.append(value&255)
                if len(transmit)>1 and transmit[-1]==0:uc.emu_stop()
        def app_entry(uc,address,size,unused):arrived.append(address);uc.emu_stop()
        u.hook_add(UC_HOOK_MEM_READ,read)
        u.hook_add(UC_HOOK_MEM_WRITE,write)
        u.hook_add(UC_HOOK_CODE,app_entry,begin=entry&~1,end=entry&~1)
        bootsp,bootentry=struct.unpack_from('<II',binary)
        u.reg_write(UC_ARM_REG_SP,bootsp)
        start=bootentry
        if case=='resident_entry':
            resident=ELF(folder/'base/source/build/picocalc_BIOS_jcs.elf')
            start=resident.symbols['bios_boot_enter']['value']
        u.emu_start(start,0,count=10_000_000)
        if case=='valid':
            assert arrived==[entry&~1] and u.reg_read(UC_ARM_REG_SP)==sp
            assert u.reg_read(UC_ARM_REG_PRIMASK)==0
            assert struct.unpack('<I',u.mem_read(0xe000ed08,4))[0]==app
            assert not transmit
        else:
            assert not arrived and transmit[:1]==b'\0' and transmit[-1:]==b'\0',transmit
            reply=decode(transmit[1:-1]);assert reply[:2]==bytes([0x42,0x81])
            assert zlib.crc32(reply[:-4])==struct.unpack_from('<I',reply,len(reply)-4)[0]
            assert struct.unpack_from('<I',reply,8)[0]==0
            assert struct.unpack_from('<I',reply,12+5*4)[0]==(case in ('forced','resident_entry'))
            assert struct.unpack('<I',u.mem_read(0x40010810,4))[0]&(1<<13)
        out[case]='PASS'
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--firmware',type=Path,required=True)
    ap.add_argument('--toolchain');ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='m3b-arm-') as tmp:
        result=dict(core=core(compiler_bin(args.toolchain),Path(tmp)),boot=actual_boot(args.firmware),physical_io=False,
                    physical_timing=False,flash_and_uart_peripherals_modeled=True)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
