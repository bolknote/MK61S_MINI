"""Check the trusted cell contract, preserved pointers and actual hot callers."""
from fractions import Fraction
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

root = Path.cwd()
sys.path.insert(0, str(root / 'tests'))
from native_eabi_m0_arm_self_test import Machine, SP, bits
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--elf', type=Path, required=True)
parser.add_argument('--bootrom', type=Path, required=True)
parser.add_argument('--json', type=Path, required=True)
args = parser.parse_args()
elf, bootrom = args.elf, args.bootrom
m = Machine(elf, True, stack_bytes=16384, instruction_budget=200000000, bootrom=bootrom)
oracle = Oracle()
rng = random.Random(0x101CE11)
cases = {(bits(x), bits(x)) for x in (.5, 1., 1.5, 2.)}
for _ in range(2400):
    x = (rng.randrange(1018, 1029) << 52) | rng.getrandbits(52)
    y = bits(float(Fraction(rng.randrange(1, 33), 1 << rng.randrange(8))))
    if rng.randrange(5) == 0:
        y = (rng.randrange(1020, 1027) << 52) | rng.getrandbits(52)
    if rng.getrandbits(1):
        y |= 1 << 63
    cases.add((x, y))
for exponent in (1, 2, 511, 1022, 1023, 1024, 1534, 2045, 2046):
    for fraction in (0, 1, (1 << 52)-2, (1 << 52)-1):
        for y in (.5, -.5, .75, -.75, 1.5, -1.5, 2.5, -2.5):
            cases.add(((exponent << 52) | fraction, bits(y)))
hard = json.loads((root / 'research/m0-pow-checked-20261022/hard-pow-inputs.json').read_text())
for group in hard['groups']:
    cases.update((int(c['a'], 16), int(c['b'], 16)) for c in group['cases'])
px, py = SP-15000, SP-14904
canary = bytes.fromhex('C4A1937D') * 4
current = None
witnesses = []
def observe(uc, address, size, unused):
    a, b = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
    x, y = struct.unpack('<Q', bytes(uc.mem_read(a, 8)))[0], struct.unpack('<Q', bytes(uc.mem_read(b, 8)))[0]
    cell = uc.reg_read(UC_ARM_REG_R2) | (uc.reg_read(UC_ARM_REG_R3) << 32)
    assert current is not None and (x, y) == current[:2]
    expected = current[2]
    if cell & ((1 << 52)-1):
        assert expected in (cell, cell+1), (hex(x), hex(y), hex(cell), hex(expected))
    witnesses.append(dict(a=f'{x:016X}', b=f'{y:016X}', cell=f'{cell:016X}', expected=f'{expected:016X}',
                          binade_start=not bool(cell & ((1 << 52)-1))))

direct = aliases = public = 0
digest = hashlib.sha256()
# Direct calls use guaranteed neighboring RNE cells. Binade-start calls also
# use intentionally distant cells; that route must retain its old checks.
for index, (x, y) in enumerate(sorted(cases)):
    expected = oracle.reference('pow', x, y)
    a, b = struct.pack('<Q', x)+canary, struct.pack('<Q', y)+canary
    m.uc.mem_write(px, a)
    m.uc.mem_write(py, b)
    actual_py = px if x == y else py
    cells = {0x3FF0000000000000}
    if 0x0010000000000001 < expected < 0x7FEFFFFFFFFFFFFE:
        cells |= {expected-1, expected}
    for cell in sorted(cells):
        got = m.call('pow_first_cell', px | (actual_py << 32), cell)[0]
        assert got == expected, (hex(x), hex(y), hex(cell), hex(got), hex(expected))
        assert bytes(m.uc.mem_read(px, len(a))) == a
        assert bytes(m.uc.mem_read(py, len(b))) == b
        digest.update(struct.pack('<4Q', x, y, cell, got))
        direct += 1
        aliases += x == y
    current = (x, y, expected)
    hook = m.uc.hook_add(UC_HOOK_CODE, observe, begin=m.elf.symbols['pow_first_cell'] & ~1,
                         end=m.elf.symbols['pow_first_cell'] & ~1)
    m.uc.ctl_flush_tb()
    try:
        got = m.call('_ZN12compact_math3powEdd', x, y)[0]
    finally:
        m.uc.hook_del(hook)
    assert got == expected, (hex(x), hex(y), 'public', hex(got), hex(expected))
    public += 1
assert direct > 7000 and aliases > 0 and public > 2500 and len(witnesses) > 100
record = dict(status='PASS', input_pairs=len(cases), direct_valid_cell_calls=direct,
              aliased_parameter_calls=aliases, public_mpfr_calls=public,
              actual_hot_first_cell_entries=len(witnesses), hot_entry_witnesses=witnesses,
              parameter_bytes_and_canaries_preserved=True, wrong_rounding=0,
              result_sha256=digest.hexdigest(), elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
              bootrom_sha256=m.bootrom_sha256, producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              scope='Actual ARM trusted pointer+cell entry with valid adjacent cells, distant binade-start cells and aliasing; every result matches directed MPFR. Hooks at the real public-path callee verify the first-tier two-cell guarantee. Arbitrary untrusted hints are checked separately through the preserved old API. Finite tests do not prove totality or device timings.')
args.json.parent.mkdir(parents=True, exist_ok=True)
args.json.write_text(json.dumps(record, indent=2) + '\n')
print('PASS:', direct, 'direct calls;', public, 'public MPFR;', len(witnesses), 'actual hot entry witnesses')
