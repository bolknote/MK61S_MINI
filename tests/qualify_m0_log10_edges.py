#!/usr/bin/env python3
"""Check log10 segment edges, cancellation and exact powers against MPFR."""
import argparse
import hashlib
import json
from pathlib import Path
import random

from m0_mpfr_oracle import Oracle, bits
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE


def corpus():
    values = set()
    for exponent in (1, 64, 1000, 1022, 1023, 1024, 1900, 2046):
        for j in range(2049):
            center = (exponent << 52)+(j << 41)
            values.update(center+offset for offset in (-1, 0, 1)
                          if 0 < center+offset < 0x7FF0000000000000)
    one = bits(1.)
    for k in range(49):
        for sign in (-1, 1):
            center = one+sign*(1 << k)
            values.update(range(center-8, center+9))
    for j in range(-128, 129):
        center = bits(1+j/8192)
        values.update((center-1,center,center+1))
    for exponent in range(-300, 301):
        center = bits(10. ** exponent)
        values.update((center-1,center,center+1))
    rng = random.Random(0x1062E094)
    for _ in range(10000):
        values.add(one+rng.randrange(-(1 << 46), (1 << 46)))
    return sorted(values)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--require-refinement', action='store_true', help='For a private build with both fast rounding exits disabled.')
    p.add_argument('--json', type=Path, required=True)
    args = p.parse_args()
    machine = Machine(args.elf, True)
    oracle = Oracle()
    refine = [0]
    if args.require_refinement:
        names = [name for name in machine.elf.symbols
                 if name == 'log10_refine' or 'log10_refineEd' in name]
        assert len(names) == 1, names
        address = machine.elf.symbols[names[0]] & ~1
        def entered(*unused):
            refine[0] += 1
        machine.uc.hook_add(UC_HOOK_CODE, entered, begin=address, end=address)
    digest = hashlib.sha256()
    cases = corpus()
    required = 0
    for index, a in enumerate(cases):
        before = refine[0]
        expected = oracle.reference('log10', a)
        got = machine.call('_ZN12compact_math5log10Ed', a)[0]
        assert got == expected, (hex(a), hex(got), hex(expected))
        if args.require_refinement and 0x0010000000000000 <= a < 0x7FF0000000000000 and a != bits(1.):
            assert refine[0] > before, ('Refinement was not forced', hex(a))
            required += 1
        digest.update(a.to_bytes(8,'little')+expected.to_bytes(8,'little'))
        if (index+1) % 10000 == 0:
            print('PASS', index+1, 'log10 edge cases', flush=True)
    result = dict(status='PASS',cases=len(cases),wrong_rounding=0,
                  forced_refinement=args.require_refinement,required_refinement_calls=required,
                  observed_refinement_calls=refine[0],sha256=digest.hexdigest(),
                  elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                  scope='Normal/subnormal inputs at Q70/Q94 segment edges, cancellation around1 and neighbors of powers of ten. Directed MPFR oracle; ARM ABI and 4KiB stack checks.')
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',len(cases),'log10 edge cases',flush=True)


if __name__ == '__main__':
    main()
