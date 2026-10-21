#!/usr/bin/env python3
"""Execute the asin root estimate against exact integer geometry and sqrt."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from native_eabi_m0_arm_self_test import Machine, SP, bits

R = 1 << 63


def quantize_x(x):
    step = 1 << max(0, x.bit_length() - 53)
    return x // step * step


def reference(x):
    n = R*R - x*x
    shift = (126 - n.bit_length()) & ~1
    normalized = n << shift
    reduction = normalized.bit_length() - 53
    top, tail = divmod(normalized, 1 << reduction)
    top += tail > (1 << (reduction-1)) or (tail == (1 << (reduction-1)) and top & 1)
    argument = top << reduction
    lower = math.isqrt(argument) >> 10
    midpoint = (lower << 10) + 512
    g = (lower + (argument > midpoint*midpoint or (argument == midpoint*midpoint and lower & 1))) << 10
    residual = abs(normalized - g*g)
    denominator = g >> 47
    correction = ((residual >> 48) + denominator//2) // denominator
    q = g + correction if g*g < normalized else g - correction
    scale = shift // 2
    y = ((q + (1 << (scale-1))) >> scale) if scale else q
    assert (q-1)**2 < normalized < (q+1)**2
    assert (y-1)**2 < n < (y+1)**2
    return q, scale, y, normalized, n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=50000)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    assert args.samples >= 0
    values = {1 << 57, R-1024}
    for head in range(1024, 65536):
        values.add(quantize_x(head << 47))
        values.add(quantize_x(((head+1) << 47)-1))
    for exponent in range(74, 127):
        center = math.isqrt(max(0, R*R - (1 << exponent)))
        for offset in range(-4, 5):
            x = quantize_x(center + offset*1024)
            if 1 << 57 <= x <= R-1024:
                values.add(x)
    rng = random.Random(0xA51E6900)
    for _ in range(args.samples):
        raw = rng.randrange(bits(1/64), bits(1.0))
        e = (raw >> 52) - 1023
        values.add(((raw & ((1 << 52)-1)) | (1 << 52)) << (e+11))
    machine = Machine(args.elf, True, stack_bytes=16384)
    pointer = SP - 8192
    digest = hashlib.sha256()
    for x in sorted(values):
        expected, scale, y, normalized, n = reference(x)
        machine.uc.mem_write(pointer, struct.pack('<I', 0xffffffff))
        got = machine.call('asin_root_estimate', x, pointer)[0]
        actual_scale = struct.unpack('<I', machine.uc.mem_read(pointer, 4))[0]
        assert (got, actual_scale) == (expected, scale), (hex(x), got, expected, actual_scale, scale)
        digest.update(struct.pack('<4Q', x, got, scale, y))
    state = struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)
    dirty = sorted(values)[::max(1, len(values)//64)][:64]
    for x in dirty:
        expected, scale, *_ = reference(x)
        machine.uc.mem_write(0xD0000060, state)
        got = machine.call('asin_root_estimate', x, pointer)[0]
        assert got == expected
        assert bytes(machine.uc.mem_read(0xD0000060, len(state))) == state
    report = dict(status='PASS', elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                  cases=len(values), actual_arm_calls=machine.calls, pending_divider_checks=len(dirty),
                  result_sha256=digest.hexdigest(), maximum_shift=26,
                  oracle='Exact arbitrary-precision N=2^126-X^2, binary64 input rounding, integer sqrt midpoint tests, quotient and interval comparisons.',
                  scope='Every top16bit X bucket at both legal endpoints, normalization boundaries and deterministic binary64 inputs. ABI, bounded stack writes and pending SIO preservation checked. General error enclosure is certified separately.')
    args.json.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS', len(values), 'root estimates;', machine.calls, 'actual ARM calls.')


if __name__ == '__main__':
    main()
