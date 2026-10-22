"""Check experimental Q64 ARM endpoints and new trusted cells independently."""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP,bits,real
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf',type=Path,required=True)
parser.add_argument('--bootrom',type=Path,required=True)
parser.add_argument('--json',type=Path,required=True)
parser.add_argument('--samples',type=int,default=6000)
args=parser.parse_args()
m=Machine(args.elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=args.bootrom)
oracle=Oracle();rng=random.Random(0x11164063);digest=hashlib.sha256();mask=(1<<64)-1
qptr,bptr=SP-15000,SP-14936


def state(a,e,r):return struct.pack('<QiI',a,e,r)
def unpack(pointer):return struct.unpack('<QiI',bytes(m.uc.mem_read(pointer,16)))
def interval(a,e,r):return F(a-r)*F(2)**(e-63),F(a+r)*F(2)**(e-63)
def rounded_fraction(value):
    exponent=value.numerator.bit_length()-value.denominator.bit_length()
    if value<F(2)**exponent:exponent-=1
    if exponent>1023:return 0x7FF0000000000000
    scaled=value*F(2)**(1074 if exponent < -1022 else 52-exponent)
    q,r=divmod(scaled.numerator,scaled.denominator)
    q+=2*r>scaled.denominator or (2*r==scaled.denominator and q&1)
    if exponent < -1022:return q
    if q==1<<53:q>>=1;exponent+=1
    return 0x7FF0000000000000 if exponent>1023 else ((exponent+1023)<<52)|(q- (1<<52))


squares=products=boundaries=packed=neighbors=trusted_intervals=0
for index in range(args.samples):
    a=rng.randrange(1<<63,1<<64);b=rng.randrange(1<<63,1<<64)
    if index%7==0:a=rng.choice((1<<63,(1<<63)+1,(1<<64)-1,(1<<64)-2))
    e,be=rng.randrange(-1022,1024),rng.randrange(-1022,1024)
    error=0 if index%5==0 else rng.randrange((1<<20)+1)
    image=state(a,e,error);m.uc.mem_write(qptr,image)
    m.call('pow_integer64_square',qptr,0,32)
    center,exponent,radius=unpack(qptr);lo,hi=interval(a,e,error);left,right=interval(center,exponent,radius)
    assert 1<<63<=center<1<<64 and exponent in (2*e,2*e+1)
    assert left<=lo*lo<=hi*hi<=right,(index,'square')
    digest.update(image+bytes(m.uc.mem_read(qptr,16)));squares+=1
    m.uc.mem_write(qptr,image);base=state(b,be,0);m.uc.mem_write(bptr,base)
    m.call('pow_integer64_base',qptr,bptr,32)
    center,exponent,radius=unpack(qptr);left,right=interval(center,exponent,radius);factor=F(b)*F(2)**(be-63)
    assert 1<<63<=center<1<<64 and exponent in (e+be,e+be+1)
    assert left<=lo*factor<=hi*factor<=right,(index,'base')
    assert bytes(m.uc.mem_read(bptr,16))==base
    digest.update(image+base+bytes(m.uc.mem_read(qptr,16)));products+=1

for index in range(args.samples):
    cell=(rng.randrange(723,1324)<<52)|rng.getrandbits(52)
    if index%11==0:cell=(cell&~((1<<52)-1))|rng.choice((0,1,2,(1<<52)-2,(1<<52)-1))
    error=rng.randrange(1001)
    midpoint=(F(real(cell))+F(real(cell+1)))/2
    coefficient=((((cell&((1<<52)-1))|(1<<52))<<1)+1)<<10
    a=(1<<127)//coefficient+rng.randrange(-2002,2003)
    a=min((1<<64)-1,max(1<<63,a));e=1022-int(cell>>52)
    image=state(a,e,error);m.uc.mem_write(qptr,image)
    value=m.call('pow_integer64_distance',qptr,cell)[0]
    assert value!=mask
    distance=value&0xFFFFFFFF;distance=distance-(1<<32) if distance>>31 else distance
    radius=value>>43;step=(value>>32)&2047
    assert radius==error+3 and step==a>>53
    exact=F(a*coefficient,1<<64)-(1<<63)
    assert 0<=exact-distance<3
    packed+=1
    lo,hi=interval(a,e,error)
    for hop in (-2,-1,0,1):
        target_cell=cell+hop
        if target_cell>>52 != cell>>52:continue
        other=(F(real(target_cell))+F(real(target_cell+1)))/2
        nominal=distance+hop*step;bound=radius+abs(hop)
        scale=F(2)**63
        assert nominal-bound <= (lo*other-1)*scale <= (hi*other-1)*scale <= nominal+bound
        side=(nominal>bound)-(nominal < -bound)
        if side:assert lo*other>1 if side>0 else hi*other<1
        if abs(nominal)<=bound and bound<=511 and target_cell&((1<<52)-1):
            assert rounded_fraction(1/hi) in (target_cell,target_cell+1)
            assert rounded_fraction(1/lo) in (target_cell,target_cell+1)
            trusted_intervals+=1
        neighbors+=1
    side=m.call('pow_integer64_boundary',qptr,cell)[0]&0xFFFFFFFF
    side=side-(1<<32) if side>>31 else side
    if side:assert lo*midpoint>1 if side>0 else hi*midpoint<1
    assert bytes(m.uc.mem_read(qptr,16))==image
    boundaries+=1;digest.update(image+struct.pack('<Q',value))

