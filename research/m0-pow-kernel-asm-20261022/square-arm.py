"""Check retained128-bit squares against exact rational centers and endpoints."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root = Path.cwd()
sys.path.insert(0, str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf', type=Path, required=True)
parser.add_argument('--baseline-elf', type=Path, required=True)
parser.add_argument('--bootrom', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
parser.add_argument('--samples', type=int, default=10000)
args = parser.parse_args()
rng = random.Random(0x1045128)
m = Machine(args.elf, True, stack_bytes=16384, instruction_budget=200000000, bootrom=args.bootrom)
before = Machine(args.baseline_elf, True, stack_bytes=16384, instruction_budget=200000000, bootrom=args.bootrom)
values = {1 << 127, (1 << 128)-1}
for bit in range(127):
    for tail in ((1 << bit)-1, 1 << bit, (1 << bit)+1):
        values.add((1 << 127) | tail)
values.update(rng.randrange(1 << 127, 1 << 128) for unused in range(args.samples))
pointer = SP-15000
mask = (1 << 64)-1
digest = hashlib.sha256()
zero_exact = 0
counted = []
for index, value in enumerate(sorted(values)):
    if index % 5 == 0:
        value &= ~mask
    error = 0 if index % 7 == 0 else rng.randrange(65536)
    exponent = rng.randrange(-1022, 1024)
    image = struct.pack('<QQiI', value >> 64, value & mask, exponent, error)
    m.uc.mem_write(pointer, image)
    m.call('pow_integer128_square', pointer, 0, 32)
    result = bytes(m.uc.mem_read(pointer, 24))
    high, low, out_exponent, out_error = struct.unpack('<QQiI', result)
    center = (high << 64) | low
    assert out_exponent in (2*exponent, 2*exponent+1)
    retained = F(center, 2) if out_exponent == 2*exponent else F(center)
    assert retained.denominator == 1
    omitted = F(value*value, 1 << 128)-retained
    assert 0 <= omitted < (7 if value & mask else 1), (index, value, omitted)
    scale = F(2)**(out_exponent-127)
    left, right = F(value-error)*F(2)**(exponent-127), F(value+error)*F(2)**(exponent-127)
    assert F(center-out_error)*scale <= left*left <= right*right <= F(center+out_error)*scale
    if not value & mask:
        before.uc.mem_write(pointer, image)
        before.call('pow_integer128_multiply', pointer, pointer, 32)
        assert result == bytes(before.uc.mem_read(pointer, 24))
        assert omitted == 0
        zero_exact += 1
    digest.update(image+result)
    if index % 61 == 0:
        row = {}
        for name, machine in (('V101', before), ('current', m)):
            machine.uc.mem_write(pointer, image)
            row[name] = machine.call('pow_integer128_square', pointer, 0, 32, count=True)[2]
        counted.append(row)
record = dict(status='PASS', cases=len(values), exact_rational_endpoint_checks=len(values),
              exact_rational_center_omission_checks=len(values),
              zero_low_bitwise_identical_to_parent_full_product=zero_exact,
              result_sha256=digest.hexdigest(), counted_samples=len(counted),
              mean_instructions={name: sum(row[name] for row in counted)/len(counted) for name in ('V101', 'current')},
              elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              baseline_elf_sha256=hashlib.sha256(args.baseline_elf.read_bytes()).hexdigest(),
              bootrom_sha256=m.bootrom_sha256, producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              scope='Actual ARM square centers lose strictly less than7 retained128-bit units and propagated enclosures contain exact rational endpoint squares. All-bit carry boundaries, maximal words, random full mantissas, zero low words and input radii through65535 are covered. Zero-low cases remain byte-identical to the parent full aliased product, including zero radius for exact sqrt-cube certification. Every call checks ABI and bounded writes. Finite coverage complements the algebraic bound; not universal pow totality or physical timings.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2)+'\n')
print('PASS:', len(values), 'exact rational squares;', zero_exact, 'exact zero-low results;', record['mean_instructions'])
