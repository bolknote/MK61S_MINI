#!/usr/bin/env python3
"""Run actual soft EABI helpers: exact host arithmetic oracle, ARM ABI and write bounds."""
import argparse
import json
import math
from pathlib import Path
import random
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import *
from check_stm32_vectors import ElfImage

MASK=(1<<64)-1
SIGN=1<<63
INF=0x7FF0000000000000
STOP=0x080FF000
SP=0x2001FFF0

def bits(x):return struct.unpack('<Q',struct.pack('<d',x))[0]
def real(x):return struct.unpack('<d',struct.pack('<Q',x))[0]
def quiet(x):return (x&~SIGN)>INF

def float_bits(x):
    try:return struct.unpack('<I',struct.pack('<f',x))[0]
    except OverflowError:return (0x80000000 if x<0 else 0)|0x7F800000

class Machine:
    def __init__(self,path):
        self.elf=ElfImage(path)
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
        self.uc.mem_map(0x08000000,0x100000)
        self.uc.mem_map(0x20000000,0x20000)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2,0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.elf.load(self.uc)
        self.uc.hook_add(UC_HOOK_MEM_WRITE,self.write)
        self.calls=0
    def write(self,uc,access,address,size,value,user):
        del uc,access,value,user
        assert SP-1024<=address and address+size<=SP,('non-stack write',hex(address),size)
    def call(self,name,a,b=0,count=False):
        uc=self.uc
        saved={}
        for reg in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1):saved[reg]=(0xA67B1903+reg*0x1021)&0xFFFFFFFF
        for reg in range(UC_ARM_REG_D8,UC_ARM_REG_D15+1):saved[reg]=(0x1982092712345678+reg*0x10001)&MASK
        saved[UC_ARM_REG_FPSCR]=0
        for reg,val in saved.items():uc.reg_write(reg,val)
        for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(a&0xFFFFFFFF,a>>32,b&0xFFFFFFFF,b>>32)):uc.reg_write(reg,val)
        uc.reg_write(UC_ARM_REG_SP,SP);uc.reg_write(UC_ARM_REG_LR,STOP|1);uc.reg_write(UC_ARM_REG_XPSR,0x01000000)
        instructions=[0]
        def tick(*unused):instructions[0]+=1
        hook=uc.hook_add(UC_HOOK_CODE,tick) if count else None
        if count:uc.ctl_remove_cache(0x08000000,0x08100000)
        try:
            uc.emu_start(self.elf.symbols[name]|1,STOP,count=20000)
        finally:
            if hook is not None:uc.hook_del(hook)
        assert uc.reg_read(UC_ARM_REG_PC)==STOP,(name,'did not return')
        assert uc.reg_read(UC_ARM_REG_SP)==SP,(name,'SP')
        for reg,val in saved.items():assert uc.reg_read(reg)==val,(name,'callee-saved/FPSCR',reg)
        self.calls+=1
        return (uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32),
                uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32),instructions[0])
    def exact(self,name,a,b,expected,width=64,remainder=None):
        got,rem,_=self.call(name,a,b)
        mask=(1<<width)-1
        assert (got&mask)==(expected&mask),(name,hex(a),hex(b),hex(got&mask),hex(expected&mask))
        if remainder is not None:assert rem==remainder,('remainder',hex(a),hex(b),hex(rem),hex(remainder))

