"""Execute exact inline pack source with signed rational h-error endpoints."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import random
import struct
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023'))
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine, SP
from oracles import round_ratio
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

proof = json.loads((W/'certificate.json').read_text())
build = json.loads((W/'pack-unit-build.json').read_text())
assert hashlib.sha256((W/'native_eabi_m0_log70.inc').read_bytes()).hexdigest() == proof['source_sha256'] == build['source_sha256']
base, argument = F(proof['residual_aware_base']),F(proof['generic_quotient_error'])
m = Machine(W/'pack-unit.elf',True,stack_bytes=128)
accesses=[0]
def access(*args):
    accesses[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
rng=random.Random(0xC01D17070)
jobs=[]
for index in range(1024):
    den=2049+2*index
    k=(-1022,-512,-2,-1,0,1,2,511,1023)[index%9]
    extra=(abs(k)+1)//2
    for variant in range(12):
        offset=rng.randrange(1<<42)
        if variant<4:
            offset=(1<<41)+(-1,0,1,1<<40)[variant]
        negative=offset<(1<<41)
        delta=abs(offset-(1<<41))
        H=F(delta<<29,den)
        h=H.__floor__()+(-6,-3,-1,0,1,3,6)[variant%7]
        if h<0 or abs(F(h)-H)>=argument:
            continue
        distance=(0,1,6+extra,7+extra,8+extra,15+extra,16+extra,17+extra)[variant%8]
        width=64+(index+variant)%17
        side=(-1,1)[(variant//2)&1]
        retained=(1<<52)+(0,1,(1<<51),(1<<52)-1)[(index+variant)%4]
        jobs.append((index,k,offset,negative,delta,H,h,extra,distance,width,side,retained))

# Power-of-two and immediately-preceding outputs have asymmetric neighbor
# gaps. Respect the physical k/width correlation at the smallest binade.
for width in range(64,81):
    for index in (0,1,255,511,512,767,1022,1023):
        for k in ((-1,0) if width==64 else (-1022,-1,0,1,1023)):
            extra=(abs(k)+1)//2
            den=2049+2*index
            offset=(1<<40)+65
            delta=(1<<41)-offset
            H=F(delta<<29,den)
            for j in (-6,-1,0,1,6):
                h=H.__floor__()+j
                if abs(F(h)-H)>=argument:continue
                half=1<<(width-54)
                jobs.append((index,k,offset,True,delta,H,h,extra,half,width,-1,1<<52))
                jobs.append((index,k,offset,True,delta,H,h,extra,half-1,width,1,(1<<53)-1))

accepted=declined=endpoint_checks=calls=0
digest=hashlib.sha256();profiled=[];denominators=set();distances=set();orientations=set()
for i,(index,k,offset,negative,delta,H,h,extra,distance,width,side,retained) in enumerate(jobs):
    shift=width-53
    half=1<<(shift-1)
    tail=half+side*distance
    assert 0<=tail<2*half
    q=(retained<<shift)+tail
    assert q.bit_length()==width
    high,low=q>>64,q&((1<<64)-1)
    output_negative=k<0
    v=-1 if negative!=output_negative else 1
    den=2049+2*index
    residue=(delta<<29)-h*den
    assert abs(residue)<1<<15
    assert ((residue+(1<<31))%(1<<32))-(1<<31)==residue
    safe=distance>=16+extra
    if not safe and distance:
        directed=v*residue if side>0 else -v*residue
        safe=(distance-(7+extra))*den+directed>=0
    expected=round_ratio(q,1,-70,64,output_negative) if safe else int(build['decline_bits'],16)
    if safe:
        error=-v*F(residue,den)
        for e in (error-base-extra,error+base+extra):
            exact=F(q)-e
            got=round_ratio(exact.numerator,exact.denominator,-70,64,output_negative)
            assert got==expected,(i,den,residue,distance,side,hex(got),hex(expected))
            endpoint_checks+=1
        accepted+=1
    else:
        declined+=1
    xbits=((k+1023)<<52)+(index<<42)+offset
    payload=struct.pack('<QQQIIII',low,xbits,int(output_negative)<<63,high,extra,h&0xffffffff,0)
    assert len(payload)==40
    m.uc.mem_write(0x20001000,payload)
    for state_index,state in enumerate(states):
        m.uc.mem_write(0xd0000060,state)
        got,_,count=m.call('audit_main_pack',0x20001000,count=(i%509==0))
        assert got==expected,(i,hex(got),hex(expected),den,residue,distance,side)
        assert bytes(m.uc.mem_read(0xd0000060,28))==state
        assert bytes(m.uc.mem_read(0x20001000,40))==payload
        digest.update(payload+struct.pack('<QB',got,state_index))
        if i%509==0:profiled.append(count)
        calls+=1
    denominators.add(den);distances.add(distance);orientations.add(v)
assert accesses[0]==0 and len(denominators)==1024
out=dict(status='PASS_EXACT_INLINE_MAIN_PACK_ARM_AND_RATIONAL_ENDPOINTS',
    source_sha256=proof['source_sha256'],unit_ELF_sha256=build['unit_ELF_sha256'],
    actual_ARM_calls=calls,configurations=len(jobs),accepted=accepted,declined=declined,
    rational_RNE_endpoint_checks=endpoint_checks,all1024_denominators=True,
    both_magnitude_orientations=sorted(orientations),pack_widths=[64,80],
    both_SIO_states_preserved=True,SIO_accesses=accesses[0],input_memory_unchanged=True,
    firmware_or_ROM_mapped=False,PCS_SP_bounded_writes_every_call=True,
    observed_stack_bytes=SP-m.stack_lowest,profiled_instruction_range=[min(profiled),max(profiled)],
    transcript_sha256=digest.hexdigest(),public_qualification=False,hardware_accessed=False)
(W/'pack-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
