#!/usr/bin/env python3
"""Exercise the public large-pow route in a linked Pico H ELF."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from m0_mpfr_oracle import Oracle
from m0_pow_large_host_self_test import (BASE, END_Y, FIRST_Y, INF, MASK, ONE,
                                         OUTPUT_LIMIT, SIGN, geometry, near_midpoint)
from native_eabi_m0_arm_self_test import Machine, SP, nan
from unicorn import UC_HOOK_CODE

PUBLIC = '_ZN12compact_math3powEdd'


def through_large_path(x, y, cuts):
    base, magnitude = x&MASK, y&MASK
    if not FIRST_Y <= magnitude < INF or base >= INF:
        return False
    return base != BASE or magnitude >= cuts['overflow' if y&SIGN else 'band']


def corpus(cuts, closest):
    rng = random.Random(0x62de45f)
    first, last = cuts['band'], cuts['underflow']
    bases = {0, 1, 0xfffffffffffff, 0x10000000000000, ONE-3, ONE-2, BASE, ONE,
             ONE+1, ONE+2, INF-1, INF, INF+1, INF+(1<<51)}
    magnitudes = {FIRST_Y-1, FIRST_Y, FIRST_Y+1, END_Y-1, END_Y, END_Y+1, INF-1, INF, INF+1}
    for threshold in cuts.values():
        magnitudes.update(range(threshold-2,threshold+3))
    pairs = {(x|sx,y|sy) for x in bases for y in magnitudes
             for sx in (0,SIGN) for sy in (0,SIGN)}
    for midpoint in (0, 1, 2, 17, 255, 65535, closest, OUTPUT_LIMIT-1):
        y0 = near_midpoint(midpoint)
        pairs.update((BASE|sign,y) for sign in (0,SIGN) for y in range(y0-2,y0+4))
    pairs.update((BASE|(rng.getrandbits(1)*SIGN),rng.randrange(first,last)) for _ in range(1024))
    pairs.update((rng.getrandbits(64),rng.randrange(FIRST_Y,INF)|(rng.getrandbits(1)*SIGN))
                 for _ in range(1024))
    return sorted(pairs)


def machine(elf, bootrom):
    return Machine(elf, True, bootrom=bootrom, stack_bytes=16384,
                   instruction_budget=30_000_000)


def run_public(arm, oracle, cuts, closest):
    visits = Counter()
    refinements = []

    def entered(_uc, _address, _size, stage):
        visits[stage] += 1

    for fragment, stage in [('pow_large_subnormal_fast','fast'), ('mk61_m0_pow_large_subnormal','160'),
                            ('mk61_m0_cr_pow','core'), ('mk61_m0_pow_rescue','rescue'),
                            ('mk61_m0_pow_round_final','stream')]:
        addresses = {value&~1 for name,value in arm.elf.symbols.items() if fragment in name}
        address, = addresses
        arm.uc.hook_add(UC_HOOK_CODE,entered,stage,begin=address,end=address)
    arm.uc.ctl_flush_tb()
    pairs = corpus(cuts,closest)
    totals = Counter()
    covered = 0
    for x,y in pairs:
        visits.clear()
        expected = oracle.reference('pow',x,y)
        got = arm.call(PUBLIC,x,y)[0]
        same = (nan(got) and bool(got&(1<<51))) if nan(expected) else got==expected
        assert same, (hex(x),hex(y),hex(got),hex(expected),visits)
        if through_large_path(x,y,cuts):
            assert not any(visits[stage] for stage in ('core','rescue','stream')), (x,y,visits)
            covered += 1
        if visits['160']:
            assert through_large_path(x,y,cuts) and visits['fast']==visits['160']==1, (x,y,visits)
            refinements.append(dict(x=f'{x:016x}',y=f'{y:016x}',rounded=f'{got:016x}'))
        totals.update(visits)
    assert totals['fast'] > 1000 and refinements
    return dict(public_cases=len(pairs), covered_cases=covered, stage_counts=dict(totals),
                refinements=refinements)


def count_samples(control, candidate, oracle, cuts, refinement):
    first, last = cuts['band'], cuts['underflow']
    rows = [('large_far_base',BASE-1,FIRST_Y),
            ('large_other_direction',ONE+1,FIRST_Y),
            ('first_certified_subnormal',BASE,first),
            ('subnormal_interior',BASE,(first+last)//2),
            ('negative_base_even_exponent',BASE|SIGN,first),
            ('last_minimum_subnormal',BASE,last-1),
            ('first_zero',BASE,last),
            ('first_infinity',BASE,cuts['overflow']|SIGN),
            ('ordinary',0x3ff23456789abcde,0x3fda123456789abc),
            ('near_one_ordinary',BASE,0x3ff23456789abcde)]
    rows.append(('natural_160_bit_refinement',int(refinement['x'],16),int(refinement['y'],16)))
    result = {}
    for label,x,y in rows:
        want = oracle.reference('pow',x,y)
        counts = {}
        for kind,arm in [('control',control),('candidate',candidate)]:
            arm.stack_lowest = SP
            got,_,instructions = arm.call(PUBLIC,x,y,count=True)
            assert got==want,(label,kind,hex(got),hex(want))
            counts[kind] = dict(instructions=instructions,stack_bytes=SP-arm.stack_lowest)
        result[label] = dict(x=f'{x:016x}',y=f'{y:016x}',rounded=f'{want:016x}',**counts)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--bootrom', type=Path, required=True)
    parser.add_argument('--certificate', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    proof = json.loads(args.certificate.read_text())
    assert proof['status']=='PASS_LARGE_EXPONENT_BAND'
    cuts = geometry()
    oracle = Oracle()
    candidate = machine(args.elf,args.bootrom)
    control = machine(args.control,args.bootrom)
    report = run_public(candidate,oracle,cuts,int(proof['closest_lower_encoding'],16))
    samples = count_samples(control,candidate,oracle,cuts,report['refinements'][0])
    result = dict(status='PASS',mpfr=oracle.version,bootrom_sha256=candidate.bootrom_sha256,
                  elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                  control_elf_sha256=hashlib.sha256(args.control.read_bytes()).hexdigest(),
                  **report,samples=samples)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print(result['public_cases'],result['covered_cases'],result['stage_counts'],flush=True)
    for name,row in samples.items():
        print(name,row['control']['instructions'],row['candidate']['instructions'],flush=True)


if __name__ == '__main__':
    main()
