#!/usr/bin/env python3
"""Test the actual APP divider on a Cortex-M0+ with a functional SIO model."""
import argparse
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE

BASE = 0xD0000060
CSR = 0xD0000078
EDGES = [0, 1, 2, 3, 15, 31, 32, 255, 256, 1023, 0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff]
STATES = [None, struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3),
          struct.pack('<7I', 0xffffffef, 3, 0xffffffef, 3, 0xfffffffb, 0xfffffffe, 3)]

def expected(a, b):
    return (a // b, a % b) if b else (0xffffffff if a else 0, 0)

def state(machine, value):
    if value is None:
        machine.uc.mem_write(CSR, struct.pack('<I', 1))
    else:
        machine.uc.mem_write(BASE, value)

def one(machine, symbol, a, b):
    got = machine.call(symbol, a, b, width=32)[0]
    q, r = expected(a, b)
    assert got == q | (r << 32), (symbol, hex(a), hex(b), hex(got), hex(q), hex(r))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('elf', type=Path)
    parser.add_argument('--samples', type=int, default=10000)
    args = parser.parse_args()
    machine = Machine(args.elf, True)
    assert machine.elf.symbols['__aeabi_uidiv'] == machine.elf.symbols['__aeabi_uidivmod']
    address = machine.elf.symbols['__aeabi_uidiv'] & ~1
    code = bytes(machine.uc.mem_read(address, machine.elf.sizes['__aeabi_uidiv']))
    assert b'\xff\xe7' * 3 in code, 'Pico SDK divider latency sequence missing'
    rng = random.Random(0x2040)
    inputs = [(a, b) for a in EDGES for b in EDGES]
    inputs += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(args.samples)]
    for context in STATES:
        for a, b in inputs:
            state(machine, context)
            one(machine, '__aeabi_uidivmod', a, b)
            if context is not None:
                assert bytes(machine.uc.mem_read(BASE, len(context))) == context, ('context lost', a, b)

    # Inject an interrupt at every instruction in both the clean and dirty
    # paths. A separate machine runs the same helper on the interrupted SIO
    # state; its SIO state is then copied back before the outer call resumes.
    interrupt = Machine(args.elf, True)
    injected = 0
    for context in STATES[:2]:
        for outer_a, outer_b, irq_a, irq_b in [(0xfedcba98, 37, 0xabcdef12, 89),
                                                (0x76543210, 3, 0x87654321, 0)]:
            state(machine, context)
            _, _, instructions = machine.call('__aeabi_uidivmod', outer_a, outer_b, width=32, count=True)
            for at in range(instructions):
                state(machine, context)
                step = [0]
                def inject(uc, address, size, _):
                    nonlocal injected
                    del address, size
                    if step[0] == at:
                        before = bytes(uc.mem_read(BASE, 28))
                        interrupt.uc.mem_write(BASE, before)
                        one(interrupt, '__aeabi_uidivmod', irq_a, irq_b)
                        after = bytes(interrupt.uc.mem_read(BASE, 28))
                        if struct.unpack_from('<I', before, 24)[0] & 2:
                            assert after == before, ('interrupted dirty SIO state changed', at)
                        uc.mem_write(BASE, after)
                        injected += 1
                    step[0] += 1
                hook = machine.uc.hook_add(UC_HOOK_CODE, inject)
                machine.uc.ctl_flush_tb()
                try:
                    one(machine, '__aeabi_uidivmod', outer_a, outer_b)
                finally:
                    machine.uc.hook_del(hook)
                    machine.uc.ctl_flush_tb()
                if context is not None:
                    assert bytes(machine.uc.mem_read(BASE, len(context))) == context, ('outer context lost', at)
    print(f'PASS: {len(inputs) * len(STATES)} arithmetic/context cases, {injected} interrupt positions')

if __name__ == '__main__':
    main()
