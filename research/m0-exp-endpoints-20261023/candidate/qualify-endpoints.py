"""Actual ARM endpoint enclosures and public exp versus independent MPFR."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP, bits, nan
from m0_mpfr_oracle import Oracle, _Number

elf = work/'firmware/mk61s-picocalc-pico-h.elf'
bootrom = root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
machine = Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,bootrom=bootrom)
oracle = Oracle()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
rng = random.Random(0x145E260)
decline = 0x7FF8000000000000
infinity = 0x7FF0000000000000


def subnormal_rne(q,k):
    shift = -k-1012
    assert shift>=11 and q>=0
    whole,tail = divmod(q,1<<shift)
    half = 1<<(shift-1)
    return whole+int(tail>half or (tail==half and whole&1))


property_cases = []
for k in range(-1078,-1022):
    s = -k-1012
    points = [1<<62,(1<<62)+1,(1<<63)-2,(1<<63)-1]
    for _ in range(120):
        q = rng.randrange(1<<62,1<<63)
        points.append(q)
        midpoint = ((q>>s)<<s)+(1<<(s-1))
        points.extend(midpoint+d for d in (-11,-10,-9,-6,-5,-4,-1,0,1,4,5,6,9,10,11)
                      if 1<<62<=midpoint+d<1<<63)
    for error in (5,10):
        property_cases += [(q,k,error) for q in dict.fromkeys(points)]
for k in (1024,1025,1026):
    for error in (5,10):
        property_cases += [(q,k,error) for q in (1<<62,(1<<62)+1,(1<<63)-1)]
accepted = rejected = 0
digest = hashlib.sha256()
for q,k,error in property_cases:
    got = machine.call('mk61_m0_exp_endpoint',q,(error<<32)|(k&0xFFFFFFFF))[0]
    if got==decline:
        rejected += 1
    else:
        if k<0:
            lower,upper = subnormal_rne(q-error,k),subnormal_rne(q+error,k)
            assert got==lower==upper,(q,k,error,hex(got),lower,upper)
        else:
            threshold = (1<<1024)-(1<<970)
            assert ((q-error)<<(k-62))>=threshold
            assert got==infinity
        accepted += 1
    digest.update(struct.pack('<QiIQ',q,k,error,got))
property_report = dict(status='PASS_ACTUAL_ARM_EXP_ENDPOINT_EXACT_INTEGER_INTERVALS',
                       cases=len(property_cases),accepted=accepted,declined=rejected,
                       result_sha256=digest.hexdigest(),elf_sha256=sha(elf),producer_sha256=sha(__file__),
                       scope='Every returned endpoint equals exact integer RNE at both ends of the closed Q62 interval; rejected cells retain the old fallback. Both radii5/10, all subnormal shifts and zero/overflow endpoints.',
                       hardware_accessed=False,goal_complete=False)
(work/'endpoint-property.json').write_text(json.dumps(property_report,indent=2)+'\n')
print('PASS endpoint property:',len(property_cases),'ARM calls;',accepted,'accepted;',rejected,'declined.',flush=True)

# MPFR log(midpoint) seeds only select difficult inputs. Directed MPFR exp
# independently decides every expected result; seed rounding is not an oracle.
ptr = C.POINTER(_Number)
oracle.lib.mpfr_set_ui.argtypes = [ptr,C.c_ulong,C.c_int]
oracle.lib.mpfr_mul_2si.argtypes = [ptr,ptr,C.c_long,C.c_int]
seed = _Number()
oracle.lib.mpfr_init2(C.byref(seed),192)


def midpoint_seed(odd,power):
    oracle.lib.mpfr_set_ui(C.byref(seed),odd,0)
    oracle.lib.mpfr_mul_2si(C.byref(seed),C.byref(seed),power,0)
    oracle.lib.mpfr_log(C.byref(seed),C.byref(seed),0)
    return bits(oracle.lib.mpfr_get_d(C.byref(seed),0))


groups = {}
try:
    numerators = {0,1,2,3,4,(1<<52)-1,(1<<52)-2}
    for b in range(53):
        for d in (-2,-1,0,1,2):
            q = (1<<b)+d
            if 0<=q<1<<52:
                numerators.add(q)
    numerators.update(rng.randrange(1<<52) for _ in range(5000))
    groups['subnormal_RNE_midpoint_neighbours'] = sorted({v
        for q in numerators for b in [midpoint_seed(2*q+1,-1075)]
        for v in range(b-3,b+4)})
    seeds = [midpoint_seed(1,-1075),midpoint_seed((1<<53)-1,-1075),
             midpoint_seed((1<<54)-1,970)]
    groups['zero_normal_overflow_dispatch_neighbours'] = sorted({v
        for b in seeds+[bits(-1024.),bits(1024.),bits(-746.),bits(710.)]
        for v in range(b-128,b+129)})
finally:
    oracle.lib.mpfr_clear(C.byref(seed))
groups['random_underflow_range'] = [bits(rng.uniform(-746.,-708.)) for _ in range(20000)]
groups['IEEE_classes'] = [0,1,(1<<52)-1,1<<52,1<<63,(1<<63)|1,
    bits(1.),bits(-1.),infinity,infinity|(1<<63),infinity|1,infinity|(1<<63)|1,
    decline,decline|(1<<63),infinity-1,(infinity-1)|(1<<63)]
groups = {n:list(dict.fromkeys(v)) for n,v in groups.items()}
results = []
digest = hashlib.sha256()
for name,values in groups.items():
    for x in values:
        expected = oracle.reference('exp',x)
        got = machine.call('_ZN12compact_math3expEd',x)[0]
        assert (nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected,(name,hex(x),hex(got),hex(expected))
        digest.update(struct.pack('<3Q',x,expected,got))
    results.append(dict(group=name,cases=len(values),wrong_rounding=0))
    print('PASS',name,len(values),flush=True)
report = dict(status='PASS_EXP_ENDPOINT_PUBLIC_DIRECTED_MPFR',cases=sum(r['cases'] for r in results),
              groups=results,wrong_rounding=0,mpfr=oracle.version,result_sha256=digest.hexdigest(),
              elf_sha256=sha(elf),producer_sha256=sha(__file__),maximum_observed_stack_bytes=SP-machine.stack_lowest,
              scope='Public production exp on MPFR log-of-exact-midpoint input neighbours, exact dispatch boundaries, random underflow values and IEEE classes. All ARM calls check ABI, SP and bounded writes. Finite corpus, not physical cycles or an exhaustive domain proof.',
              hardware_accessed=False,production_promoted=False,goal_complete=False)
(work/'endpoint-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS public exp:',report['cases'],'directed MPFR cases; no errors.',flush=True)
