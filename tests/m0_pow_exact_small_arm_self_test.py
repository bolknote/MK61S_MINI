#!/usr/bin/env python3
"""Exercise the exact integer pow stage directly in the linked ARM image."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

from m0_mpfr_oracle import Oracle
from native_eabi_m0_arm_self_test import Machine, SP, bits
from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_CODE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=12)
    parser.add_argument('--checked-hints', action='store_true',
                        help='Require near hints to finish with at most two exact comparisons')
    args = parser.parse_args()
    assert args.samples >= 0
    sha = hashlib.sha256(args.elf.read_bytes()).hexdigest()
    machine = Machine(args.elf, True, stack_bytes=16384, instruction_budget=200000000)
    oracle = Oracle()
    pairs = [(1, bits(.5)), (1, bits(-.5)), (bits(2.), bits(32.)),
             (bits(9.), bits(.5)), (bits(81.), bits(.75)),
             (0x3FEFFFFFFFFFFFFF, bits(-31. / 32)),
             (0x3FF0000000000001, bits(31. / 32)),
             (0x3FF0000000000001, bits(-31. / 32)),
             (0x0010000000000000, bits(2.)),
             (0x7FEFFFFFFFFFFFFF, bits(32.)),
             (bits(2.), bits(-32.)), (bits(1.), bits(-1. / 32))]
    rng = random.Random(0xE7AC70)
    for _ in range(args.samples):
        pairs.append((rng.randrange(1, 0x7FF0000000000000),
                      bits(rng.choice((-1, 1)) * rng.randrange(1, 33) / 2.**rng.randrange(6))))
    pointer = SP - 15000
    lowest = [SP]
    def stack_write(uc, access, address, size, value, user):
        del uc, access, value, user
        if pointer <= address and address + size <= pointer + 8:
            return  # Caller-owned output is separate from the callee frame.
        if SP - machine.stack_bytes <= address < SP:
            lowest[0] = min(lowest[0], address)
    machine.uc.hook_add(UC_HOOK_MEM_WRITE, stack_write)
    comparisons = [0]
    relation_addresses = {value & ~1 for name, value in machine.elf.symbols.items()
                          if 'm0_pow_exact' in name and 'relation' in name}
    assert relation_addresses
    def compared(*unused):comparisons[0] += 1
    for address in relation_addresses:
        machine.uc.hook_add(UC_HOOK_CODE, compared, begin=address, end=address)
    digest = hashlib.sha256()
    for index, (x, y) in enumerate(pairs):
        machine.uc.mem_write(pointer, struct.pack('<Q', 0xBAD0BAD0BAD0BAD0))
        accepted = machine.call('mk61_m0_pow_exact_small', x, y, c=pointer)[0] & 255
        got = struct.unpack('<Q', machine.uc.mem_read(pointer, 8))[0]
        wanted = oracle.reference('pow', x, y)
        assert accepted and got == wanted, (index, hex(x), hex(y), accepted, hex(got), hex(wanted))
        digest.update(struct.pack('<4Q', x, y, got, wanted))
        print('PASS', index + 1, '/', len(pairs), flush=True)
    hinted_calls = 0
    maximum_hint_comparisons = 0
    if args.checked_hints:
        infinity = 0x7FF0000000000000
        for x, y in pairs:
            wanted = oracle.reference('pow', x, y)
            for hint in {min(wanted, infinity - 1), max(0, wanted - 1)}:
                machine.uc.mem_write(pointer, struct.pack('<Q', hint))
                before = comparisons[0]
                assert machine.call('mk61_m0_pow_exact_small', x, y, c=pointer)[0] & 255
                got = struct.unpack('<Q', machine.uc.mem_read(pointer, 8))[0]
                used = comparisons[0] - before
                assert got == wanted and 1 <= used <= 2, (hex(x), hex(y), hex(hint), used, hex(got), hex(wanted))
                maximum_hint_comparisons = max(maximum_hint_comparisons, used)
                hinted_calls += 1
                digest.update(struct.pack('<5Q', x, y, hint, got, wanted))
    pending = struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)
    for x, y in pairs[:4]:
        machine.uc.mem_write(0xD0000060, pending)
        assert machine.call('mk61_m0_pow_exact_small', x, y, c=pointer)[0] & 255
        assert bytes(machine.uc.mem_read(0xD0000060, len(pending))) == pending
    for y in [0., 33., 1. / 64, float('inf')]:
        machine.uc.mem_write(pointer, struct.pack('<Q', 0xBAD0BAD0BAD0BAD0))
        assert not machine.call('mk61_m0_pow_exact_small', bits(1.25), bits(y), c=pointer)[0] & 255
        assert struct.unpack('<Q', machine.uc.mem_read(pointer, 8))[0] == 0xBAD0BAD0BAD0BAD0
    assert sha == hashlib.sha256(args.elf.read_bytes()).hexdigest()
    report = dict(status='PASS', elf_sha256=sha, cases=len(pairs), actual_arm_calls=machine.calls,
                  wrong_rounding=0, dirty_sio_checks=4, unsupported_checks=4,
                  maximum_stack_bytes=SP-lowest[0],
                  maximum_bounded_write_depth=SP-machine.stack_lowest, result_sha256=digest.hexdigest(),
                  checked_hint_calls=hinted_calls,maximum_hint_comparisons=maximum_hint_comparisons,
                  mpfr=oracle.version,
                  scope='Direct exact-stage ARM calls including all saved registers, SP, stack writes, signed exponents, subnormal/overflow output and a pending SIO divider. Finite implementation qualification; domain argument is separate.')
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
