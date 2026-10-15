#!/usr/bin/env python3
"""Execute the production MPU configuration and decode its exact permissions."""
import argparse,json,random,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from check_stm32_vectors import ElfImage
P=argparse.ArgumentParser(description=__doc__);P.add_argument('elf',type=Path);P.add_argument('--json',type=Path);a=P.parse_args()
e=ElfImage(a.elf);u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
for begin,size in ((0x08000000,0x100000),(0x20000000,0x20000),(0xE000E000,0x1000)):u.mem_map(begin,size)
u.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30);e.load(u)
TYPE,CTRL,RNR,RBAR,RASR=0xE000ED90,0xE000ED94,0xE000ED98,0xE000ED9C,0xE000EDA0
SP,STOP=0x2001FFF0,0x080FF000
banks=[[0,0] for _ in range(8)];selected=[0]
u.mem_write(TYPE,struct.pack('<I',8<<8))
def write(uc,access,address,size,value,_):
    if address==RNR:selected[0]=value
    elif address in (RBAR,RASR):
        assert size==4 and selected[0]<8
        banks[selected[0]][address==RASR]=value
u.hook_add(UC_HOOK_MEM_WRITE,write)
def symbol(part):
    found=[v for n,v in e.symbols.items() if n==part]
    assert len(found)==1,(part,found)
    return found[0]
set_app=symbol('_ZN9mpu_guard17set_app_executionEPKvj')
def call(fn,x=0,y=0):
    saved={r:0x61A00000+r for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    for r,value in saved.items():u.reg_write(r,value)
    u.reg_write(UC_ARM_REG_SP,SP);u.reg_write(UC_ARM_REG_LR,STOP|1)
    u.reg_write(UC_ARM_REG_R0,x);u.reg_write(UC_ARM_REG_R1,y)
    u.reg_write(UC_ARM_REG_XPSR,0x01000000);u.emu_start(fn|1,STOP,count=1000000)
    assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_SP)==SP
    assert all(u.reg_read(r)==value for r,value in saved.items())
    return u.reg_read(UC_ARM_REG_R0)
# LTO inlines unchanged MPU initialization. Model its completed state in the
# exact shipping layout; the code under test is the actual resident setter.
layout='_ZN9mpu_guard12_GLOBAL__N_1L13active_layoutE'
enabled='_ZN9mpu_guard12_GLOBAL__N_1L16hardware_enabledE'
assert e.sizes[layout]==40 and e.sizes[enabled]==1
static=e.symbols['_end'];guard=0x2001BF00
u.mem_write(e.symbols[layout],struct.pack('<BB2x8IB3x',1,8,
    0x20000000,0x20020000,static,SP,guard,guard+256,256,16384,1))
u.mem_write(e.symbols[enabled],bytes([1]));u.mem_write(CTRL,struct.pack('<I',5))
xn=(1<<28)|(3<<24)|(7<<16)
banks[0]=[0x20000000,xn|(16<<1)|1]
banks[6]=[0,(1<<28)|(4<<1)|1]
banks[7]=[guard,(1<<28)|(7<<1)|1]
fixed={i:tuple(banks[i]) for i in (0,6,7)}
def permissions(begin,end):
    # Decode every actual RAM granule, including globals, gap buffers, guard
    # and stack. Highest-numbered enabled matching MPU region wins.
    for address in range(0x20000000,0x20020000,32):
        executable=None
        for base,rasr in banks:
            if not rasr&1:continue
            size=1<<(((rasr>>1)&31)+1)
            if not base<=address<base+size:continue
            if size>=256 and ((rasr>>8)&(1<<((address-base)//(size//8)))):continue
            executable=not bool(rasr&(1<<28)) and bool((rasr>>24)&7)
        assert executable==bool(begin<=address<end),(hex(address),begin,end,banks)
    assert all(tuple(banks[i])==value for i,value in fixed.items())
guard=0x2001BF00;static=e.symbols['_end'];cases=[]
for end in (guard,guard-1536,(guard-2112)&~255,(guard-3648)&~255,guard-8192):
    for size in (32,64,288,544,864,1952,4096,4672,8192,16384,20480):
        if end-size>=static:cases.append((end-size,size))
rng=random.Random(0x61A44)
for _ in range(192):
    end=guard-256*rng.randrange(100);size=32*rng.randrange(1,641)
    if end-size>=static:cases.append((end-size,size))
for begin,size in cases:
    assert call(set_app,begin,size)==1,(hex(begin),size)
    permissions(begin,begin+size)
# A six-region interval and invalid/alignment/overflow cases must be rejected
# before touching any live MPU slot.
for begin,size in ((0x200136E0,0x1240),(guard-32,64),(static-32,32),
                   (guard-64,33),(guard-63,32),(guard-32768,32768),(0xFFFFFFE0,64)):
    before=[tuple(x) for x in banks];assert call(set_app,begin,size)==0,(begin,size)
    assert before==[tuple(x) for x in banks],'invalid span changed MPU'
# Couple the actual shipping gap allocator to the actual MPU setter. Owner
# metadata models cold M61/framebuffer/FS buffers at the top of free SRAM.
integrated=0
head='_ZN13shared_memory12_GLOBAL__N_1L16lifetime_buffersE'
gap='_ZN13shared_memory12_GLOBAL__N_1L8high_gapEjb'
if head in e.symbols:
    assert e.sizes[head]==4 and gap in e.symbols
    metadata=0x2001E000
    for lengths in ((1536,),(2112,1536),(2112,1536,1536)):
        end=guard
        for i,length in enumerate(lengths):
            end-=length;next_=metadata+16*(i+1) if i+1<len(lengths) else 0
            u.mem_write(metadata+16*i,struct.pack('<4I',end,length,29+i,next_))
        u.mem_write(e.symbols[head],struct.pack('<I',metadata))
        for size in (32,864,1952,20480):
            begin=call(e.symbols[gap],size,1)
            assert begin==((end&~255)-size),(lengths,size,hex(begin))
            assert call(set_app,begin,size)==1,(lengths,size,hex(begin))
            permissions(begin,begin+size);integrated+=1
    u.mem_write(e.symbols[head],bytes(4))
assert call(set_app,0,0)==1;permissions(0,0)
report=dict(status='PASS',elf=str(a.elf),exact_spans=len(cases),invalid_cases=7,
            granules_per_span=4096,allocator_spans=integrated,app_regions=5,neighbor_sram_xn=True,
            null_stack_guards_unchanged=True,callee_saved_and_sp=True)
if a.json:a.json.write_text(json.dumps(report,indent=2)+'\n')
print('Production MPU APP ARM:',len(cases),'spans +',integrated,'allocator/MPU integrations, all4096RAMgranules, five slots, exact XN/guards/ABI PASS',flush=True)