def run(path,samples,baseline):
    m=Machine(path);rng=random.Random(0x61411)
    edge=[0,SIGN,1,2,3,0xFFFFFFFF,0xFFFFFFFFFFFFF,0x10000000000000,
          bits(0.5),bits(1),bits(2),bits(1.5),0x7FEFFFFFFFFFFFFF,
          INF,INF|SIGN,INF|1,0x7FF8123456789ABC,0xFFF8123456789ABC,MASK]
    pairs=[(a,b) for a in edge for b in edge]
    pairs.extend((rng.getrandbits(64),rng.getrandbits(64)) for _ in range(samples))
    for a,b in pairs:
        x,y=real(a),real(b)
        for name,operation in [('dadd',lambda:x+y),('dsub',lambda:x-y),('drsub',lambda:y-x),('dmul',lambda:x*y),('ddiv',lambda:x/y)]:
            if '__aeabi_'+name not in m.elf.symbols:continue # Unexported, unused helpers may be GC'd.
            if math.isnan(x) or math.isnan(y):continue # Baseline NaN payload checks below.
            if name=='ddiv' and y==0:
                expected=INF|((a^b)&SIGN) if x!=0 else INF|(1<<51)
            elif math.isinf(x) and math.isinf(y) and name=='ddiv':expected=INF|(1<<51)
            else:
                out=operation();expected=bits(out)
                if math.isnan(out):expected=INF|(1<<51)
            if quiet(expected):assert quiet(m.call('__aeabi_'+name,a,b)[0])
            else:m.exact('__aeabi_'+name,a,b,expected)
        for name,expected in [('dcmpeq',x==y),('dcmplt',x<y),('dcmple',x<=y),('dcmpge',x>=y),('dcmpgt',x>y)]:m.exact('__aeabi_'+name,a,b,int(expected),32)
        if not math.isnan(x):m.exact('__aeabi_d2f',a,0,float_bits(x),32)
        f=struct.unpack('<f',struct.pack('<I',b&0xFFFFFFFF))[0]
        if not math.isnan(f):m.exact('__aeabi_f2d',b&0xFFFFFFFF,0,bits(float(f)))
        for name,integer in [('ui2d',a&0xFFFFFFFF),('i2d',(a&0xFFFFFFFF)-(1<<32) if a&(1<<31) else a&0xFFFFFFFF),('ul2d',b),('l2d',b-(1<<64) if b&SIGN else b)]:
            m.exact('__aeabi_'+name,a if name in ('ui2d','i2d') else b,0,bits(float(integer)))
        if math.isfinite(x):
            for name,lo,hi,width in [('d2iz',-(1<<31),1<<31,32),('d2uiz',0,1<<32,32),('d2lz',-(1<<63),1<<63,64),('d2ulz',0,1<<64,64)]:
                if lo<=x<hi:m.exact('__aeabi_'+name,a,0,int(x),width)
        for n,d in ((a,b),(a,b&0xFFFFFFFF),(a,b&0xFFFFFFFFFF)):
            m.exact('__aeabi_uldivmod',n,d,n//d if d else MASK if n else 0,remainder=n%d if d else 0)
    # Real exponent insertion fast path: exercise both signs, fraction tails,
    # exact scaling, the normal/subnormal boundary and overflow.
    exponents=(1,2,3,52,53,100,511,1022,1023,1024,1535,2044,2045,2046)
    for ea in exponents:
        for eb in exponents:
            for fraction in (0,1,(1<<52)-1):
                for sign in (0,SIGN):
                    for sign_b in (0,SIGN):
                        a=(ea<<52)|fraction|sign;b=(eb<<52)|sign_b
                        out=real(a)/real(b)
                        m.exact('__aeabi_ddiv',a,b,bits(out))
    if baseline:
        gold=json.loads(baseline.read_text())
        for name,rows in gold.items():
            for row in rows:
                a=int(row.get('input',row.get('a')),16);b=int(row.get('b','0'),16)
                if name=='__aeabi_d2f' and quiet(a):
                    got,_,_=m.call(name,a,b)
                    assert (got&0x7FFFFFFF)>0x7F800000
                    continue # NaN sign/payload is not specified by conversion.
                width=32 if name in ('__aeabi_d2iz','__aeabi_d2uiz','__aeabi_d2f') else 64
                m.exact(name,a,b,int(row['r0r1'],16),width,int(row['r2r3'],16) if name=='__aeabi_uldivmod' else None)
    counts={name:m.call('__aeabi_'+name,bits(0.7),bits(1.3),True)[2] for name in ('dadd','dsub','dmul','ddiv')}
    report=dict(status='PASS',calls=m.calls,samples=samples,sample_instructions=counts,
                abi='soft EABI GPR arguments/return, R4-R11/D8-D15/SP/FPSCR preserved, writes stack only')
    print(path.parent.name,report,flush=True)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,action='append',required=True)
    p.add_argument('--baseline-edges',type=Path,default=Path(__file__).parent/'fixtures/native_eabi_gcc_boundaries.json')
    p.add_argument('--samples',type=int,default=3000)
    p.add_argument('--json',type=Path)
    a=p.parse_args();report={str(path):run(path,a.samples,a.baseline_edges) for path in a.elf}
    if a.json:a.json.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
