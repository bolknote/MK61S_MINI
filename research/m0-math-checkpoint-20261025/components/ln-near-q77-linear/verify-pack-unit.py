"""Bare exact Q77 pack source versus rational interval endpoints."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import random
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023'))
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine,SP
from oracles import round_ratio
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE

proof=json.loads((W/'certificate.json').read_text())
build=json.loads((W/'pack-unit-build.json').read_text())
assert hashlib.sha256((W/'native_eabi_m0_log70.inc').read_bytes()).hexdigest()==proof['source_sha256']==build['source_sha256']
base,argument=F(proof['remaining_symmetric_base']),F(proof['corrected_argument_bound'])
m=Machine(W/'pack-unit.elf',True,stack_bytes=128)
accesses=[0]
def access(*args):accesses[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
rng=random.Random(0x77170C01D)
jobs=[]
for den in range(8065,8321):
    edge=(argument*den).__ceil__()-1
    for distance in range(6):
        for side in (-1,1):
            for add in (False,True):
                r2=rng.choice((-1,0));r3=rng.choice((-1,0,1));r4=rng.choice((-2,-1,0,1));r5=rng.choice((-2,-1,0,1,2))
                bias=5*(-4*r3+rng.choice((-1,1))*(6*r2+3*r4))-12*r5
                residue=rng.choice((-edge,-1,0,1,edge))
                jobs.append((den,bias,residue,add,False,distance,side,False))
    for distance in range(5):
        for side in (-1,1):jobs.append((den,0,0,False,True,distance,side,False))
    for add in (False,True):
        for bias in (-104,104):
            for residue in (-edge,edge):jobs.append((den,bias,residue,add,False,0,-1,True))

accepted=declined=calls=endpoint_checks=0
digest=hashlib.sha256();profiled=[]
for i,(den,bias,residue,add,center,distance,side,binade) in enumerate(jobs):
    width=63+i%10;shift=width-53;half=1<<(shift-1)
    retained=(1<<52)+(0,1,1<<51,(1<<52)-1)[i%4]
    if binade:retained=1<<52;distance=half
    tail=half+side*distance
    assert 0<=tail<2*half
    q=(retained<<shift)+tail
    assert q.bit_length()==width
    high,low=q>>64,q&((1<<64)-1)
    sign=bool(i&1)
    safe=distance>=4
    if not safe and distance:
        safe=center or (den*(60*distance-bias)+60*residue>=90*den if (side>0)==add else den*(60*distance+bias)-60*residue>=90*den)
    expected=round_ratio(q,1,-77,64,sign) if safe else int(build['decline_bits'],16)
    if safe:
        e=F(bias,60)-F(residue,den)
        lo,hi=(-F(1,2),F(1,2)) if center else ((e-base,e+base) if add else (-e-base,-e+base))
        for error in (lo,hi):
            exact=F(q)-error
            assert round_ratio(exact.numerator,exact.denominator,-77,64,sign)==expected,(i,den,bias,residue,distance,side)
            endpoint_checks+=1
        accepted+=1
    else:declined+=1
    meta=(bias+128)|(int(add)<<8)|(int(center)<<9)|(int(sign)<<10)|(high<<11)|((den-8065)<<19)
    assert 0<=bias+128<256 and high<256
    config=meta|((residue&0xffffffff)<<32)
    for state_index,state in enumerate(states):
        m.uc.mem_write(0xd0000060,state)
        got,_,cost=m.call('audit_near_pack77',low,config,count=(i%509==0))
        assert got==expected,(i,hex(got),hex(expected),den,bias,residue,distance,side)
        assert bytes(m.uc.mem_read(0xd0000060,28))==state
        digest.update(struct.pack('<QQQB',low,config,got,state_index));calls+=1
        if i%509==0:profiled.append(cost)
assert accesses[0]==0
out=dict(status='PASS_EXACT_Q77_NEAR_PACK_BARE_ARM_AND_RATIONAL_ENDPOINTS',
    source_sha256=proof['source_sha256'],unit_ELF_sha256=build['unit_ELF_sha256'],
    actual_ARM_calls=calls,configurations=len(jobs),accepted=accepted,declined=declined,
    rational_RNE_endpoint_checks=endpoint_checks,all256_denominators=True,
    signed_bias_residue_and_both_magnitude_orientations=True,output_widths=[63,72],binade_boundaries_included=True,
    SIO_accesses=accesses[0],both_SIO_states_preserved=True,PCS_SP_bounded_writes_every_call=True,
    observed_stack_bytes=SP-m.stack_lowest,profiled_instruction_range=[min(profiled),max(profiled)],
    transcript_sha256=digest.hexdigest(),firmware_or_ROM_mapped=False,hardware_accessed=False)
(W/'pack-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