context=dict(active=False,first=False,x=None,y=None,expected=None)
initial_squares=trusted_calls=0;witnesses=[]
core_addresses={m.elf.symbols[name]&~1 for name in ('pow_integer64_square','pow_integer64_base')}
checked=m.elf.symbols['pow_dyadic128_checked']&~1


def hook(uc,address,size,unused):
    global initial_squares,trusted_calls
    if not context['active']:return
    if address in core_addresses and not context['first']:
        pointer=uc.reg_read(UC_ARM_REG_R0);a,e,r=struct.unpack('<QiI',bytes(uc.mem_read(pointer,16)))
        exact=F(real(context['x']))**2
        exponent=exact.numerator.bit_length()-exact.denominator.bit_length()
        if exact<F(2)**exponent:exponent-=1
        scaled=exact*F(2)**(63-exponent);center,tail=divmod(scaled.numerator,scaled.denominator)
        assert (a,e,r)==(center,exponent,int(tail!=0)),('first exact square',context['x'])
        initial_squares+=1;context['first']=True
    if address==checked:
        sp=uc.reg_read(UC_ARM_REG_SP);cell=struct.unpack('<Q',bytes(uc.mem_read(sp,8)))[0]
        first=bytes(uc.mem_read(sp+8,1))[0]
        if first:
            assert context['expected'] in (cell,cell+1),('new trusted cell',context['x'],context['y'],cell,context['expected'])
            assert cell&((1<<52)-1)
            trusted_calls+=1
            if len(witnesses)<8:witnesses.append(dict(x=f"{context['x']:016x}",y=f"{context['y']:016x}",cell=f'{cell:016x}',expected=f"{context['expected']:016x}"))


m.uc.hook_add(UC_HOOK_CODE,hook);m.uc.ctl_flush_tb()
cases=set()
for n in range(3,33):
    for exponent in (-1022,-341,-340,-65,-32,-1,0,1,31,64,339,340,1023):
        for fraction in (0,1,(1<<52)-1,rng.getrandbits(52)):
            cases.add((((exponent+1023)<<52)|fraction,bits(-float(n))))
for unused in range(args.samples):
    n=rng.randrange(3,33);exponent=rng.randrange(-40,41)
    cases.add((((exponent+1023)<<52)|rng.getrandbits(52),bits(-float(n))))
hard=json.loads((root/'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
for group in hard['groups']:
    for c in group['cases']:
        x,y=int(c['a'],16),int(c['b'],16)
        if not y&0xFFFFFFFF and 0xC0080000<=y>>32<=0xC0400000:cases.add((x,y))
accepted=declined=public=0
for index,(x,y) in enumerate(sorted(cases)):
    expected=oracle.reference('pow',x,y)
    context.update(active=True,first=False,x=x,y=y,expected=expected)
    got=m.call('pow_integer64_negative',x,y>>32)[0]
    context['active']=False
    if got==0x7FF8000000000000:declined+=1
    else:assert got==expected,(hex(x),hex(y),hex(got),hex(expected));accepted+=1
    digest.update(struct.pack('<3Q',x,y,got))
    if index%31==0:
        assert m.call('_ZN12compact_math3powEdd',x,y)[0]==expected
        public+=1
assert accepted>1000 and initial_squares>1000 and trusted_intervals>100
record=dict(status='PASS_DIAGNOSTIC_Q64_ENDPOINT_AND_TRUSTED_CELL_TESTS',square_endpoint_cases=squares,
    exact_base_product_endpoint_cases=products,packed_distance_cases=packed,cached_neighbor_cases=neighbors,
    direct_midpoint_cases=boundaries,complete_two_cell_interval_endpoint_checks=trusted_intervals,
    direct_power_cases=len(cases),accepted_power_results=accepted,declined_power_results=declined,public_mpfr_calls=public,
    exact_first_square_states=initial_squares,actual_new_trusted_calls=trusted_calls,witnesses=witnesses,
    result_sha256=digest.hexdigest(),elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Independent exact Fraction enclosure endpoints, neighboring midpoint intervals and reciprocal endpoint RNE; directed MPFR for accepted/public negative powers. Hooks check exact first-square states and actual new trusted-cell calls. Every call checks ABI and bounded writes. Diagnostic image only; no complete qualification, general totality or hardware timing claim.')
args.json.write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',len(cases),'powers;',accepted,'accepted;',trusted_calls,'new trusted calls;',trusted_intervals,'complete two-cell interval checks.')
