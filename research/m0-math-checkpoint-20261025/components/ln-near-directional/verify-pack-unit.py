"""Bare exact-source packer execution against rational interval endpoints."""
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
sys.path.insert(0, str(ROOT / '.build/m0-float-fma-qualification-20261023'))
sys.path.insert(0, str(ROOT / '.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine, SP
from oracles import round_ratio
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

proof = json.loads((W / 'certificate.json').read_text())
build = json.loads((W / 'pack-unit-build.json').read_text())
assert hashlib.sha256((W / 'native_eabi_m0_log70.inc').read_bytes()).hexdigest() == proof['source_sha256'] == build['source_sha256']
upper, lower = F(proof['upper']), F(proof['lower'])
argument = F(proof['quotient_error_bound'])
m = Machine(W / 'pack-unit.elf', True, stack_bytes=128)
accesses = [0]
def access(*args):
    accesses[0] += 1
m.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access, begin=0xd0000060, end=0xd000007b)
states = [struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1), struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)]
jobs = []
rng = random.Random(0x10D17070)
for den in range(8065, 8321):
    edge = (argument * den).__ceil__() - 1
    for distance in (0, 1, 2, 3, 4, 5):
        for side in (-1, 1):
            for add in (False, True):
                r2, r3, r4 = rng.choice((-1,0)), rng.choice((-1,0,1)), rng.choice((-2,-1,0,1))
                bias = -4*r3 + rng.choice((-1,1))*(6*r2+3*r4)
                residue = rng.choice((-edge,-1,0,1,edge))
                jobs.append((den, bias, residue, add, False, distance, side))
    for distance in (0,1,2,3,4):
        for side in (-1,1):
            jobs.append((den,0,0,False,True,distance,side))

digest, counts, endpoint_checks = hashlib.sha256(), [], 0
accepted = declined = calls = 0
for i, (den,bias,residue,add,center,distance,side) in enumerate(jobs):
    width = (56,57,58,60,64,65)[i % 6]
    shift = width-53
    half = 1 << (shift-1)
    tail = half + side*distance
    if not 0 <= tail < 2*half:
        continue
    retained = (1 << 52) + (0,1,(1 << 52)-1,1 << 51)[i % 4]
    if half == 4:
        retained += 32 if retained == 1 << 52 else 0
    q = (retained << shift) + tail
    high, low = q >> 64, q & ((1 << 64)-1)
    assert high in (0,1)
    sign = bool(i & 1)
    meta = (bias+16) | (int(add)<<6) | (int(center)<<7) | (int(sign)<<8) | (high<<9) | ((den-8065)<<10)
    assert 0 <= bias+16 < 64
    config = meta | ((residue & 0xffffffff)<<32)
    safe = distance >= 4
    if not safe and distance:
        safe = center or (den*(12*distance-bias)+12*residue >= 18*den if (side>0)==add
                          else den*(12*distance+bias)-12*residue >= 21*den)
    expected = round_ratio(q,1,-70,64,sign) if safe else 0x7ff800000000019a
    if safe:
        if center:
            error_low, error_high = -F(1,2), F(1,2)
        else:
            e = F(bias,12)-F(residue,den)
            error_low, error_high = (e-lower,e+upper) if add else (-e-upper,-e+lower)
        for error in (error_low, error_high):
            exact = F(q)-error
            assert round_ratio(exact.numerator,exact.denominator,-70,64,sign) == expected
            endpoint_checks += 1
        accepted += 1
    else:
        declined += 1
    for j,state in enumerate(states):
        m.uc.mem_write(0xd0000060,state)
        got,_,cost = m.call('audit_near_pack',low,config,count=(i%509==0))
        assert got == expected,(i,hex(got),hex(expected),den,bias,residue,add,center,distance,side)
        assert bytes(m.uc.mem_read(0xd0000060,28)) == state
        digest.update(struct.pack('<QQQB',low,config,got,j))
        if i%509==0:
            counts.append(cost)
        calls += 1
assert accesses[0] == 0
out = dict(status='PASS_EXACT_INLINE_NEAR_PACK_BARE_ARM_AND_FRACTION_ENDPOINTS',
    actual_ARM_calls=calls, configurations=accepted+declined, accepted=accepted, declined=declined,
    rational_RNE_endpoint_checks=endpoint_checks, all256_denominators=True,
    all_results_exact=True, midpoint_always_declines=True,
    source_sha256=proof['source_sha256'], unit_ELF_sha256=build['unit_ELF_sha256'],
    firmware_or_ROM_mapped=False, SIO_accesses=accesses[0], both_SIO_states_preserved=True,
    PCS_SP_bounded_writes_every_call=True, observed_stack_bytes=SP-m.stack_lowest,
    profiled_instruction_range=[min(counts),max(counts)], transcript_sha256=digest.hexdigest(),
    public_qualification=False, hardware_accessed=False)
(W / 'pack-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
