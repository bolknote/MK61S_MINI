#!/usr/bin/env python3
"""Execute the compiled Thumb code with an explicit SIO functional model.

The model is independent of the C kernels, is checked against integer formulas,
and supplies peripheral results only. No model count is physical RP2040 timing.
"""
import argparse
import hashlib
import json
from math import isqrt
from pathlib import Path
import random
import struct
import sys
from fractions import Fraction

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_MEM_READ

MASK=(1<<32)-1
def u32(x):return x&MASK
def s32(x):return x-(1<<32) if x>>31 else x
class InterpMachine(Machine):
    def __init__(self,elf):
        self.mmio_reads=0;self.mmio_writes=0
        super().__init__(elf,True)
        self.uc.hook_add(UC_HOOK_MEM_READ,self.read_interp,begin=0xD0000080,end=0xD00000FF)
    def write(self,uc,access,address,size,value,user):
        if 0xD0000080<=address<0xD0000100:
            off=(address-0xD0000080)%64
            assert size==4 and off in (0,4,8,12,16,44,48),('unexpected INTERP write',hex(address),size)
            self.mmio_writes+=1;return
        return super().write(uc,access,address,size,value,user)
    def read_interp(self,uc,access,address,size,value,user):
        assert size==4
        base=address&~63;off=address-base
        self.mmio_reads+=1
        raw=struct.unpack('<16I',uc.mem_read(base,64))
        if off in (0,4,8,12,16,44,48):return
        assert off in (32,36,40),('POP/unsupported INTERP read',hex(address))
        vals=[]
        for k in range(2):
            ctrl=raw[11+k];shift=ctrl&31;lsb=(ctrl>>5)&31;msb=(ctrl>>10)&31
            assert lsb<=msb
            accum=raw[1-k] if ctrl&(1<<16) else raw[k]
            v=(accum>>shift)&(((1<<(msb-lsb+1))-1)<<lsb)
            if ctrl&(1<<15) and v&(1<<msb):v|=MASK^((1<<(msb+1))-1)
            vals.append(u32(v))
        if raw[11]&(1<<21):
            assert base==0xD0000080
            alpha=vals[1]&255
            a,b=raw[2:4]
            if raw[12]&(1<<15):a,b=s32(a),s32(b)
            result=(alpha,u32(a+((b-a)*alpha//256)),u32(raw[4]+vals[0]))
        else:result=(u32(raw[2]+vals[0]),u32(raw[3]+vals[1]),u32(raw[4]+vals[0]+vals[1]))
        uc.mem_write(address,struct.pack('<I',result[(off-32)//4]))

def seed_oracle(m,p):
    num=1<<116;den=m<<p;q=isqrt(num//den)
    mid=den*(2*q+1)**2
    if 4*num>mid or (4*num==mid and q&1):q+=1
    return min(MASK,q)
def q62_oracle(a,b):
    q,r=divmod(a*b,1<<62)
    return (q+int(r>(1<<61) or (r==(1<<61) and q&1)))&((1<<64)-1)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--elf',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--variant',choices=('all','alu','rsqrt','sqrt','address'),default='all')
    ap.add_argument('--samples',type=int,default=4000);a=ap.parse_args()
    rng=random.Random(0x20401A);m=InterpMachine(a.elf);digest=hashlib.sha256();checked={};profiles={}
    required={
      'alu':('cpu_wide32','interp_wide32','cpu_mul8','interp_mul8','cpu_q62','interp_q62'),
      'rsqrt':('current_rsqrt_seed','cpu_rsqrt_seed','interp_rsqrt_seed'),
      'sqrt':('current_sqrt_seeds','cpu_sqrt_seeds','interp_sqrt_seeds'),
      'address':('cpu_exp_address','interp_exp_address','cpu_ln_addresses','interp_ln_addresses','cpu_pow_address','interp_pow_address')}
    required_names=set(n for names in required.values() for n in names) if a.variant=='all' else set(required[a.variant])
    assert required_names<=set(m.elf.symbols),(a.variant,required_names-set(m.elf.symbols))
    def available(name):return name in required_names
    def call(name,x=0,y=0,count=False):
        if name.endswith('_setup') and name not in m.elf.symbols:return (0,0,0)
        return m.call(name,x,y,count=count)
    def check(name,x,y,expected):
        if not available(name):return
        got=call(name,x,y)[0]
        assert got==expected,(name,hex(x),hex(y),hex(got),hex(expected))
        digest.update(struct.pack('<3Q',x,y,got));checked[name]=checked.get(name,0)+1
    def profile(name,inputs,setup=None):
        if not available(name):return
        rows=[]
        for x,y in inputs:
            if setup:call(setup)
            r,w=m.mmio_reads,m.mmio_writes
            got,unused,n=call(name,x,y,True)
            rows.append(dict(a=hex(x),b=hex(y),result=hex(got),instructions=n,
              interp_reads=m.mmio_reads-r,interp_writes=m.mmio_writes-w))
        profiles[name]=rows
    edge=sorted({0,1,255,256,65535,65536,MASK,MASK-1,*[1<<k for k in range(32)]})
    pairs=[(x,y) for x in edge for y in edge]+[(rng.getrandbits(32),rng.getrandbits(32)) for _ in range(a.samples)]
    call('interp_blend_setup')
    for x,y in pairs:
        for name in ('cpu_wide32','interp_wide32'):check(name,x,y,x*y)
        for name in ('cpu_mul8','interp_mul8'):check(name,x,y,x*(y&255))
    for x,y in [(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(a.samples)]+[(0,0),((1<<64)-1,(1<<64)-1),(1<<62,1<<61)]:
        for name in ('cpu_q62','interp_q62'):check(name,x,y,q62_oracle(x,y))
    for name in ('cpu_wide32','interp_wide32','cpu_mul8','interp_mul8','cpu_q62','interp_q62'):
        profile(name,[(0,0),(MASK,MASK),(0xF1234567,0x9ABCDEF0)],'interp_blend_setup')
    seed_inputs=[]
    for p in range(2):
        for j in range(256):
            for alpha in (0,1,127,128,254,255):
                lo=(1<<52)+(j<<44)+(alpha<<36)
                seed_inputs.extend(((lo,p),(lo+(1<<36)-1,p)))
    seed_inputs += [((1<<52)|rng.getrandbits(52),rng.randrange(2)) for _ in range(a.samples)]
    maxerror={name:0 for name in ('current_rsqrt_seed','cpu_rsqrt_seed','interp_rsqrt_seed') if available(name)}
    for x,p in seed_inputs:
        expected=seed_oracle(x,p);got=[]
        for name in maxerror:
            value=call(name,x,p)[0];checked[name]=checked.get(name,0)+1
            error=abs(value-expected);maxerror[name]=max(maxerror[name],error)
            assert error<=13,(name,hex(x),p,value,expected,error)
            digest.update(struct.pack('<3Q',x,p,value))
            got.append(value)
        if got:assert got[1]==got[2],('CPU/HW blend disagreement',hex(x),p,got)
    seed_examples=[(1<<52,0),((1<<52)+1234567890123,0),((1<<53)-1,1)]
    for name in maxerror:profile(name,seed_examples,'interp_blend_setup')
    sqrt_error={name:[0,0] for name in ('current_sqrt_seeds','cpu_sqrt_seeds','interp_sqrt_seeds') if available(name)}
    for x,p in seed_inputs:
        n=x<<(10+p);r=isqrt(n)
        if 4*n>(2*r+1)**2 or (4*n==(2*r+1)**2 and r&1):r+=1
        r=min(MASK,r)
        inv_num=1<<114;den=x<<p;v=isqrt(inv_num//den)
        if 4*inv_num>den*(2*v+1)**2 or (4*inv_num==den*(2*v+1)**2 and v&1):v+=1
        results=[]
        for name in sqrt_error:
            value=call(name,x,p)[0];checked[name]=checked.get(name,0)+1
            er,ev=abs((value&MASK)-r),abs((value>>32)-v)
            sqrt_error[name]=[max(sqrt_error[name][0],er),max(sqrt_error[name][1],ev)]
            limits=(11,13) if name.startswith('current_') else (2,6)
            assert er<=limits[0] and ev<=limits[1],(name,hex(x),p,er,ev,hex(value),r,v)
            digest.update(struct.pack('<3Q',x,p,value))
            results.append(value)
        if results:assert results[1]==results[2],('sqrt CPU/HW blend disagreement',hex(x),p)
    for name in sqrt_error:profile(name,seed_examples,'interp_blend_setup')
    for setup,names,oracle in (
        ('interp_exp_setup',('cpu_exp_address','interp_exp_address'),lambda k:0x20010000+((k&511)<<3)),
        ('interp_ln_setup',('cpu_ln_addresses','interp_ln_addresses'),lambda k:(0x20010000+(((k>>10)&1023)<<3))|((0x20014000+((k>>10)&1023))<<32)),
        ('interp_pow_setup',('cpu_pow_address','interp_pow_address'),lambda k:0x20010000+12*((k>>10)&1023))):
        call(setup)
        for k in [0,MASK,*[j<<10 for j in range(1024)],*[rng.getrandbits(32) for _ in range(a.samples)]]:
            for name in names:check(name,k,0,oracle(k))
        for name in names:profile(name,[(0,0),(MASK,0),(0x3FF12345,0)],setup)
    # Busy-divider fallback must preserve every divider word. Exercise carry
    # in generic 32-bit restoring division as well as the seed denominator.
    for x,y in [(MASK,MASK),(MASK,0x80000001),(MASK,3),(123456789,777),(1,0)]:
        if 'experiment_udiv32' not in m.elf.symbols:break
        before=struct.pack('<7I',0x11111111,0x22222222,0x11111111,0x22222222,0x33333333,0x44444444,3)
        m.uc.mem_write(0xD0000060,before)
        got=m.call('experiment_udiv32',x,y,width=32)
        assert got[0]&MASK==(x//y if y else MASK)
        assert bytes(m.uc.mem_read(0xD0000060,28))==before
    report=dict(status='PASS',variant=a.variant,hardware_verified=False,physical_timing=False,
      elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),actual_arm_calls=m.calls,
      checked=checked,maximum_seed_error_q32=maxerror,maximum_sqrt_seed_errors_q31=sqrt_error,profiles=profiles,digest=digest.hexdigest(),
      model='Functional shift/mask/sign-extend/base and unsigned blend floor; no POP reads. Counts are ARM instructions, never RP2040 cycles.',
      abi='Every kernel call checks R4-R11, SP, return and bounded stack writes; MMIO writes restricted to named INTERP registers or divider.',
      scope='Seed stage only: no claim that full sqrt/rsqrt/pow is accelerated or that existing final-rounding proofs have been transferred.')
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='profiles'},indent=2))
if __name__=='__main__':main()
