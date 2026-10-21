#!/usr/bin/env python3
"""Compare captured ROM V3 arithmetic and selected science cases with RNE."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from m0_bootrom import ROMMachine, ROM_SHA
from m0_mpfr_oracle import Oracle, bits
from native_eabi_m0_arm_self_test import nan, ordered


def normal(value):
    return 0 < (value >> 52) & 2047 < 2047


def eligible(name,a,b):
    if not normal(a) or (name != 'sqrt' and not normal(b)):
        return False
    ea,eb=(a>>52)&2047,(b>>52)&2047
    if name=='sqrt':
        return not a>>63
    if name in ('dadd','dsub'):
        return min(ea,eb)>=54 and max(ea,eb)<=2045
    if name=='dmul':
        return 1025<=ea+eb<=3067
    return -1020<=ea-eb<=1022


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args();assert args.samples>=0
    elf_sha=hashlib.sha256(args.elf.read_bytes()).hexdigest()
    m=ROMMachine(args.elf,args.rom,args.metadata);oracle=Oracle()
    edge=[0,1<<63,1,(1<<63)|1,0xfffffffffffff,0x10000000000000,
          0x10000000000001,bits(.5),bits(1.),bits(-1.),bits(2.),bits(3.),
          0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,
          0x7ff0000000000001,0x7ff8000000001234]
    rng=random.Random(0x524f4d33)
    pairs=[(a,b) for a in edge for b in edge]
    def draw():return (rng.getrandbits(1)<<63)|(rng.randrange(1,2047)<<52)|rng.getrandbits(52)
    pairs += [(draw(),draw()) for _ in range(args.samples)]
    # Reach cancellation, halfway rounding, narrow exponents and power seeds.
    for exponent in (1,2,52,53,54,55,1022,1023,1024,2045,2046):
        for fraction in (0,1,(1<<52)-1,rng.getrandbits(52)):
            a=(exponent<<52)|fraction
            for delta in (-1,0,1):
                b=max(1,a+delta)
                pairs.extend([(a,b),(a,b|(1<<63))])
    report={}
    for name in ('dadd','dsub','dmul','ddiv','sqrt'):
        values=[(a,0) for a in dict.fromkeys(edge+[draw()&0x7fffffffffffffff for _ in range(args.samples)])] if name=='sqrt' else pairs
        wrong=passed_eligible=wrong_eligible=0;examples=[];digest=hashlib.sha256()
        for a,b in values:
            expected=oracle.reference(name,a) if name=='sqrt' else oracle.reference(name,a,b)
            own=m.call('mk61_m0_sqrt' if name=='sqrt' else '__aeabi_'+name,a,b)[0]
            good_own=own==expected or (nan(own) and nan(expected) and own&(1<<51))
            assert good_own,(name,'owned RNE failure',hex(a),hex(b),hex(own),hex(expected))
            got=m.call('rom_'+name,a,b)[0]
            good=got==expected or (nan(got) and nan(expected) and got&(1<<51))
            use=eligible(name,a,b);passed_eligible+=use;wrong_eligible+=bool(use and not good)
            wrong+=not good
            if not good and len(examples)<8:
                examples.append(dict(a=f'{a:016X}',b=f'{b:016X}',expected=f'{expected:016X}',rom=f'{got:016X}',guard_eligible=use))
            digest.update(struct.pack('<4Q',a,b,expected,got))
        assert wrong_eligible==0,(name,wrong_eligible)
        report[name]=dict(cases=len(values),raw_rom_wrong_rounding=wrong,guard_eligible_cases=passed_eligible,
                          guard_eligible_wrong_rounding=wrong_eligible,examples=examples,result_sha256=digest.hexdigest())
        print(name,report[name]['cases'],'raw wrong',wrong,'eligible',passed_eligible,'wrong',wrong_eligible,flush=True)
    science=[]
    for name,inputs in [('ln',[bits(1-2.**-45),bits(2.),1,0,bits(-1.)]),
                        ('exp',[0xc06de95fb9e75672,bits(-745.),bits(1.)]),
                        ('sin',[bits(1.),bits(1024.),bits(1e20)]),
                        ('cos',[bits(1.),bits(1024.),bits(1e20)]),
                        ('tan',[bits(1.),bits(1024.),bits(1e20)])]:
        for a in inputs:
            expected=oracle.reference(name,a);got=m.call('rom_'+name,a)[0]
            good=got==expected or (nan(got) and nan(expected) and got&(1<<51))
            science.append(dict(operation=name,input=f'{a:016X}',expected=f'{expected:016X}',rom=f'{got:016X}',rne=bool(good),
                ulp_error=abs(ordered(got)-ordered(expected)) if not nan(got) and not nan(expected) else None))
    assert elf_sha==hashlib.sha256(args.elf.read_bytes()).hexdigest()
    result=dict(status='PASS_EVALUATION',rom_sha256=ROM_SHA,rom_version=3,rom_revision=f'{m.rom_revision:08X}',
        uid=m.rom_metadata['uid'],elf_sha256=elf_sha,mpfr=oracle.version,operations=report,science_examples=science,
        proposed_guards='Normal finite operands and conservative exponent bounds avoid subnormal operands/results and overflow; sqrt requires positive normal input.',
        scope='Actual captured ARM ROM bytes, not a recompiled approximation. Proposed guarded arithmetic domains pass this finite corpus; no all-input proof or physical timing claimed. Scientific ROM entry points fail RNE. Every call verifies saved registers, SP and bounded stack writes; memcpy/memset alone are functional models.')
    args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
