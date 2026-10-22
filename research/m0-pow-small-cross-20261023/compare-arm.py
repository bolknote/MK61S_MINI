"""Compare the reference-based ARM interval decision with exact integer bounds."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tests'))
from native_eabi_m0_arm_self_test import Machine, SP

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf', type=Path, required=True)
parser.add_argument('--bootrom', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
parser.add_argument('--samples', type=int, default=20000)
args = parser.parse_args()
m = Machine(args.elf, True, stack_bytes=16384, instruction_budget=200000000, bootrom=args.bootrom)
rng = random.Random(0x10796128)
mask = (1 << 64)-1
top = 1 << 127
limit = 1 << 128
cases = []
for distance in range(-3, 4):
    for a in (top, top+1, top+(1 << 32)-1, top+(1 << 64)-1, limit-2, limit-1):
        for b in (top, top+1, limit-2, limit-1):
            for error in (0, 1, 2, 65535, 131071, 262143, 1048575):
                cases.append((a, distance, error, b, 0, error, False))
for unused in range(args.samples):
    a = rng.randrange(top, limit)
    ea, eb = rng.randrange(1 << 20), rng.randrange(1 << 20)
    distance = rng.randrange(-3, 4)
    mode = rng.randrange(5)
    if mode == 0:
        b = rng.randrange(top, limit)
    elif mode == 1:
        b = a+rng.choice((-1, 1))*rng.choice((ea+eb, ea+eb+1, max(0, ea+eb-1), 1 << 32, 1 << 64))
        distance = 0
    elif mode == 2:
        a = top | (rng.getrandbits(64) << 32) | rng.choice((0, 1, (1 << 32)-1))
        b = a+rng.randrange(-2097152, 2097153)
        distance = 0
    elif mode == 3:
        a = top+rng.randrange(2097152)
        b = limit-1-rng.randrange(2097152)
        distance = 1
    else:
        b = a
        distance = 0
    if not top <= b < limit:
        b = top
    alias = mode == 4
    if alias:
        eb = ea
    cases.append((a, distance, ea, b, 0, eb, alias))

decided = aliased = narrow = 0
digest = hashlib.sha256()
for index, (a, ae, ar, b, be, br, alias) in enumerate(cases):
    difference = ae-be
    if difference >= 2:
        expected = 1
    elif difference <= -2:
        expected = -1
    else:
        left, right, left_error, right_error = a, b, ar, br
        if difference < 0:
            left >>= 1
            left_error = left_error//2+1
        elif difference > 0:
            right >>= 1
            right_error = right_error//2+1
        gap = left-right
        expected = (1 if gap > 0 else -1) if abs(gap) > left_error+right_error else 0
        narrow += (left >> 32) == (right >> 32)
    block = bytearray(b'\xA5'*128)
    struct.pack_into('<QQiI', block, 8, a >> 64, a & mask, ae, ar)
    struct.pack_into('<QQiI', block, 72, b >> 64, b & mask, be, br)
    pointer = SP-15000
    m.uc.mem_write(pointer, bytes(block))
    got = m.call('pow_dyadic128_compare', pointer+8, pointer+8 if alias else pointer+72, 32)[0] & 0xFFFFFFFF
    got = got-(1 << 32) if got >> 31 else got
    assert got == expected, (index, got, expected, a, ae, ar, b, be, br)
    assert bytes(m.uc.mem_read(pointer, len(block))) == block, ('Input/canary mutation', index)
    if got:
        # Independent exact unaligned endpoint ordering: every accepted sign
        # must separate the original complete input intervals.
        left = (a-ar) << max(0, difference)
        right = (b+br) << max(0, -difference)
        other_left = (a+ar) << max(0, difference)
        other_right = (b-br) << max(0, -difference)
        assert left > right if got > 0 else other_left < other_right
        decided += 1
    aliased += alias
    digest.update(block+struct.pack('<i', got))
record = dict(status='PASS', cases=len(cases), certified_signs=decided,
              alias_calls=aliased, identical_high96_cases=narrow,
              exact_decision_model_matches=len(cases), input_and_canary_bytes_preserved=True,
              maximum_input_radius=(1 << 20)-1, result_sha256=digest.hexdigest(),
              elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              bootrom_sha256=m.bootrom_sha256, producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              scope='Actual ARM reference ABI, both signed alignment directions, exponent gaps through three, high/low carry boundaries, equal high96 fast paths and overlapping inputs. Exact integer enclosure decisions match the original mathematical alignment rule; accepted signs also strictly separate independent original endpoints. Finite coverage complements source/algebraic equivalence; no universal pow totality or physical speed claim.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2)+'\n')
print('PASS:', len(cases), 'exact interval decisions;', decided, 'certified signs;', aliased, 'aliases')
