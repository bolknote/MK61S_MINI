#!/usr/bin/env python3
"""Qualify the certified small-exponent power-of-two domain in linked ARM code."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from m0_mpfr_oracle import Oracle, bits
from native_eabi_m0_arm_self_test import Machine, SP
from unicorn import UC_HOOK_CODE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--bootrom', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    machine = Machine(args.elf, True, bootrom=args.bootrom, stack_bytes=4096,
                      instruction_budget=2_000_000)
    oracle = Oracle()
    entries = Counter()

    def entered(_uc, _pc, _size, name):
        entries[name] += 1

    for name, fragment in (
            ('512', 'm0_pow_interval5FixedILj512EE8evaluateEyyRy'),
            ('1024', 'm0_pow_interval5FixedILj1024EE8evaluateEyyRy'),
            ('products', 'm0_pow_interval5FixedILj512EE7productE'),
            ('divisions', 'm0_pow_interval5FixedILj512EE6divideE'),
            ('exact', 'mk61_m0_pow_exact_small'),
            ('4096', 'PowerBoundsILj256EE4sideE'),
            ('8192', 'PowerBoundsILj512EE4sideE')):
        matches = [address & ~1 for symbol, address in machine.elf.symbols.items()
                   if fragment in symbol and address]
        address, = matches
        machine.uc.hook_add(UC_HOOK_CODE, entered, name, begin=address, end=address)

    rows = []
    for exponent in (-1074, -738, -1, 0, 1, 738, 1023):
        x = bits(math.ldexp(1., exponent))
        for shift in (100, 116):
            for sign in (-1, 1):
                y = bits(math.ldexp(float(sign*((1 << 53)-1)), -shift))
                expected = oracle.reference('pow', x, y)
                entries.clear()
                machine.stack_lowest = SP
                got, _, instructions = machine.call('mk61_m0_pow_rescue', x, y,
                                                    c=bits(1.), count=True)
                stages = {key: value for key, value in entries.items()
                          if key not in ('products', 'divisions')}
                assert got == expected and stages == {'512': 1}, (
                    hex(x), hex(y), hex(got), hex(expected), dict(entries))
                assert entries['products'] <= 60 and entries['divisions'] <= 58
                row = dict(base_exponent=exponent, denominator_shift=shift,
                           negative=sign < 0, rounded=f'{got:016x}',
                           instructions=instructions,
                           stack_bytes=SP-machine.stack_lowest,
                           full_products=entries['products'],
                           limb_divisions=36*entries['divisions'])
                rows.append(row)
                print('PASS', len(rows), row, flush=True)

    report = dict(
        status='PASS', mpfr=oracle.version, cases=len(rows), rows=rows,
        elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        bootrom_sha256=machine.bootrom_sha256,
        maximum_instructions=max(row['instructions'] for row in rows),
        maximum_stack_bytes=max(row['stack_bytes'] for row in rows),
        maximum_full_products=max(row['full_products'] for row in rows),
        maximum_limb_divisions=max(row['limb_divisions'] for row in rows),
        scope='Forced production rescue calls with real linked memory and BootROM. '
              'All selected cases finish in the actual 512-bit interval and respect '
              'the separately certified arithmetic loop bounds. Saved registers, SP, '
              'bounded writes and the RP2040 divider model remain checked. Observed '
              'instruction and stack maxima are finite test results, not uniform timing bounds.')
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
