#!/usr/bin/env python3
"""Execute the real shared SDK startup/resolver/veneer on old/new ARM ABIs.

This is functional emulation, never a hardware cycle measurement. Old 28-byte
services and 26-slot tables have exact read bounds, enforced on every load.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0,UC_CPU_ARM_CORTEX_M4,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
    UC_ARM_REG_R4,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR)

def verify(elf,cpu):
    e=ElfImage(elf);u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if cpu=='m0' else UC_CPU_ARM_CORTEX_M4)
    u.mem_map(0x20000000,0x100000);u.mem_map(0x30000000,4096);e.load(u)
    stop,query,resident,cap=0x30000000,0x30000100,0x30000200,0x30000300
    stack,api,services,table,buffer=0x200e0000,0x200f0000,0x200f1000,0x200f2000,0x20040000
    optional=e.symbols['mk61_optional_memchr'];fallback=e.symbols['mk61_memchr_fallback']|1
    initial=struct.unpack('<I',u.mem_read(optional,4))[0]
    u.mem_write(query,b'\x70\x47');u.mem_write(cap,b'\x70\x47')
    u.mem_write(resident,b'\x00\x4b\x18\x47'+struct.pack('<I',fallback))
    code=e.named_sections['.module_image'];active={};counters={}
    saved={reg:0x19376101+reg*314 for reg in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    def hook_code(_u,address,_size,_user):
        if address==query:
            assert (u.reg_read(UC_ARM_REG_R0),u.reg_read(UC_ARM_REG_R1))==(1,2)
            counters['query']+=1;u.reg_write(UC_ARM_REG_R0,services if active['present'] else 0)
        elif address==cap:
            assert u.reg_read(UC_ARM_REG_R0)==26
            assert all(u.reg_read(r)==0 for r in (UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3))
            counters['cap']+=1;u.reg_write(UC_ARM_REG_R0,1<<8)
        elif address==resident:counters['resident']+=1
    def access(_u,kind,address,size,_value,_user):
        if cpu=='m0':assert size in (1,2,4) and address%size==0,('alignment',hex(address),size,active)
        on_stack=stack-256<=address and address+size<=stack+4
        if kind==UC_MEM_WRITE:
            allowed=[(optional,optional+4)]
            if active['stage']=='init':
                allowed += [(e.symbols[n],e.symbols[n]+4) for n in ('mk61_api','mk61_app_image_crc','mk61_app_current_kind','mk61_app_runtime') if n in e.symbols]
            assert on_stack or any(a<=address and address+size<=b for a,b in allowed),('write',hex(address),size,active)
        else:
            ranges=[(code[3],code[3]+code[5]),(e.symbols['mk61_api'],e.symbols['mk61_api']+4),
                (api,api+active['api_size']),(services,services+active['service_size']),
                (table,table+active['table_count']*4),(resident+4,resident+8),
                (active['pointer'],active['pointer']+active['n'])]
            assert on_stack or any(a<=address and address+size<=b for a,b in ranges),('read beyond exact ABI/input',hex(address),size,active)
    u.hook_add(UC_HOOK_CODE,hook_code);u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)
    def execute(name,args):
        for reg,value in saved.items():u.reg_write(reg,value)
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,value&0xffffffff)
        for reg,value in ((UC_ARM_REG_SP,stack),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)):u.reg_write(reg,value)
        u.emu_start(e.symbols[name]|1,stop,count=1500000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
        assert all(u.reg_read(reg)==value for reg,value in saved.items()),('callee-saved',name,active)
        return u.reg_read(UC_ARM_REG_R0)
    results=[]
    modes=[('old26',108,28,26,True,False,True),('native27',108,32,27,True,True,True),
        ('null-optional',108,32,27,True,False,True),('extended26',108,32,26,True,False,True),
        ('short-count',108,32,25,True,False,False),('short-services',108,27,26,True,False,False),
        ('missing-services',108,0,0,False,False,False),('old-app-prefix',104,28,26,True,False,False)]
    for mode,api_size,service_size,count,present,native,valid in modes:
        counters.update(query=0,cap=0,resident=0)
        active.update(stage='init',api_size=api_size,service_size=service_size,table_count=count,present=present,pointer=buffer,n=0)
        u.mem_write(optional,struct.pack('<I',initial));u.mem_write(e.symbols['mk61_api'],bytes(4));u.mem_write(stack,bytes(4))
        api_raw=bytearray(108);struct.pack_into('<IHH',api_raw,0,0x31505041,1,api_size);struct.pack_into('<I',api_raw,104,query|1);u.mem_write(api,bytes(api_raw))
        service_raw=bytearray(32);struct.pack_into('<IHH',service_raw,0,0x31535953,2,service_size)
        struct.pack_into('<I',service_raw,12,cap|1);struct.pack_into('<II',service_raw,24,table,count);u.mem_write(services,bytes(service_raw))
        u.mem_write(table,b''.join(struct.pack('<I',cap|1) for _ in range(max(count,27))))
        if count>=27:u.mem_write(table+104,struct.pack('<I',resident|1 if native else 0))
        initialized=execute('mk61_module_entry',(0,api,0x12345678,4))
        assert initialized==(0 if valid else 5),(mode,'startup',initialized)
        calls=0
        if valid:
            for n in (0,1,3,4,7,8,16,17,65,4096):
                for offset in range(8):
                    for value in (0,-1,256):
                        for at in sorted({-1,0,n//2,n-1}) if n else [-1]:
                            pointer=buffer+offset;data=bytearray([(value&255)^0x80])*n
                            if at>=0:data[at]=value&255
                            u.mem_write(pointer,bytes(data));active.update(stage='call',pointer=pointer,n=n)
                            actual=execute('memchr',(pointer,value,n,0x12345678))
                            assert actual==(pointer+at if at>=0 else 0),(mode,n,offset,value,at,actual)
                            assert struct.unpack('<I',u.mem_read(optional,4))[0]==(resident|1 if native else fallback)
                            calls+=1
            active.update(pointer=0,n=0)
            assert execute('memchr',(0,-1,0,0))==0;calls+=1
            assert counters['query']==2 and counters['cap']==1,(mode,counters)
            assert counters['resident']==(calls if native else 0),(mode,counters,calls)
        row=dict(mode=mode,initialized=valid,calls=calls,callbacks=dict(counters),status='PASS');results.append(row);print(cpu,row,flush=True)
    return dict(cpu=cpu,status='PASS',scope='Functional ARM shared SDK startup and dispatch, not hardware timing',
        elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),results=results)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--cpu',choices=('m0','m4'),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=verify(a.elf,a.cpu);a.output.write_text(json.dumps(result,indent=2)+'\n')
