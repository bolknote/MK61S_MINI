#!/usr/bin/env python3
"""Check the linked fixed-work pow rescue for power-of-two bases."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random

from m0_mpfr_oracle import Oracle, bits, real
from native_eabi_m0_arm_self_test import Machine, SP
from unicorn import UC_HOOK_CODE

SIGN = 1 << 63
ONE = 0x3ff0000000000000
MASK = (1 << 64)-1
RESCUE = 'mk61_m0_pow_rescue'
DYADIC = 'm0_pow_dyadic12_GLOBAL__N_1L8evaluateEyy'


def symbol(arm, fragment):
    name, = (name for name in arm.elf.symbols if fragment in name)
    return name


def x_encoding(s):
    return 1 << (s+1074) if s < -1022 else (s+1023) << 52


def certified_domain(s, y):
    if (y & (SIGN-1)) < bits(2.**-37):
        return 'small_y'
    t = s*Fraction.from_float(real(y))
    if t >= 1024 or t <= -1075 or t.denominator == 1:
        return 'integer_or_saturation'
    tail = abs(t)-int(abs(t))
    if tail.numerator.bit_length() <= 53:
        return 'binary64_fraction'
    fraction = t - t//1
    if fraction >= Fraction(1,2) and fraction.denominator <= 1 << 64:
        return 'extended_fraction'
    return 'guarded_only'


def corpus():
    rng = random.Random(0xd2ad1c)
    cases = {(s, y) for s in range(-1074, 1024)
             for y in (bits(0.4618321734287223), bits(-0.7135236742412348))}
    fields = (-65,-64,-53,-40,-38,-37,-35,-20,-12,-11,-10,-2,-1,0,9,10,11,52,62)
    for s in (-1074,-1063,-1022,-993,-611,-53,-9,-2,-1,0,1,2,9,53,715,997,1023):
        for exponent in fields:
            for fraction in (0, 1, (1<<52)-1):
                y = ((exponent+1023)<<52) | fraction
                cases.update(((s, y), (s, y | SIGN)))
        if s:
            for boundary in (-1075, -1074, -1022, 1023, 1024):
                y = bits(boundary/s)
                cases.update((s, y+i) for i in range(-2,3))
    for start, stop in ((-64,-37), (-37,-16), (-16,3), (3,11)):
        for _ in range(384):
            s = rng.randrange(-1074,1024)
            y = (rng.getrandbits(1)<<63) | ((1023+rng.randrange(start,stop))<<52) | rng.getrandbits(52)
            cases.add((s,y))
    hard = bits(float.fromhex('0x1.e4596526bf94dp-10'))
    cases.update((1, hard+i) for i in range(-2,3))
    return sorted(cases)


def checks(arm, oracle):
    check = symbol(arm,DYADIC)
    counts, misses = Counter(), Counter()
    for s,y in corpus():
        x = x_encoding(s)
        domain = certified_domain(s,y)
        expected = oracle.reference('pow',x,y)
        got = arm.call(check,x,y)[0]
        counts[domain] += 1
        if got == MASK:
            assert domain == 'guarded_only', (s,hex(y),domain,hex(expected))
            misses[domain] += 1
        else:
            assert got == expected, (s,hex(y),domain,hex(got),hex(expected))
    assert all(counts[key] for key in ('small_y','integer_or_saturation','binary64_fraction',
                                      'extended_fraction','guarded_only'))
    for x in (0,3,ONE-1,ONE+1,0x7ff0000000000000,0x7ff8000000000000):
        assert arm.call(check,x,bits(.125))[0] == MASK
    return dict(direct_cases=sum(counts.values()), domains=dict(counts), undecided=dict(misses))


def route_and_counters(arm, control, oracle):
    entries = Counter()

    def entered(_uc, _pc, _size, name):
        entries[name] += 1

    for key, fragment in (('dyadic',DYADIC),('products','PowerBoundsILj10EE8multiplyE'),
                          ('512','m0_pow_interval5FixedILj512EE8evaluateEyyRy'),
                          ('stream','mk61_m0_pow_round_final')):
        address = arm.elf.symbols[symbol(arm,fragment)] & ~1
        arm.uc.hook_add(UC_HOOK_CODE,entered,key,begin=address,end=address)
    arm.uc.ctl_flush_tb()
    rows = (
        ('all_ones_fraction', 1, 0x3bffffffffffffff),
        ('small_negative_argument', 1, 0xbbffffffffffffff),
        ('small_x_wide_product', -1074, 0xbbffffffffffffff),
        ('at_zero_midpoint', 1, bits(-1075.)),
        ('below_overflow', 1023, bits(1024./1023)-1),
        ('published_boundary', 1, bits(float.fromhex('0x1.e4596526bf94dp-10'))),
        ('extended_grid', -1074, bits(-0.0008123445678273146)),
    )
    report = {}
    for name,s,y in rows:
        x = x_encoding(s)
        expected = oracle.reference('pow',x,y)
        counts = {}
        for label,machine in (('control',control),('candidate',arm)):
            entries.clear()
            machine.stack_lowest = SP
            got,_,instructions = machine.call(RESCUE,x,y,c=ONE,count=True)
            assert got == expected, (name,label,hex(got),hex(expected))
            counts[label] = dict(instructions=instructions,stack_bytes=SP-machine.stack_lowest)
        assert entries['dyadic']==1 and not entries['512'] and not entries['stream'] and entries['products']<=64
        report[name] = dict(x=f'{x:016x}',y=f'{y:016x}',rounded=f'{got:016x}',
                            products=entries['products'],**counts)

    # Exercise the negative-result sign supplied by CORE-MATH and the
    # existing fallback on a non-power of two through the same entry.
    for x,y,sign in ((bits(-2.),bits(-1075.),SIGN|ONE), (ONE-1,bits(.125),ONE)):
        entries.clear()
        assert arm.call(RESCUE,x,y,c=sign)[0] == oracle.reference('pow',x,y)
        assert entries['dyadic']==1 and entries['512']==int(x == ONE-1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('elf','control','bootrom','json'):
        parser.add_argument('--'+arg,type=Path,required=True)
    args = parser.parse_args()
    arm = Machine(args.elf,True,bootrom=args.bootrom,stack_bytes=16384,instruction_budget=35_000_000)
    control = Machine(args.control,True,bootrom=args.bootrom,stack_bytes=16384,instruction_budget=35_000_000)
    oracle = Oracle()
    report = dict(status='PASS',mpfr=oracle.version,bootrom_sha256=arm.bootrom_sha256,
                  elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                  control_elf_sha256=hashlib.sha256(args.control.read_bytes()).hexdigest(),
                  **checks(arm,oracle),counter_samples=route_and_counters(arm,control,oracle))
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(report['direct_cases'], report['domains'], report['undecided'])
    for name,row in report['counter_samples'].items():
        print(name,row['control']['instructions'],row['candidate']['instructions'],row['products'])


if __name__ == '__main__':
    main()
