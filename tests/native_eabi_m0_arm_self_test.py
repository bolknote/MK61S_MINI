#!/usr/bin/env python3
"""Execute the actual ARMv6-M helpers and compact math, without libgcc or an FPU."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ, UC_HOOK_CODE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0, UC_ARM_REG_R0, UC_ARM_REG_R1,
    UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R11, UC_ARM_REG_SP,
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR)
from check_stm32_vectors import ElfImage

ROOT=Path(__file__).resolve().parents[1]
MASK=(1<<64)-1
SIGN=1<<63
INF=0x7FF0000000000000
STOP=0x081FF000
SP=0x2003FFF0

def bits(x):return struct.unpack('<Q',struct.pack('<d',x))[0]
def real(x):return struct.unpack('<d',struct.pack('<Q',x))[0]
def f_real(x):return struct.unpack('<f',struct.pack('<I',x&0xFFFFFFFF))[0]
def f_bits(x):
    try:return struct.unpack('<I',struct.pack('<f',x))[0]
    except OverflowError:return (0x80000000 if x<0 else 0)|0x7F800000
def signed(x,width):return x-(1<<width) if x>>(width-1) else x
def nan(x,width=64):return (x&((1<<(width-1))-1))>(INF if width==64 else 0x7F800000)
def ordered(x):return ~x&MASK if x&SIGN else x|SIGN
def quotient(x,y):
    if math.isnan(x) or math.isnan(y) or (x==0 and y==0):return float('nan')
    if y==0:return math.copysign(math.inf,x)*math.copysign(1,y)
    return x/y

class Machine:
    def __init__(self,path,rp2040=False):
        self.rp2040=rp2040
        self.elf=ElfImage(path)
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
        self.uc.mem_map(0x08000000,0x200000)
        self.uc.mem_map(0x10000000,0x200000)
        self.uc.mem_map(0x20000000,0x42000)
        self.uc.mem_map(0xD0000000,0x1000)
        self.elf.load(self.uc)
        self.rom_models=[]
        # Production Pico SDK wrappers normally resolve their ROM pointers at
        # boot. A function-only ELF test has not run that initializer. Model
        # only CLZ and ISO C memory intrinsics; all floating arithmetic and
        # quotient/remainder correction still execute the actual ARM code.
        for symbol,operation in (('__wrap___clzsi2','clz32'),('__wrap___clzdi2','clz64'),
            ('__wrap_memcpy','memcpy'),('__wrap_memset','memset')):
            if symbol not in self.elf.symbols:continue
            self.rom_models.append(symbol)
            address=self.elf.symbols[symbol]&~1
            self.uc.hook_add(UC_HOOK_CODE,self.rom_intrinsic,operation,begin=address,end=address)
        self.uc.hook_add(UC_HOOK_MEM_WRITE,self.write)
        self.uc.hook_add(UC_HOOK_MEM_READ,self.read_sio,begin=0xD0000070,end=0xD0000073)
        self.calls=0
    def rom_intrinsic(self,uc,address,size,operation):
        del address,size
        a,b,n=(uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2))
        if operation=='clz32':uc.reg_write(UC_ARM_REG_R0,32-a.bit_length())
        elif operation=='clz64':uc.reg_write(UC_ARM_REG_R0,64-(a|(b<<32)).bit_length())
        else:
            assert SP-4096<=a and a+n<=SP,('ROM memory write outside stack',hex(a),n)
            data=bytes([b&255])*n if operation=='memset' else bytes(uc.mem_read(b,n))
            if n:uc.mem_write(a,data)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    def write(self,uc,access,address,size,value,user):
        del access,user
        if self.rp2040 and address in (0xD0000060,0xD0000064):
            if address==0xD0000060:self.dividend=value
            else:
                quotient=self.dividend//value if value else 0xFFFFFFFF
                remainder=self.dividend%value if value else self.dividend
                uc.mem_write(0xD0000070,struct.pack('<3I',quotient,remainder,3))
            return
        assert SP-4096<=address and address+size<=SP,('non-stack write',hex(address),size)
    def read_sio(self,uc,access,address,size,value,user):
        del access,address,size,value,user
        # Reading DIV_QUOTIENT acknowledges and clears DIRTY.
        uc.mem_write(0xD0000078,struct.pack('<I',1))
    def call(self,name,a,b=0,width=64,count=False,shift=False):
        uc=self.uc
        saved={r:(0xA75D184B+r*0x1321)&0xFFFFFFFF for r in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
        for r,v in saved.items():uc.reg_write(r,v)
        regs=(a&0xFFFFFFFF,a>>32,b&0xFFFFFFFF,b>>32) if width==64 else (a&0xFFFFFFFF,b&0xFFFFFFFF,0,0)
        if shift:regs=(a&0xFFFFFFFF,a>>32,b,0)
        for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),regs):uc.reg_write(r,v)
        uc.reg_write(UC_ARM_REG_SP,SP);uc.reg_write(UC_ARM_REG_LR,STOP|1);uc.reg_write(UC_ARM_REG_XPSR,0x01000000)
        instructions=[0]
        def tick(*unused):instructions[0]+=1
        hook=uc.hook_add(UC_HOOK_CODE,tick) if count else None
        if count:uc.ctl_remove_cache(0x08000000,0x10200000)
        try:uc.emu_start(self.elf.symbols[name]|1,STOP,count=1000000)
        finally:
            if hook is not None:uc.hook_del(hook)
        assert uc.reg_read(UC_ARM_REG_PC)==STOP,(name,'did not return')
        assert uc.reg_read(UC_ARM_REG_SP)==SP,(name,'SP')
        for r,v in saved.items():assert uc.reg_read(r)==v,(name,'callee-saved',r)
        self.calls+=1
        return (uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32),
            uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32),instructions[0])
    def exact(self,name,a,b,expected,width=64,result_width=None,remainder=None,shift=False):
        got,rem,_=self.call(name,a,b,width,shift=shift)
        mask=(1<<(result_width or width))-1
        assert got&mask==expected&mask,(name,hex(a),hex(b),hex(got&mask),hex(expected&mask))
        if remainder is not None:assert rem==remainder,(name,'remainder',hex(a),hex(b),hex(rem),hex(remainder))
    def floating(self,name,a,b,expected,width=64,result_width=None):
        got=self.call(name,a,b,width)[0];rw=result_width or width
        if nan(expected,rw):assert nan(got&((1<<rw)-1),rw),(name,'NaN',hex(a),hex(b),hex(got))
        else:assert got&((1<<rw)-1)==expected,(name,hex(a),hex(b),hex(got),hex(expected))

def arithmetic(m,samples):
    rng=random.Random(0x6142040)
    edge=[0,SIGN,1,2,3,0xFFFFFFFF,0xFFFFFFFFFFFFF,0x10000000000000,
        bits(0.5),bits(1),bits(2),0x7FEFFFFFFFFFFFFF,INF,INF|SIGN,INF|1,INF|0x8000000000001,MASK]
    pairs=[(a,b) for a in edge for b in edge]+[(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(samples)]
    # Reach alignment/rounding/cancellation branches which uniform random bit
    # patterns rarely exercise, including both sides of the normal guards.
    for exponent in (1,2,54,55,56,1022,1023,1024,2044,2045,2046):
        for delta in (0,1,2,31,32,33,52,53,54,55,56,63,64):
            for fraction in (0,1,(1<<52)-1,rng.getrandbits(52)):
                a=(exponent<<52)|fraction
                b=(max(1,exponent-delta)<<52)|rng.getrandbits(52)
                pairs.extend(((a,b),(a,b|SIGN),(a,(a+1)|SIGN),(a,(a-1)|SIGN)))
    for a,b in pairs:
        x,y=real(a),real(b)
        for op,expected in (('dadd',x+y),('dsub',x-y),('drsub',y-x),('dmul',x*y),
            ('ddiv',quotient(x,y))):
            m.floating('__aeabi_'+op,a,b,bits(expected))
        for op,expected in (('dcmpeq',x==y),('dcmplt',x<y),('dcmple',x<=y),('dcmpge',x>=y),('dcmpgt',x>y),('dcmpun',math.isnan(x) or math.isnan(y))):
            m.exact('__aeabi_'+op,a,b,int(expected),result_width=32)
        m.floating('__aeabi_d2f',a,0,f_bits(x),result_width=32)
        for name,lo,hi,rw in (('d2iz',-(1<<31),1<<31,32),('d2uiz',0,1<<32,32),('d2lz',-(1<<63),1<<63,64),('d2ulz',0,1<<64,64)):
            if lo<=x<hi:m.exact('__aeabi_'+name,a,0,int(x),result_width=rw)
        for name,integer in (('ui2d',a&0xFFFFFFFF),('i2d',signed(a&0xFFFFFFFF,32)),('ul2d',a),('l2d',signed(a,64))):
            m.floating('__aeabi_'+name,a,0,bits(float(integer)))
        m.exact('__aeabi_lmul',a,b,(a*b)&MASK)
        m.exact('__aeabi_uldivmod',a,b,a//b if b else MASK if a else 0,remainder=a%b if b else 0)
        sa,sb=signed(a,64),signed(b,64)
        if sb:
            q=abs(sa)//abs(sb);q=-q if (sa<0)!=(sb<0) else q
            m.exact('__aeabi_ldivmod',a,b,q,remainder=(sa-q*sb)&MASK)
        for shift in (0,1,31,32,33,63):
            m.exact('__aeabi_llsl',a,shift,a<<shift,shift=True)
            m.exact('__aeabi_llsr',a,shift,a>>shift,shift=True)
            m.exact('__aeabi_lasr',a,shift,signed(a,64)>>shift,shift=True)
    fe=[0,0x80000000,1,2,0x7FFFFF,0x800000,0x3F000000,0x3F800000,0x7F7FFFFF,0x7F800000,0xFF800000,0x7F800001,0x7FC01234]
    pairs=[(a,b) for a in fe for b in fe]+[(rng.getrandbits(32),rng.getrandbits(32)) for _ in range(samples)]
    for a,b in pairs:
        x,y=f_real(a),f_real(b)
        for op,expected in (('fadd',x+y),('fsub',x-y),('frsub',y-x),('fmul',x*y),
            ('fdiv',quotient(x,y))):
            m.floating('__aeabi_'+op,a,b,f_bits(expected),32)
        for op,expected in (('fcmpeq',x==y),('fcmplt',x<y),('fcmple',x<=y),('fcmpge',x>=y),('fcmpgt',x>y),('fcmpun',math.isnan(x) or math.isnan(y))):
            m.exact('__aeabi_'+op,a,b,int(expected),32)
        m.floating('__aeabi_f2d',a,0,bits(x),32,64)
        m.floating('mk61_m0_sqrtf',a,0,f_bits(math.sqrt(x) if x>=0 else float('nan')),32)
        for name,integer in (('ui2f',a),('i2f',signed(a,32))):m.floating('__aeabi_'+name,a,0,f_bits(float(integer)),32)
        for name,lo,hi in (('f2iz',-(1<<31),1<<31),('f2uiz',0,1<<32)):
            if lo<=x<hi:m.exact('__aeabi_'+name,a,0,int(x),32)
        qr_expected=((a%b)<<32)|(a//b) if b else 0xFFFFFFFF if a else 0
        m.exact('__aeabi_uidivmod',a,b,qr_expected,32,result_width=64)
        # uidivmod returns the remainder in R1, alongside R0's quotient.
        qr=m.call('__aeabi_uidivmod',a,b,32)[0]
        assert qr>>32==(a%b if b else 0)

def math_vectors(m):
    stats={}
    for line in (ROOT/'tests/fixtures/compact_math_binary64.tsv').read_text().splitlines():
        if not line or line.startswith('#'):continue
        name,a,b,expected=line.split();a,b,expected=int(a,16),int(b,16),int(expected,16)
        symbol=f'_ZN12compact_math{len(name)}{name}E'+('dd' if name=='pow' else 'd')
        got=m.call(symbol,a,b)[0];value,ref=real(got),real(expected)
        if math.isnan(ref):assert math.isnan(value)
        elif ref==0 or math.isinf(ref):assert got==expected,(name,hex(a),hex(b),hex(got),hex(expected))
        else:
            ulp=abs(ordered(got)-ordered(expected));assert math.isfinite(value) and ulp<=(0 if name=='sqrt' else 4),(name,hex(a),hex(b),hex(got),hex(expected),ulp)
            stats[name]=max(stats.get(name,0),ulp)
    return stats

def fast_path_boundaries(m):
    rng=random.Random(0xCACE11)
    # Exercise large cancellation at every binary64 exponent, rather than
    # relying on uniform random pairs to happen to have nearby magnitudes.
    for exponent in range(1,2047):
        a=(exponent<<52)|rng.getrandbits(52)
        for b in (a+1,a-1):
            m.floating('__aeabi_dsub',a,b,bits(real(a)-real(b)))
            m.floating('__aeabi_dadd',a,b|SIGN,bits(real(a)-real(b)))
    # Exact rational reciprocal seeds and both power-of-two multiply orders.
    for fraction in range(8):
        for exponent in (1,2,54,55,1022,1023,1024,2044,2045,2046):
            b=(exponent<<52)|(fraction<<49)
            for _ in range(24):
                a=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
                for sign in (0,SIGN):
                    d=b|sign
                    m.floating('__aeabi_ddiv',a,d,bits(real(a)/real(d)))
                    m.floating('__aeabi_dmul',a,d,bits(real(a)*real(d)))
                    m.floating('__aeabi_dmul',d,a,bits(real(d)*real(a)))

def addition_rounding(m):
    # Uniform random encodings mostly reach the large-exponent-gap branch.
    # Deliberately cover both alignment directions, guard/sticky ties, a
    # significand carry, and equal negative signs throughout the fast guard.
    fractions=(0,1,1<<31,(1<<52)-2,(1<<52)-1)
    for exponent in (1,2,54,55,56,1022,1023,1024,2044,2045,2046):
        for delta in (0,1,2,31,32,33,52,53,54,55,60,64):
            if exponent<=delta:continue
            for af in fractions:
                for bf in fractions:
                    a=(exponent<<52)|af
                    b=((exponent-delta)<<52)|bf
                    for sign in (0,SIGN):
                        x,y=a|sign,b|sign
                        expected=bits(real(x)+real(y))
                        m.floating('__aeabi_dadd',x,y,expected)
                        m.floating('__aeabi_dadd',y,x,expected)
                        m.floating('__aeabi_dsub',x,y^SIGN,expected)
    rng=random.Random(0xADD06140)
    for _ in range(4096):
        exponent=rng.randrange(1,2047)
        a=(exponent<<52)|rng.getrandbits(52)
        b=(max(1,exponent-rng.randrange(65))<<52)|rng.getrandbits(52)
        for sa,sb in ((0,0),(SIGN,SIGN),(0,SIGN),(SIGN,0)):
            x,y=a|sa,b|sb
            expected=bits(real(x)+real(y))
            m.floating('__aeabi_dadd',x,y,expected)
            m.floating('__aeabi_dadd',y,x,expected)
            m.floating('__aeabi_dsub',x,y^SIGN,expected)

def build(toolchain,out,rp2040=False):
    out.mkdir(parents=True,exist_ok=True)
    flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-ffunction-sections','-fdata-sections',
        '-fno-lto','-fno-builtin','-DMK61_USE_M0_EABI=1','-DMK61_USE_NATIVE_EABI=0','-DMK61_USE_COMPACT_LIBM=1','-I'+str(ROOT/'code')]
    if rp2040:flags+=['-DMK61_M0_RP2040_EABI=1']
    objects=[]
    for source in ('code/native_eabi_m0.cpp','code/native_eabi_m0.S','code/native_eabi_m0_rp2040.S','code/compact_math.cpp'):
        p=ROOT/source;target=out/(p.name+'.o');objects.append(target)
        subprocess.run([str(toolchain/('arm-none-eabi-g++' if p.suffix=='.cpp' else 'arm-none-eabi-gcc')),*flags,
            *(['-std=c++17','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror'] if p.suffix=='.cpp' else []),'-c',str(p),'-o',str(target)],check=True)
    elf=out/'runtime.elf'
    subprocess.run([str(toolchain/'arm-none-eabi-g++'),*flags,'-nostdlib','-Wl,-Ttext=0x08000000',
        '-Wl,-e,__aeabi_dadd','-Wl,-Map='+str(out/'runtime.map'),*[str(p) for p in objects],'-o',str(elf)],check=True)
    undefined=subprocess.check_output([str(toolchain/'arm-none-eabi-nm'),'-u',str(elf)],text=True)
    assert not undefined,undefined
    return elf

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path)
    p.add_argument('--toolchain',type=Path)
    p.add_argument('--output-dir',type=Path,default=ROOT/'.build/m0-eabi-test')
    p.add_argument('--samples',type=int,default=1000)
    p.add_argument('--rp2040',action='store_true',help='Test SDK-derived normal kernels with a functional SIO divider model')
    p.add_argument('--math-only',action='store_true',help='Qualify a production ELF whose unused helper symbols were removed by section GC')
    p.add_argument('--json',type=Path)
    a=p.parse_args()
    if a.elf:elf=a.elf
    else:
        sys.path.insert(0,str(ROOT/'tools'));from build_picocalc import compiler_bin
        elf=build(compiler_bin(a.toolchain),a.output_dir,a.rp2040)
    m=Machine(elf,a.rp2040)
    if not a.math_only:
        arithmetic(m,a.samples);fast_path_boundaries(m);addition_rounding(m)
    worst=math_vectors(m)
    if a.rp2040:
        # A caller with pending divider state must get the full software path,
        # preserving every SIO operand/result/CSR bit.
        state=struct.pack('<7I',17,3,0,0,5,2,3)
        m.uc.mem_write(0xD0000060,state)
        for x,y in ((.7,1.3),(1.,2.),(-17.,3.)):
            m.exact('__aeabi_ddiv',bits(x),bits(y),bits(x/y))
            assert bytes(m.uc.mem_read(0xD0000060,len(state)))==state,'pending SIO state changed'
        m.uc.mem_write(0xD0000078,struct.pack('<I',1))
    counts={n:m.call('__aeabi_'+n,bits(.7),bits(1.3),count=True)[2] for n in ('dadd','dsub','dmul','ddiv')}
    report={'status':'PASS','elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'actual_arm_calls':m.calls,
        'math_vectors':1897,'math_worst_ulp':worst,'sample_instructions':counts,
        'abi':'Cortex-M0, soft EABI registers, R4-R11/SP preserved; writes '+('stack and SIO divider only' if a.rp2040 else 'stack only'),
        'timing_note':'Instruction counts are emulator diagnostics, not measured RP2040 cycles.'}
    if m.rom_models:report['sdk_rom_intrinsic_models']=m.rom_models
    print(json.dumps(report,indent=2),flush=True)
    if a.json:a.json.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
