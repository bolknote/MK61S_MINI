"""Bare actual ARM gates and independent rational RNE enclosure endpoints."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
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
from propagation import ARGUMENT,gate,interval,radii40,coefficient_bias20

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
proof=json.loads((W/'certificate.json').read_text())
build=json.loads((W/'pack-unit-build.json').read_text())
assert sha(W/'native_eabi_m0_log70.inc')==proof['source_sha256']==build['source_sha256']
assert sha(W/'pack-unit.elf')==build['unit_ELF_sha256']
assert sha(W/'propagation.py')==proof['propagation_source_sha256']
m=Machine(W/'pack-unit.elf',True,stack_bytes=512)
accesses=[0]
def access(*args):accesses[0]+=1
m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access,begin=0xd0000060,end=0xd000007b)
states=[struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)]
calls=configurations=endpoints=pack_calls=coefficient_calls=midpoint_calls=0
accepted=declined=equality=0;digest=hashlib.sha256();costs=[];selected=set()
coverage=set();widths=set();pack_names=set()
sentinel=int(build['decline_bits'],16)

def checked(name,a,config,fixture,expected):
    global calls
    for state_index,state in enumerate(states):
        m.uc.mem_write(0x20000000,fixture)
        m.uc.mem_write(0xd0000060,state)
        profile=calls%997==0
        got,_,cost=m.call(name,a,config,count=profile)
        assert got==expected,(name,hex(a),hex(config),hex(got),hex(expected),fixture.hex())
        assert bytes(m.uc.mem_read(0xd0000060,28))==state
        assert bytes(m.uc.mem_read(0x20000000,32))==fixture
        digest.update(name.encode()+struct.pack('<QQQB',a,config,got,state_index)+fixture)
        if profile:costs.append(cost)
        calls+=1

def raw_input(den,negative,n,sign):
    index=(den-2049)//2
    exponent=1023-n if sign else 1023+n
    assert 1<=exponent<=2046
    offset_high=100 if negative else 700
    return (exponent<<52)+(index<<42)+(offset_high<<32)+0x7fffffc1

def fixture(raw,residue,fourth,fifth,distance,above):
    den=2049+2*((raw&((1<<52)-1))>>42)
    negative=not bool(raw&(1<<41))
    delta_low=((raw&0xffffffff)<<29)&0xffffffff
    if negative:delta_low=(-delta_low)&0xffffffff
    h_low=((delta_low-residue)*pow(den,-1,1<<32))&0xffffffff
    return struct.pack('<8I',raw&0xffffffff,raw>>32,h_low,fourth,fifth,distance,int(above),residue&0xffffffff)

def check_point(name,distance,above,raw,n,sign,den,residue,negative,fourth,fifth):
    global endpoints,pack_calls
    width=64+(pack_calls//2)%17;shift=width-53;half=1<<(shift-1)
    retained=(1<<52)+(0,1,1<<51,(1<<52)-1)[(pack_calls//2)%4]
    point=(retained<<shift)+half+(distance if above else -distance)
    assert point.bit_length()==width
    expected=round_ratio(point,1,-70,64,sign)
    errors=interval(sign,n,den,residue,negative,fourth,fifth)
    for error in errors:
        true=F(point)-error
        assert round_ratio(true.numerator,true.denominator,-70,64,sign)==expected,(name,distance,above,n,den,residue,errors)
        endpoints+=1
    config=(point>>64)|(n<<16)|(int(sign)<<26)
    checked(name,point&((1<<64)-1),config,fixture(raw,residue,fourth,fifth,distance,above),expected)
    pack_calls+=2;widths.add(width);pack_names.add(name)

for den in (2049,2079,2081,3583,3585,4095):
    edge=(ARGUMENT*den).__ceil__()-1
    for n in (0,1,512,1023):
        for sign in (False,True):
            if sign and n in (0,1023):continue
            for negative in (False,True):
                raw=raw_input(den,negative,n,sign)
                for f4 in range(4):
                    for f5 in range(5):
                        fourth=(den<<10)|f4
                        fifth=30000+f5
                        bias=coefficient_bias20(fourth,fifth,negative)
                        lo,hi=radii40(den,negative)
                        if sign:lo,hi=hi,lo;bias=-bias
                        coverage.add((den,negative,sign,n,((fourth+2)&3)-2,fifth-5*((fifth+2)//5)))
                        for residue in (-edge,-den,-1,0,edge):
                            oriented=-residue if negative!=sign else residue
                            adjust=2*bias*den-40*oriented
                            for above in (False,True):
                                limit=hi if above else lo+20*n
                                rhs=limit*den+(adjust if above else -adjust)
                                critical=-((-rhs)//(40*den))
                                for distance in sorted({0,max(1,critical-1),max(1,critical),max(1,critical+1)}):
                                    if distance>527:continue
                                    expected=gate(distance,above,sign,n,den,oriented,negative,fourth,fifth)
                                    margin=(40*distance-limit)*den+(-adjust if above else adjust)
                                    assert expected==(margin>=0)
                                    equality+=int(margin==0)
                                    accepted+=int(expected);declined+=int(not expected)
                                    f=fixture(raw,residue,fourth,fifth,distance,above)
                                    checked('audit_coefficient',(fifth<<32)|fourth,(n<<16)|(int(sign)<<26),f,int(expected))
                                    coefficient_calls+=2;configurations+=1
                                    if not expected or not distance:continue
                                    extra=(n+1)//2
                                    for name in ('audit_exact','audit_raw'):
                                        if name=='audit_exact':
                                            forced=distance<=7+extra and not (n and above and distance>=8)
                                            if not n:forced=forced and distance<(6 if negative else 7) if above else forced and distance<4
                                            forced=forced and -den<=residue<0
                                        else:
                                            radius=7+extra if n else (6 if above else 3 if negative else 4)
                                            directed=oriented if above else -oriented
                                            forced=distance<=15+extra and not (n and above and distance>=14) and (distance-radius)*den+directed<0
                                        key=(name,den,negative,sign,n,f4,f5)
                                        if forced and key not in selected:
                                            check_point(name,distance,above,raw,n,sign,den,residue,negative,fourth,fifth)
                                            selected.add(key)

# Every normal exponent magnitude exercises the inherited ln2 shortcut
# in the actual new packer machine code, including both odd/even n.
for n in range(1,1024):
    for sign in (False,True):
        if sign and n==1023:continue
        den=(2079,2081,3583,3585,4095)[n%5]
        negative=bool(n&1);raw=raw_input(den,negative,n,sign)
        for name,distance in (('audit_exact',8),('audit_raw',14)):
            check_point(name,distance,True,raw,n,sign,den,-den+1,negative,0,0)

# Exact midpoint inputs always reach the unchanged refinement, even
# when an abstract coefficient bound alone would admit one side.
for den in (2081,3585,4095):
    for negative in (False,True):
        for sign,n in ((False,0),(False,1),(True,1)):
            raw=raw_input(den,negative,n,sign);width=68;shift=width-53
            point=((1<<52)<<shift)+(1<<(shift-1));config=(point>>64)|(n<<16)|(int(sign)<<26)
            for name in ('audit_exact','audit_raw'):
                checked(name,point&((1<<64)-1),config,fixture(raw,-1,2,4,0,False),sentinel)
                midpoint_calls+=2
assert accesses[0]==0 and accepted and declined and equality
assert pack_names=={'audit_exact','audit_raw'} and widths==set(range(64,81))
assert calls==coefficient_calls+pack_calls+midpoint_calls
out=dict(status='PASS_BARE_MAIN_LN_COEFFICIENT_AND_PACK_ARM_RATIONAL_ENDPOINTS',
    source_sha256=proof['source_sha256'],candidate_ELF_sha256=proof['candidate_ELF_sha256'],
    unit_ELF_sha256=build['unit_ELF_sha256'],actual_ARM_calls=calls,
    coefficient_ARM_calls=coefficient_calls,coefficient_configurations=configurations,
    coefficient_accepted_configurations=accepted,coefficient_declined_configurations=declined,
    exact_integer_equality_configurations=equality,pack_ARM_calls=pack_calls,
    new_coefficient_forced_pack_configurations=len(selected),midpoint_decline_ARM_calls=midpoint_calls,
    rational_RNE_endpoint_checks=endpoints,all_normal_n_magnitudes_1_through_1023=True,
    bands_boundaries_both_offset_and_output_signs_and_all_coefficient_residues=True,
    output_widths=[64,80],signs_parities_and_binade_carries=True,
    SIO_accesses=accesses[0],both_SIO_states_and_input_fixture_preserved=True,
    PCS_SP_bounded_writes_every_call=True,observed_stack_bytes=SP-m.stack_lowest,
    profiled_instruction_range=[min(costs),max(costs)],transcript_sha256=digest.hexdigest(),
    full_firmware_or_ROM_loaded=False,new_public_candidate_calls=0,hardware_accessed=False,
    scope='Actual helper and pack source. New-predicate arithmetic plus rational endpoints and inherited ln2 upper paths; abstract coefficient/residue configurations are not additional public numerical inputs.')
(W/'pack-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
