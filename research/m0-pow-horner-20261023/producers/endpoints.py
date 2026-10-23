"""Independent Fraction/MPFR checks for the lazy factor prototype."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root=Path.cwd();sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP,bits,real
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf',type=Path,required=True)
parser.add_argument('--json',type=Path,required=True)
parser.add_argument('--samples',type=int,default=6000)
args=parser.parse_args()
m=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,
          bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
rng=random.Random(0x12364096);digest=hashlib.sha256()
qptr,bptr=SP-15000,SP-14936
state=lambda h,e,r:struct.pack('<QiI',h,e,r)
unpack=lambda ptr:struct.unpack('<QiI',bytes(m.uc.mem_read(ptr,16)))
interval=lambda h,e,r:(F(h-r)*F(2)**(e-63),F(h+r)*F(2)**(e-63))
counts=dict(square=0,base=0,multiply=0,aliases=0,inverse=0)
assert 'factor64_square' not in m.elf.symbols, 'Unused Q64 square must be absent from this Horner build'
for i in range(args.samples):
    h,bh=rng.randrange(1<<63,1<<64),rng.randrange(1<<63,1<<64)
    if i%7==0:h=rng.choice((1<<63,(1<<63)+1,(1<<64)-1,(1<<64)-2))
    e,be=rng.randrange(-1022,1024),rng.randrange(-1022,1024)
    error=0 if i%5==0 else rng.randrange((1<<20)+1)
    a=state(h,e,error);lo,hi=interval(h,e,error)
    b=state(bh,be,0);m.uc.mem_write(qptr,a);m.uc.mem_write(bptr,b)
    m.call('factor64_base',qptr,bptr,32)
    center,exponent,radius=unpack(qptr);left,right=interval(center,exponent,radius)
    factor=F(bh)*F(2)**(be-63)
    assert 1<<63<=center<1<<64 and left<=lo*factor<=hi*factor<=right,(i,'base')
    assert bytes(m.uc.mem_read(bptr,16))==b
    counts['base']+=1;digest.update(a+b+bytes(m.uc.mem_read(qptr,16)))
    b=state(bh,be,0 if i%5==1 else rng.randrange((1<<20)+1))
    alias=i%17==0
    if alias:b=a
    blo,bhi=interval(*struct.unpack('<QiI',b))
    m.uc.mem_write(qptr,a);m.uc.mem_write(bptr,b)
    m.call('factor64_multiply',qptr,qptr if alias else bptr,32)
    center,exponent,radius=unpack(qptr);left,right=interval(center,exponent,radius)
    assert 1<<63<=center<1<<64 and left<=lo*blo<=hi*bhi<=right,(i,'multiply')
    if not alias:assert bytes(m.uc.mem_read(bptr,16))==b
    counts['multiply']+=1;counts['aliases']+=alias;digest.update(a+b+bytes(m.uc.mem_read(qptr,16)))

inverse_name=next(n for n in m.elf.symbols if 'factor_inverse' in n)
inverse_cases=set()
for parity in (0,1):
    for cell in range(256):
        for tail in (0,1,(1<<43)-1,1<<43,(1<<43)+1,(1<<44)-1):
            inverse_cases.add(((1023+parity)<<52)|(cell<<44)|tail)
for _ in range(args.samples):inverse_cases.add((rng.randrange(1,2047)<<52)|rng.getrandbits(52))
for xb in sorted(inverse_cases):
    m.call(inverse_name,qptr,xb)
    h,e,r=unpack(qptr);lo,hi=interval(h,e,r)
    assert 1<<63<=h<1<<64 and r in (24,48) and lo>0
    assert lo*lo<=1/F(real(xb))<=hi*hi,('inverse root',hex(xb),h,e,r)
    counts['inverse']+=1;digest.update(struct.pack('<Q',xb)+bytes(m.uc.mem_read(qptr,16)))

cases=set()
for p in (1,3,5,7,9,15,17,19,21,29,31,32):
    for depth in range(8):
        for exponent in (-1022,-341,-340,-17,-1,0,1,17,339,340,1023):
            for fraction in (0,1,(1<<52)-1):
                for sign in (-1,1):
                    cases.add((((exponent+1023)<<52)|fraction,bits(float(F(sign*p,1<<depth)))))
for _ in range(args.samples):
    x=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
    p=rng.randrange(1,33);depth=rng.randrange(8)
    cases.add((x,bits(float(F(-p if rng.getrandbits(1) else p,1<<depth)))))
hard=json.loads((root/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
for group in hard['groups']:cases.update((int(c['a'],16),int(c['b'],16)) for c in group['cases'])
context=dict(active=False,expected=None);trusted=0
checked=m.elf.symbols['pow_root128_decide']&~1
def hook(uc,address,size,unused):
    global trusted
    if context['active'] and address==checked:
        sp=uc.reg_read(UC_ARM_REG_SP)
        if bytes(uc.mem_read(sp+8,1))[0]:
            cell=struct.unpack('<Q',bytes(uc.mem_read(sp,8)))[0]
            assert context['expected'] in (cell,cell+1),('trusted pair',context,hex(cell))
            trusted+=1
m.uc.hook_add(UC_HOOK_CODE,hook);m.uc.ctl_flush_tb()
oracle=Oracle();accepted=declined=public=0
for i,(x,y) in enumerate(sorted(cases)):
    expected=oracle.reference('pow',x,y);context.update(active=True,expected=expected)
    got=m.call('pow_root128',x,y)[0];context['active']=False
    if got==0x7FF8000000000000:declined+=1
    else:assert got==expected,(hex(x),hex(y),hex(got),hex(expected));accepted+=1
    digest.update(struct.pack('<3Q',x,y,got))
    if i%31==0:
        assert m.call('_ZN12compact_math3powEdd',x,y)[0]==expected,('public',hex(x),hex(y))
        public+=1
assert accepted>1000 and trusted>10
record=dict(status='PASS_LAZY_FACTOR_FRACTION_AND_MPFR_ENDPOINTS',core_cases=counts,
    direct_power_cases=len(cases),accepted=accepted,declined=declined,new_trusted_calls=trusted,
    public_mpfr_calls=public,result_sha256=digest.hexdigest(),
    elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Exact Fraction square, multiply and reciprocal-square-root enclosures; directed MPFR for every accepted prefix and selected public powers. Actual trusted pairs checked. ABI and bounded writes on every ARM call. Finite software tests, not all-input correctness, totality, resource/isolation, cache or physical timing qualification.')
args.json.write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',counts,len(cases),'powers;',accepted,'accepted;',trusted,'trusted;',public,'public MPFR calls.')
