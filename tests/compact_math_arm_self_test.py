#!/usr/bin/env python3
"""Execute public binary64 math from production ARM ELFs against an independent oracle."""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from run_portable_system_arm_tests import Elf

NAMES=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt','pow')
STOP=0x080FF000
def bits(x): return struct.unpack('<Q',struct.pack('<d',x))[0]
def value(x): return struct.unpack('<d',struct.pack('<Q',x))[0]
def ordered(x): return ~x & ((1<<64)-1) if x>>63 else x|(1<<63)
def distance(a,b): return abs(ordered(a)-ordered(b))

class MathMachine:
    def __init__(self,path):
        elf=Elf(path);elf.require_libm_math(path)
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        self.uc.mem_map(0x08000000,0x100000)
        self.uc.mem_map(0x20000000,0x20000)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2,0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        elf.load(self.uc)
        api=elf.symbol('_ZZN15loadable_module12app_servicesEvE3api')
        header=struct.unpack('<IHH',self.uc.mem_read(api,8))
        assert header==(0x31535953,2,28),header
        self.entry=struct.unpack('<I',self.uc.mem_read(api+16,4))[0]
        assert self.entry&1 and 0x08000000<=self.entry<STOP
        self.stack_top=elf.symbol('_estack')-16
        self.compact=any('_ZN12compact_math' in name for name in elf.symbols)
        self.instructions=0
        if self.compact:
            legacy = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'log', 'log10', 'exp', 'sqrt', 'pow'}
            assert not legacy.intersection(elf.symbols), 'standard libm remains in compact firmware'
            self.uc.hook_add(UC_HOOK_MEM_WRITE,self.check_write)
    def check_write(self,uc,access,address,size,written,user):
        del uc,access,written,user
        assert self.stack_top-8192<=address and address+size<=self.stack_top,(hex(address),size)
    def count_instruction(self,uc,address,size,user):
        del uc,address,size,user
        self.instructions+=1
    def call(self,operation,a,b,count=False):
        saved={}
        for register in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1):
            saved[register]=(0xA54CE019+register*0x1021)&0xFFFFFFFF
        for register in range(UC_ARM_REG_D8,UC_ARM_REG_D15+1):
            saved[register]=(0x0123456789ABCDEF+register*0x10001)&((1<<64)-1)
        for register,sentinel in saved.items(): self.uc.reg_write(register,sentinel)
        self.uc.reg_write(UC_ARM_REG_R0,operation)
        self.uc.reg_write(UC_ARM_REG_D0,a)
        self.uc.reg_write(UC_ARM_REG_D1,b)
        self.uc.reg_write(UC_ARM_REG_SP,self.stack_top)
        self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
        self.instructions=0
        hook=self.uc.hook_add(UC_HOOK_CODE,self.count_instruction) if count else None
        if count:
            # Unicorn must rebuild cached translation blocks after adding a
            # code hook, otherwise only previously unseen paths are counted.
            self.uc.ctl_remove_cache(0x08000000,0x08100000)
        try:
            self.uc.emu_start(self.entry,STOP,count=200000)
            assert self.uc.reg_read(UC_ARM_REG_PC)==STOP,'math did not return'
            assert self.uc.reg_read(UC_ARM_REG_SP)==self.stack_top,'stack imbalance'
            for register,sentinel in saved.items():
                assert self.uc.reg_read(register)==sentinel,('AAPCS callee-saved',register)
            return self.uc.reg_read(UC_ARM_REG_D0),self.instructions
        finally:
            if hook is not None:self.uc.hook_del(hook)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resident-elf',type=Path,action='append',required=True)
    parser.add_argument('--vectors',type=Path,default=Path(__file__).parent/'fixtures/compact_math_binary64.tsv')
    parser.add_argument('--json',type=Path)
    args=parser.parse_args()
    vectors=[]
    for line in args.vectors.read_text().splitlines():
        if not line or line.startswith('#'):continue
        name,a,b,result=line.split()
        vectors.append((NAMES.index(name),int(a,16),int(b,16),int(result,16)))
    assert len(vectors)>=1800
    report={}
    for path in args.resident_elf:
        machine=MathMachine(path)
        stats={name:{'cases':0,'worst_ulp':0} for name in NAMES}
        for operation,a,b,expected in vectors:
            actual,_=machine.call(operation,a,b)
            x,y=value(actual),value(expected)
            if math.isnan(y):assert math.isnan(x)
            elif y==0 or math.isinf(y):assert actual==expected,(path,NAMES[operation],hex(a),hex(b),hex(actual),hex(expected))
            else:
                ulp=distance(actual,expected)
                limit=0 if NAMES[operation]=='sqrt' else 4
                assert math.isfinite(x) and ulp<=limit,(path,NAMES[operation],hex(a),hex(b),hex(actual),hex(expected),ulp)
                stats[NAMES[operation]]['worst_ulp']=max(stats[NAMES[operation]]['worst_ulp'],ulp)
            stats[NAMES[operation]]['cases']+=1
        # Exact IEEE boundary semantics, independent of the finite oracle.
        zero, negative_zero = 0, 0x8000000000000000
        one, infinity, negative_infinity = 0x3FF0000000000000, 0x7FF0000000000000, 0xFFF0000000000000
        quiet_nan = 0x7FF8000000000123
        edges = []
        for name in ('sin', 'tan', 'asin', 'atan', 'sqrt'):
            edges += [(name, zero, zero, zero), (name, negative_zero, zero, negative_zero)]
        for name in ('cos', 'exp'):
            edges += [(name, zero, zero, one), (name, negative_zero, zero, one)]
        for name in ('ln', 'log10'):
            edges += [(name, zero, zero, negative_infinity),
                      (name, negative_zero, zero, negative_infinity),
                      (name, infinity, zero, infinity),
                      (name, bits(-1.0), zero, quiet_nan)]
        for name in ('sin', 'cos', 'tan', 'asin', 'acos'):
            edges += [(name, infinity, zero, quiet_nan), (name, negative_infinity, zero, quiet_nan)]
        edges += [('sqrt', infinity, zero, infinity), ('sqrt', negative_infinity, zero, quiet_nan),
                  ('exp', infinity, zero, infinity), ('exp', negative_infinity, zero, zero),
                  ('acos', one, zero, zero), ('asin', bits(2.0), zero, quiet_nan),
                  ('pow', negative_zero, bits(3.0), negative_zero),
                  ('pow', negative_zero, bits(2.0), zero),
                  ('pow', negative_zero, bits(-3.0), negative_infinity),
                  ('pow', quiet_nan, zero, one), ('pow', one, quiet_nan, one),
                  ('pow', bits(-2.0), bits(0.5), quiet_nan)]
        edges += [(name, quiet_nan, zero, quiet_nan) for name in NAMES if name != 'pow']
        for name, a, b, expected in edges:
            actual, _ = machine.call(NAMES.index(name), a, b)
            assert math.isnan(value(actual)) if math.isnan(value(expected)) else actual == expected, (path, name, hex(a), hex(b), hex(actual), hex(expected))
        counts={}
        for operation,name in enumerate(NAMES):
            a=0.7 if operation<=5 else 1.3
            if name=='pow':a=1.3
            _,n=machine.call(operation,bits(a),bits(0.7),count=True)
            counts[name]=n
        large_counts={}
        for label,a in [('float32_1e38',struct.unpack('<f',struct.pack('<f',1e38))[0]),('binary64_max',value(0x7FEFFFFFFFFFFFFF))]:
            large_counts[label]={NAMES[op]:machine.call(op,bits(a),0,count=True)[1] for op in range(3)}
        report[str(path)]={'status':'PASS','compact':machine.compact,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'vectors':len(vectors),'IEEE_edge_cases':len(edges),'stats':stats,'sample_instructions':counts,'large_angle_instructions':large_counts,'ABI':'AAPCS integer/VFP callee-saved and SP preserved; compact math writes stack only'}
        print(path.parent.name,len(vectors),'actual ARM math vectors and AAPCS PASS',flush=True)
    if args.json:
        args.json.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
