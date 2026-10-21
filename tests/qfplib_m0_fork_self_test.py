#!/usr/bin/env python3
"""Measure a standalone Qfplib fork, preserving its documented limits."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle,bits,real
from native_eabi_m0_arm_self_test import Machine,SP,ordered,nan

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--samples',type=int,default=5000)
p.add_argument('--json',type=Path,required=True)
a=p.parse_args();assert a.samples>=0
images={k:Machine(a.build/(k+'.elf')) for k in ['original','modified']}
rng=random.Random(0x514650);oracle=Oracle();groups={};unchanged=0;digest=hashlib.sha256()

def check(name,symbol,pairs,reference,*,same=False,exact=False):
    global unchanged
    stats={k:dict(cases=0,wrong_rounding=0,worst_ulp=0) for k in images}
    examples=[]
    for x,y in pairs:
        expected=reference(x,y);outputs={}
        for label,m in images.items():
            got=m.call(symbol,x,y)[0];outputs[label]=got
            good=(nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected
            s=stats[label];s['cases']+=1;s['wrong_rounding']+=not good
            error=0 if good else abs(ordered(got)-ordered(expected)) if not nan(expected) and not nan(got) else None
            if error is not None:s['worst_ulp']=max(s['worst_ulp'],error)
            if label=='modified' and not good and len(examples)<6:examples.append(dict(x=hex(x),y=hex(y),got=hex(got),expected=hex(expected),ulp=error))
            if exact and label=='modified':assert good,(name,hex(x),hex(y),hex(got),hex(expected))
            digest.update(struct.pack('<4Q',x,y,got,expected))
        if same:assert outputs['original']==outputs['modified'],(name,hex(x),hex(y),outputs);unchanged+=1
    groups[name]=dict(symbol=symbol,statistics=stats,examples=examples)
    print(name,stats,flush=True)

normal=[(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(a.samples)]
near={bits(1.)+d for d in range(-512,513)}
for b in range(53):near.update([bits(1.)+(1<<b),bits(1.)-(1<<b)])
one=bits(1.)
def near_one(v):return one-65535<=v<=one+32767
lnvalues=[v for v in normal+sorted(near) if not near_one(v)]
check('ln_positive_normal_outside_new_kernel','qfp_dln',[(v,0) for v in lnvalues],lambda x,y:oracle.reference('ln',x),same=True)
check('ln_near_one_exhaustive','qfp_dln',[(v,0) for v in range(one-65535,one+32768)],lambda x,y:oracle.reference('ln',x),exact=True)
subnormal={1,2,3,(1<<52)-1}
for b in range(52):subnormal.update(v for v in [(1<<b)-1,1<<b,(1<<b)+1] if 0<v<1<<52)
subnormal.update(rng.randrange(1,1<<52) for _ in range(a.samples))
check('ln_positive_subnormal','qfp_dln',[(v,0) for v in sorted(subnormal)],lambda x,y:oracle.reference('ln',x))
special=[0,1<<63,0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff0000000000001,0x7ff8000000001234,0xfff8000000001234,bits(-1.),bits(-2.),(1<<63)|1,0xffefffffffffffff]
check('ln_special_numeric_semantics','qfp_dln',[(v,0) for v in special],lambda x,y:oracle.reference('ln',x),exact=True)
check('sqrt_normal','qfp_dsqrt',[(v,0) for v in normal],lambda x,y:oracle.reference('sqrt',x),same=True)
for name in ['sin','cos','tan']:
    values=[bits(rng.uniform(-1024,1024)) for _ in range(a.samples)]
    values += [bits(v) for v in [0.,-0.,1.,-1.,math.pi,math.pi/2,-math.pi/2]]
    check(name+'_documented_range','qfp_d'+name,[(v,0) for v in values],lambda x,y,n=name:oracle.reference(n,x),same=True)
values=[bits(rng.uniform(-750,710)) for _ in range(a.samples)]
check('exp_finite_range','qfp_dexp',[(v,0) for v in values],lambda x,y:oracle.reference('exp',x),same=True)
check('atan_composed','qfp_datan2',[(bits(rng.uniform(-1e6,1e6)),bits(1.)) for _ in range(a.samples)],lambda x,y:oracle.reference('atan',x),same=True)
# Ordinary IEEE arithmetic is exact RNE subject to Qfplib's stated NaN/denormal restrictions.
base=[0,1<<63,1,(1<<52)-1,1<<52,bits(1.),bits(-1.),0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000001]
pairs=[(x,y) for x in base for y in base]
pairs += [(normal[i],normal[(i+1)%len(normal)]^(rng.randrange(2)<<63)) for i in range(len(normal))] if normal else []
def binary(name,x,y):
    u,v=real(x),real(y)
    if name=='add':return bits(u+v)
    if name=='sub':return bits(u-v)
    if name=='mul':return bits(u*v)
    if math.isnan(u) or math.isnan(v) or u==v==0:return bits(float('nan'))
    if v==0:return bits(math.copysign(math.inf,u)*math.copysign(1.,v))
    return bits(u/v)
for name in ['add','sub','mul','div']:
    check(name+'_ieee_audit','qfp_d'+name,pairs,lambda x,y,n=name:binary(n,x,y),same=True)
    exact_pairs=[(x,y) for x,y in pairs if 0<(x>>52)&2047<2047 and 0<(y>>52)&2047<2047 and 0<(binary(name,x,y)>>52)&2047<2047]
    check(name+'_normal_inputs_and_results','qfp_d'+name,exact_pairs,lambda x,y,n=name:binary(n,x,y),exact=True)
counts=[]
for v in [bits(.5),bits(.75),bits(1.),bits(1.)+1,one-1,one-65535,one-65536,one+32767,one+32768,bits(1.5),bits(2.),bits(100.),0x0010000000000000,0x7fefffffffffffff]:
    row=dict(input=hex(v))
    for label,m in images.items():row[label]=m.call('qfp_dln',v,count=True)[2]
    assert row['modified']<row['original'],row
    counts.append(row)
sizes={k:m.elf.named_sections['.text'][5] for k,m in images.items()}
report=dict(status='PASS_RESEARCH_GATES',mpfr=oracle.version,groups=groups,
    normal_regression_cases_unchanged=unchanged,normal_ln_instruction_counts=counts,
    code_and_tables_bytes=sizes,added_bytes=sizes['modified']-sizes['original'],
    static_ram_bytes={k:sum(s[5] for s in m.elf.sections if s[2]&3==3) for k,m in images.items()},
    maximum_stack_bytes={k:SP-m.stack_lowest for k,m in images.items()},
    elf_sha256={k:hashlib.sha256((a.build/(k+'.elf')).read_bytes()).hexdigest() for k in images},
    build=json.loads((a.build/'build.json').read_text()),
    result_sha256=digest.hexdigest(),firmware_integrated=False,
    remaining=['Scientific functions outside the new tiny ln kernel are not universally correctly rounded; relative error can grow near zeros.','Positive subnormal ln now has a numerical result but retains occasional one-ULP errors.','NaN/subnormal behavior of other Qfplib entries is unchanged.','asin/acos/log10/pow/fma have no native Qfplib entries.','GPL-2.0-only/GPLv3 distribution compatibility is unresolved.'],
    scope='Separate Qfplib fork. MPFR-directed RNE audit, actual ARM outputs and ABI, unchanged ordinary outputs outside the exact near-one kernel, and lower instruction counts. This PASS does not mean every Qfplib result is correctly rounded or that the main goal is complete.')
a.json.parent.mkdir(parents=True,exist_ok=True)
a.json.write_text(json.dumps(report,indent=2)+'\n');print('PASS_RESEARCH_GATES',sizes,flush=True)
