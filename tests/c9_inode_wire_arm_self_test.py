#!/usr/bin/env python3
"""Run the linked production C9 codec on Cortex-M4 with strict memory bounds."""
import argparse
import json
from pathlib import Path
import random
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from run_portable_system_arm_tests import Elf
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('elf',type=Path)
p.add_argument('--json',type=Path)
a=p.parse_args()
e=Elf(a.elf)
def symbol(fragment):
    matches=[value for name,value in e.symbols.items() if fragment in name and '.isra.' not in name]
    assert len(matches)==1,(fragment,matches)
    return matches[0]
encode=symbol('L15serialize_inode')
decode=symbol('L17deserialize_inode')
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
u.mem_map(0x08000000,0x100000);u.mem_map(0x20000000,0x20000)
u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
e.load(u)
stop=0x080ff000;u.mem_write(stop,b'\x70\x47');sp=0x2001fff0
node=0x2001a000;wire=0x2001a100;output=0x2001a200
allowed_read=[];allowed_write=[]
def memory(uc,access,address,size,value,unused):
    spans=allowed_read if access==UC_MEM_READ else allowed_write
    if access==UC_MEM_READ and 0x08000000<=address and address+size<=0x08100000:return
    if sp-4096<=address and address+size<=sp:return
    assert any(lo<=address and address+size<=hi for lo,hi in spans),(hex(address),size,access,spans)
# Constants are imported separately: preserve exact Unicorn access values.
from unicorn import UC_MEM_READ
u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory)
saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
       UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
def call(function,r0,r1):
    for i,reg in enumerate(saved):u.reg_write(reg,0x61000000+i)
    u.reg_write(UC_ARM_REG_R0,r0);u.reg_write(UC_ARM_REG_R1,r1)
    u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,stop|1)
    u.emu_start(function|1,stop,count=100000)
    assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==sp
    assert all(u.reg_read(reg)==0x61000000+i for i,reg in enumerate(saved))
rng=random.Random(0xC926F411)
cases=0
for n in range(100):
    fields=[rng.getrandbits(bits) for bits in (32,16,16,16,16,16,16,16,8,8,16,32)]
    if n%11==0:fields[0]=0xffffffff
    ram=struct.pack('<I7HBBH2xI',*fields)
    golden=b'\xff'*26 if fields[0]==0xffffffff else struct.pack('<I7HBBHI',*fields)
    for shift in range(8):
        u.mem_write(node,ram);u.mem_write(wire,b'\x59'*48)
        allowed_read[:]=[(node,node+28)];allowed_write[:]=[(wire+shift,wire+shift+26)]
        call(encode,node,wire+shift)
        assert bytes(u.mem_read(wire+shift,26))==golden
        assert bytes(u.mem_read(wire,shift))==b'\x59'*shift
        assert bytes(u.mem_read(wire+shift+26,48-shift-26))==b'\x59'*(48-shift-26)
        u.mem_write(output,b'\x73'*40)
        allowed_read[:]=[(wire+shift,wire+shift+26)];allowed_write[:]=[(output,output+28)]
        call(decode,output,wire+shift)
        actual=bytes(u.mem_read(output,28))
        expected=b'\xff'*28 if fields[0]==0xffffffff else ram
        assert actual[:22]==expected[:22] and actual[24:28]==expected[24:28]
        assert bytes(u.mem_read(output+28,12))==b'\x73'*12
        cases+=2
result=dict(status='PASS',elf=str(a.elf),calls=cases,alignments=8,
            exact_memory_bounds=True,callee_saved_and_SP=True)
if a.json:a.json.write_text(json.dumps(result,indent=2)+'\n')
print('Production C9 ARM codec:',cases,'calls, 8 wire alignments, exact bounds, empty inode, ABI/SP PASS')
