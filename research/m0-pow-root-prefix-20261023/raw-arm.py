"""Check every raw fixed-root result against independent exact integer endpoints."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root = Path.cwd()
sys.path.insert(0, str(root / 'tests'))
from native_eabi_m0_arm_self_test import Machine

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
parser.add_argument('--samples', type=int, default=20000)
args = parser.parse_args()
m = Machine(args.elf, True, stack_bytes=16384, instruction_budget=200000000,
            bootrom=root / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
rng = random.Random(0x11264063)
cases = set()
tails = (0, 1, 2, (1 << 22)-1, 1 << 22, (1 << 23)-1, 1 << 23,
         (1 << 54)-1, 1 << 54, (1 << 54)+1, (1 << 55)-2, (1 << 55)-1)
for parity in (0, 1):
    for cell in range(256):
        for tail in tails:
            cases.add(((1 << 63) | (cell << 55) | tail, parity))
for _ in range(args.samples):
    cases.add((rng.randrange(1 << 63, 1 << 64), rng.randrange(2)))
digest = hashlib.sha256()
instructions = []
max_floor_distance = 0
for index, (a, parity) in enumerate(sorted(cases)):
    wrapped, _, count = m.call('pow_sqrt64_raw', a, parity, count=index % 31 == 0)
    center = wrapped + ((1 << 64) if wrapped < 1 << 63 else 0)
    target = a << (63 + parity)
    assert (center-3)**2 <= target <= (center+3)**2, (index, hex(a), parity, hex(center),
                (center-3)**2-target, (center+3)**2-target)
    exact_floor = __import__('math').isqrt(target)
    max_floor_distance = max(max_floor_distance, abs(center-exact_floor))
    digest.update(struct.pack('<QQI', a, wrapped, parity))
    if index % 31 == 0:
        instructions.append(count)
record = dict(status='PASS_RAW_FIXED_ROOT_EXACT_ENDPOINTS', cases=len(cases),
    radius=3, maximum_observed_distance_from_exact_floor=max_floor_distance,
    counted_cases=len(instructions), mean_instructions=sum(instructions)/len(instructions),
    minimum_instructions=min(instructions), maximum_instructions=max(instructions),
    result_sha256=digest.hexdigest(), elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Exact integer squares enclose the full64-bit input root; all512 coefficient cells include coordinate boundaries and low-bit extrema. Every ARM call checks ABI and bounded writes. Finite diagnostic test; no complete pow qualification or device timing.')
args.json.write_text(json.dumps(record, indent=2) + '\n')
print('PASS:', record)
