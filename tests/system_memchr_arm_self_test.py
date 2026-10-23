#!/usr/bin/env python3
"""Execute memchr ARM code: earliest unsigned-byte match, exact bounds, ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
from check_stm32_vectors import ElfImage
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_CPU_ARM_CORTEX_M4,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R11,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR)

def verify(elf,cpu,names,input_address=0x20040000,indirect_target=None):
    image=ElfImage(elf)
    def function_size(name):
        if image.sizes[name]:return image.sizes[name]
        start=image.symbols[name]&~1
        if name+'_end' in image.symbols:return (image.symbols[name+'_end']&~1)-start
        section=next(s for s in image.sections if s[2]&4 and s[3]<=start<s[3]+s[5])
        end=min([s&~1 for n,s in image.symbols.items() if image.sizes[n] and start<(s&~1)<section[3]+section[5]]+[section[3]+section[5]])
        return end-start
    sizes_by_name={n:function_size(n) for n in names}
    machine=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if cpu=='m0' else UC_CPU_ARM_CORTEX_M4)
    for address,size in ((0x20000000,0x100000),(0x08000000,0x100000),(0x10000000,0x200000),(0x30000000,4096)):
        machine.mem_map(address,size)
    image.load(machine)
    stop,stack,buffer=0x30000000,0x200fe000,input_address
    indirect_reads=[]
    if indirect_target:
        table=0x200f0000;global_pointer=image.symbols['bench_search_runtime']
        machine.mem_write(global_pointer,struct.pack('<I',table))
        machine.mem_write(table+104,struct.pack('<I',image.symbols[indirect_target]|1))
        target=image.symbols[indirect_target]&~1
        indirect_reads=[(global_pointer,global_pointer+4),(table,table+108),(target,target+function_size(indirect_target))]
    sizes=[*range(130),255,256,257,511,512,513,1023,1024,1025,4095,4096,4097,16384,65536]
    cases=[]
    for n in sizes:
        positions=range(n) if n<=16 else sorted({0,1,2,3,4,7,8,15,16,n//2,n-1})
        for offset in range(8):
            for value in (0,1,127,128,255):
                cases.append((n,offset,value,-1,False))
                for at in positions:cases.append((n,offset,value,at,True))
    for value in [*range(256),-513,-1,256,511,0x123400A5]:
        for offset in range(4):
            for at in (-1,0,1,2,3,4,7,8,15,16,31,32,63):
                cases.append((64,offset,value,at,True))
    rng=random.Random(610422)
    for _ in range(500):
        n=rng.randrange(8193)
        cases.append((n,rng.randrange(16),rng.randrange(-1024,1024),rng.randrange(n) if n else -1,False))
    saved={reg:0x72816201+reg*314 for reg in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    active={}
    def access(_machine,kind,address,size,_value,_user):
        if cpu=='m0':assert size in (1,2,4) and address%size==0,('alignment',hex(address),size,active)
        on_stack=stack-64<=address and address+size<=stack
        if kind==UC_MEM_WRITE:
            assert on_stack,('memchr wrote outside stack',hex(address),size,active)
        else:
            assert on_stack or any(a<=address and address+size<=b for a,b in active['read']),('read beyond input span',hex(address),size,active)
    machine.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)
    def call(name,pointer,value,n,expected):
        start=image.symbols[name]&~1
        active.update(name=name,n=n,value=value,pointer=pointer,
            read=[(pointer,pointer+n),(start,start+sizes_by_name[name])]+(indirect_reads if name=='indirect_search' else []))
        for reg,initial in saved.items():machine.reg_write(reg,initial)
        for reg,initial in ((UC_ARM_REG_R0,pointer),(UC_ARM_REG_R1,value&0xffffffff),(UC_ARM_REG_R2,n),
                (UC_ARM_REG_SP,stack),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)):
            machine.reg_write(reg,initial)
        try:machine.emu_start(start|1,stop,count=1500000)
        except Exception:
            print('FAIL',active,hex(machine.reg_read(UC_ARM_REG_PC)),flush=True)
            raise
        assert machine.reg_read(UC_ARM_REG_PC)==stop,(active,'return')
        assert machine.reg_read(UC_ARM_REG_R0)==expected,(active,'result',hex(machine.reg_read(UC_ARM_REG_R0)),hex(expected))
        assert machine.reg_read(UC_ARM_REG_SP)==stack,(active,'stack')
        assert all(machine.reg_read(reg)==initial for reg,initial in saved.items()),(active,'callee saved')
    results=[]
    for name in names:
        for n,offset,value,at,multiple in cases:
            pointer=buffer+offset
            # Alternating x=1 / x=0x80 catches borrow propagation in the SWAR mask.
            wanted=value&255
            data=bytearray(bytes((wanted^1,wanted^128))*(n//2+1))[:n]
            if at>=0:
                data[at]=wanted
                if multiple and at+1<n:data[at+1:]=bytes([wanted])*(n-at-1)
            machine.mem_write(pointer,bytes(data))
            # Equal sentinel bytes immediately outside the span must be ignored.
            machine.mem_write(pointer-1,bytes([wanted]));machine.mem_write(pointer+n,bytes([wanted]))
            call(name,pointer,value,n,pointer+at if at>=0 else 0)
        call(name,0,-1,0,0)
        row=dict(name=name,cases=len(cases)+1,bytes=sizes_by_name[name],status='PASS')
        results.append(row);print(row,flush=True)
    return dict(cpu=cpu,input_address=hex(input_address),indirect_target=indirect_target,
        elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),results=results)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--cpu',choices=('m0','m4'),required=True)
    p.add_argument('--names',nargs='+',default=['memchr'])
    p.add_argument('--output',type=Path)
    p.add_argument('--input-address',type=lambda s:int(s,0),default=0x20040000)
    p.add_argument('--indirect-target')
    a=p.parse_args();result=verify(a.elf,a.cpu,a.names,a.input_address,a.indirect_target)
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
