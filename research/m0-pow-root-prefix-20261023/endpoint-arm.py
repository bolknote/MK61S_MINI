"""Independently check the composed root prefix, interval roots and exact-base specialization."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root=Path.cwd()
sys.path.insert(0,str(root/'tests'))
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
rng=random.Random(0x11812863)
qptr,bptr=SP-15000,SP-14936
root_name=next(name for name in m.elf.symbols if name.startswith('_ZL') and 'root64_sqrt' in name)
digest=hashlib.sha256()
base_calls=aliases=root_calls=0


def state(h,l,e,r):return struct.pack('<QQiI',h,l,e,r)
def root_interval(image):
    h,e,r=struct.unpack('<QiI',image)
    return F(h-r)*F(2)**(e-63),F(h+r)*F(2)**(e-63)


for index in range(args.samples):
    a=state(rng.randrange(1<<63,1<<64),rng.getrandbits(64),rng.randrange(-1022,1024),rng.randrange(131073))
    b=state(rng.randrange(1<<63,1<<64),0,rng.randrange(-1022,1024),0)
    if index%7==0:
        h,l,e,r=struct.unpack('<QQiI',a)
        a=state(h,0,e,0)
    alias=index%17==0
    if alias:a=b
    def run(name):
        m.uc.mem_write(qptr,a);m.uc.mem_write(bptr,b)
        m.call(name,qptr,qptr if alias else bptr,32)
        if not alias:assert bytes(m.uc.mem_read(bptr,24))==b
        return bytes(m.uc.mem_read(qptr,24))
    before=run('pow_integer128_multiply')
    after=run('pow_integer128_base')
    assert before==after,(index,'exact base centers/radii')
    digest.update(a+b+after);base_calls+=1;aliases+=alias
    h=rng.randrange(1<<63,1<<64);e=rng.randrange(-1022,1024)
    error=0 if index%5==0 else rng.randrange((1<<20)+1)
    if index%31==0:h=(1<<63)+rng.randrange(8)
    image=struct.pack('<QiI',h,e,error);m.uc.mem_write(qptr,image)
    m.call(root_name,qptr,0,32)
    output=bytes(m.uc.mem_read(qptr,16));lo,hi=root_interval(image);left,right=root_interval(output)
    assert 1<<63<=struct.unpack('<Q',output[:8])[0]<1<<64
    assert left*left<=lo<=hi<=right*right,(index,'composed interval root')
    digest.update(image+output);root_calls+=1

oracle=Oracle()
cases=set()
for p in (1,3,5,7,15,17,31,32):
    for depth in range(8):
        for exponent in (-1022,-341,-340,-17,-1,0,1,17,339,340,1023):
            for fraction in (0,1,(1<<52)-1):
                x=((exponent+1023)<<52)|fraction
                for sign in (-1,1):cases.add((x,bits(float(F(sign*p,1<<depth)))))
for _ in range(args.samples):
    x=(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
    p=rng.randrange(1,33);depth=rng.randrange(8)
    cases.add((x,bits(float(F(-p if rng.getrandbits(1) else p,1<<depth)))))
hard=json.loads((root/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
for group in hard['groups']:
    cases.update((int(c['a'],16),int(c['b'],16)) for c in group['cases'])
context=dict(active=False,expected=None)
checked=m.elf.symbols['pow_root128_decide']&~1
trusted=0


def hook(uc,address,size,unused):
    global trusted
    if context['active'] and address==checked:
        sp=uc.reg_read(UC_ARM_REG_SP)
        cell=struct.unpack('<Q',bytes(uc.mem_read(sp,8)))[0]
        if bytes(uc.mem_read(sp+8,1))[0]:
            assert context['expected'] in (cell,cell+1),('new trusted pair',context,hex(cell))
            trusted+=1


m.uc.hook_add(UC_HOOK_CODE,hook);m.uc.ctl_flush_tb()
accepted=declined=public=0
for index,(x,y) in enumerate(sorted(cases)):
    expected=oracle.reference('pow',x,y)
    context.update(active=True,expected=expected)
    got=m.call('pow_root128',x,y)[0]
    context['active']=False
    if got==0x7FF8000000000000:declined+=1
    else:
        assert got==expected,(hex(x),hex(y),hex(got),hex(expected))
        accepted+=1
    digest.update(struct.pack('<3Q',x,y,got))
    if index%31==0:
        assert m.call('_ZN12compact_math3powEdd',x,y)[0]==expected,('public',hex(x),hex(y))
        public+=1
assert accepted>1000 and trusted>10
record=dict(status='PASS_ROOT_PREFIX_DIAGNOSTIC_ENDPOINTS',exact_base_bitwise_comparisons=base_calls,
    exact_base_aliases=aliases,interval_root_endpoint_cases=root_calls,direct_power_cases=len(cases),
    accepted_power_results=accepted,declined_power_results=declined,new_trusted_calls=trusted,
    public_mpfr_calls=public,result_sha256=digest.hexdigest(),elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Independent exact Fraction root enclosures; exact-base ARM states bitwise equal to the qualified general multiply; directed MPFR for every accepted prefix and selected complete public calls; actual new trusted pairs checked. Every call checks ABI and bounded writes. Finite software diagnostic, not general totality, resource/isolation/cache qualification or hardware timing.')
args.json.write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',len(cases),'powers;',accepted,'accepted;',trusted,'new trusted calls;',public,'public MPFR calls.')
