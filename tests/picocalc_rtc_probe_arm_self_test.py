#!/usr/bin/env python3
"""Execute relocated SRAM probe, flash-comparison bounds and native-step jobs."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2


def run(path):
    raw=Path(path).read_bytes();h=struct.unpack_from('<16I',raw)
    assert h[:3]==(0x314d3353,1,64) and h[3]==len(raw)
    assert h[15]==zlib.crc32(raw[:60]) and h[12]==zlib.crc32(raw[64:])
    image=bytearray(raw[64:64+h[4]]);base=0x20001000;delta=base-0x20000000
    for at, in struct.iter_unpack('<I',raw[64+h[4]:]):
        struct.pack_into('<I',image,at,struct.unpack_from('<I',image,at)[0]+delta)
    u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
    for start,size in [(0x08000000,0x10000),(0x20000000,0x10000),(0x40000000,0x30000)]:u.mem_map(start,size)
    u.mem_write(base,bytes(image));api=0x20004000;job=api+64;data=api+128;out=api+1024
    clock=0x0800ffe0;stop=clock+16
    u.mem_write(api,struct.pack('<4I',1,16,clock|1,0))
    u.mem_write(clock,b'\x70\x47')
    ticks=[0]
    def code(uc,pc,size,ctx):
        if pc==clock:
            ticks[0]+=100
            uc.reg_write(UC_ARM_REG_R0,ticks[0]);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def write(uc,access,at,size,value,ctx):
        assert 0x20000000<=at<0x20010000,hex(at)
    u.hook_add(UC_HOOK_CODE,code);u.hook_add(UC_HOOK_MEM_WRITE,write)
    def call(op):
        u.reg_write(UC_ARM_REG_R0,op);u.reg_write(UC_ARM_REG_R1,api);u.reg_write(UC_ARM_REG_R2,job)
        u.reg_write(UC_ARM_REG_SP,0x20004f00);u.reg_write(UC_ARM_REG_LR,stop|1)
        u.emu_start(base+h[6],stop,timeout=1000000,count=1000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==0x20004f00
        return u.reg_read(UC_ARM_REG_R0)
    def start(payload):
        u.mem_write(data,payload);u.mem_write(out,bytes(512))
        u.mem_write(job,struct.pack('<6I',data,len(payload),out,512,0,0))
        return call(0)
    def response():
        size=struct.unpack('<I',u.mem_read(job+16,4))[0]
        return struct.unpack('<'+'I'*(size//4),u.mem_read(out,size))
    magic=0x31435452
    reference=bytes((i*29+7)&255 for i in range(224))
    u.mem_write(0x08002000,reference)
    assert start(struct.pack('<4I',magic,0,0x2000,224)+reference)==1
    assert response()==(magic,0,0x2000,224,1)
    bad=bytearray(reference);bad[-1]^=1
    assert start(struct.pack('<4I',magic,0,0x2000,224)+bad)==1
    assert response()[-1]==0
    for at,n in [(0xf800,1),(0xfffffff0,16),(0,225),(0,0)]:
        assert start(struct.pack('<4I',magic,0,at,n)+bytes(n))==2
    for steps,work in [(9,0),(17,64),(3,4096)]:
        seed=0x12345678;expected=seed
        assert start(struct.pack('<6I',magic,1,steps,work,seed,0))==0
        for i in range(steps):
            for _ in range(work):expected=(expected*1664525+1013904223)&0xffffffff
            expected^=i+0x9e3779b9
            assert call(1)==(1 if i==steps-1 else 0)
        assert response()==(magic,1,steps,work,seed,expected,100)
    for at,value in [(0x40002800,2),(0x40002804,0x28),(0x40002818,0),(0x4000281c,12345),
                     (0x20004a00,0x18011c03),(0x20004a04,0x00392a03),(0x20004a08,0x18011c03)]:
        u.mem_write(at,struct.pack('<I',value))
    assert start(struct.pack('<5I',magic,2,0x20004a00,0x20004a04,0x20004a08))==1
    assert response()==(magic,2,2,0x28,12345,0x18011c03,0x18011c03,0x00392a03)
    assert start(struct.pack('<5I',magic,2,0x20005000,0x20004a04,0x20004a08))==2
    assert call(3)==1
    return {'status':'PASS','physical_io':False,'hardware_timing':False,
            'module_sha256':hashlib.sha256(raw).hexdigest(),
            'module_memory_bytes':h[4]+h[5], 'peripheral_or_flash_writes':0,
            'cases':['relocations','matching and mismatching flash bytes','flash/size bounds',
                     'cooperative jobs and independent checksums','diagnostic registers/RAM bounds','FINI']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--module',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();result=run(a.module);text=json.dumps(result,indent=2)+'\n'
    if a.output:a.output.write_text(text)
    print(text,end='')
