"""Explore independent binary64 domains beyond the curated performance matrix."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
sys.path.insert(0, str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine, SP, bits, nan
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle

candidate = root/'.build/m0-exp-endpoints-v145-20261023/firmware/mk61s-picocalc-pico-h.elf'
reference = root/'.build/m0-v138-execution-20261023/reference/reference.elf'
bootrom = root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
config = json.loads((root/'.build/m0-v138-execution-20261023/benchmark.json').read_text())
operations = {c['operation']: c for c in config['chunks']}
own = Machine(candidate, True, stack_bytes=16384, instruction_budget=200000000, bootrom=bootrom)
qfp_image = ElfImage(reference)
qfp_image.load(own.uc)
reference_entries = {c['qfplib_symbol'] for c in config['chunks']}
exports = {n: a for n, a in qfp_image.symbols.items() if n in reference_entries or n.startswith('qfp_')}
assert all(n not in own.elf.symbols or own.elf.symbols[n] == a for n, a in exports.items())
# Keep local labels such as dd_2 from the owned ELF: the SIO guard uses them.
own.elf.symbols.update(exports)
oracle = Oracle()
rng = random.Random(0xD0A142)
sign = 1 << 63
inf = 0x7FF0000000000000
groups = []
samples = 128


def group(op, name, pairs):
    groups.append((op, name, list(dict.fromkeys(pairs))))


for op in ('sin', 'cos', 'tan'):
    group(op, 'independent_moderate', [(bits(rng.uniform(-100, 100)), 0) for _ in range(samples)])
    group(op, 'tiny_exponent_range', [(bits(math.ldexp(rng.uniform(.5, 1), -rng.randrange(1, 1074))) | (sign if rng.getrandbits(1) else 0), 0) for _ in range(samples)])
    for lo, hi in ((20, 60), (60, 500), (500, 1023)):
        group(op, f'argument_exponents_{lo}_{hi}', [(bits(math.ldexp(rng.uniform(.5, 1), rng.randrange(lo, hi))) | (sign if rng.getrandbits(1) else 0), 0) for _ in range(samples)])
    seeds = [bits(j*math.pi/2) for j in range(1, 33)]
    group(op, 'quadrant_seed_neighbours', [(x+d, 0) for x in seeds for d in (-1, 0, 1, 2)])
for op in ('ln', 'log10', 'sqrt'):
    group(op, 'positive_normal_full_exponents', [(rng.randrange(1, 2047) << 52 | rng.getrandbits(52), 0) for _ in range(samples)])
    group(op, 'subnormal_mantissas', [(rng.randrange(1, 1 << 52), 0) for _ in range(samples)])
    group(op, 'near_one_ulp_offsets', [(bits(1.)+d, 0) for d in range(-64, 65) if d])
for op in ('asin', 'acos', 'atan'):
    group(op, 'independent_unit_range', [(bits(rng.uniform(-1, 1)), 0) for _ in range(samples)])
    group(op, 'tiny_normal_inputs', [(bits(math.ldexp(rng.uniform(.5, 1), -rng.randrange(30, 1022))) | (sign if rng.getrandbits(1) else 0), 0) for _ in range(samples)])
    group(op, 'near_positive_one', [(bits(1.)-i, 0) for i in range(1, 129)])
group('atan', 'large_normal_magnitudes', [(rng.randrange(1080, 2047) << 52 | rng.getrandbits(52) | (sign if rng.getrandbits(1) else 0), 0) for _ in range(samples)])
for name, lo, hi in [('negative_extreme', -746., -700.), ('unit', -1., 1.),
                     ('moderate', -100., 100.), ('positive_extreme', 700., 710.)]:
    group('exp', name, [(bits(rng.uniform(lo, hi)), 0) for _ in range(samples)])
group('exp', 'tiny_signed_normal', [(bits(math.ldexp(rng.uniform(.5, 1), -rng.randrange(30, 1022))) | (sign if rng.getrandbits(1) else 0), 0) for _ in range(samples)])
group('pow', 'independent_full_fractional', [(bits(rng.uniform(.01, 10)), bits(rng.uniform(-16, 16))) for _ in range(samples)])
group('pow', 'wide_base_fractional_exponent', [(rng.randrange(1, 2047) << 52 | rng.getrandbits(52), bits(rng.uniform(-8, 8))) for _ in range(samples)])
for e in (-64, -63, -62, -60, -50):
    group('pow', f'cutoff_adjacent_y_2p{e}', [(rng.randrange(1, 2047) << 52 | rng.getrandbits(52), bits(2.**e) | (sign if i & 1 else 0)) for i in range(samples)])
group('pow', 'huge_finite_exponents', [(rng.randrange(1, 2047) << 52 | rng.getrandbits(52), rng.randrange(1086, 2047) << 52 | rng.getrandbits(52) | (sign if i & 1 else 0)) for i in range(samples)])
group('pow', 'near_one_variable_exponent', [(bits(1.)+rng.choice([-1, 1])*rng.randrange(1, 513), bits(math.ldexp(rng.uniform(.5, 1), rng.randrange(-60, 80))) | (sign if i & 1 else 0)) for i in range(samples)])
group('pow', 'medium_integer_exponents', [(bits(rng.uniform(.2, 3.)), bits(float(rng.randrange(7, 1025))) | (sign if i & 1 else 0)) for i in range(samples)])
group('pow', 'power_of_two_bases_wide_exponents', [(bits(2.**rng.randrange(-1000, 1000)), bits(rng.uniform(-1024, 1024))) for _ in range(samples)])

reports = []
for op, name, vectors in groups:
    spec = operations[op]
    assert spec['qfplib_symbol'] in own.elf.symbols, spec['qfplib_symbol']
    rows = []
    for x, y in vectors:
        args = (x, y) if op == 'pow' else (x,)
        expected = oracle.reference(op, *args)
        actual, _, oc = own.call(spec['own_symbol'], x, y, count=True)
        assert ((nan(actual) and bool(actual & (1 << 51))) if nan(expected) else actual == expected), (op, name, hex(x), hex(y), hex(actual), hex(expected))
        result, _, qc = own.call(spec['qfplib_symbol'], x, y, count=True)
        correct = (nan(result) if nan(expected) else result == expected)
        rows.append(dict(x=f'{x:016X}', y=f'{y:016X}', expected=f'{expected:016X}',
                         own=f'{actual:016X}', qfplib=f'{result:016X}', own_instructions=oc,
                         qfplib_instructions=qc, qfplib_correct=correct))
    correct = [r for r in rows if r['qfplib_correct']]
    means = {side: sum(r[side+'_instructions'] for r in rows)/len(rows) for side in ('own', 'qfplib')}
    eligible_means = {side: sum(r[side+'_instructions'] for r in correct)/len(correct) if correct else None for side in ('own', 'qfplib')}
    record = dict(operation=op, stream=name, cases=len(rows), own_wrong=0,
                  qfplib_wrong=len(rows)-len(correct), mean_instructions=means,
                  both_correct_cases=len(correct), both_correct_mean_instructions=eligible_means,
                  both_correct_own_slower=sum(r['own_instructions'] > r['qfplib_instructions'] for r in correct), rows=rows)
    reports.append(record)
    (work/'progress.json').write_text(json.dumps(dict(status='RUNNING', completed_groups=len(reports),
        last={k:v for k,v in record.items() if k!='rows'}), indent=2)+'\n')
    print(op, name, means, 'Qfp_wrong', record['qfplib_wrong'], 'eligible', eligible_means, flush=True)

result = dict(status='PASS_INDEPENDENT_DOMAIN_AUDIT_NOT_A_SPEED_PASS',
              elf_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
              reference_elf_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
              producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              bootrom_sha256=own.bootrom_sha256, mpfr=oracle.version, groups=reports,
              cases=sum(r['cases'] for r in reports), own_wrong=0,
              slower_mean_groups=sum(r['mean_instructions']['own'] > r['mean_instructions']['qfplib'] for r in reports),
              maximum_observed_stack_bytes=SP-own.stack_lowest,
              scope='New independent ranges,128 cases per stream, exact MPFR return values. Raw means and the subset where Qfplib is also correct are both reported. Actual ARM instructions, modeled SIO division, not physical cycles or all-input coverage.',
              hardware_accessed=False, candidate_changed=False, goal_complete=False)
(work/'result.json').write_text(json.dumps(result, indent=2)+'\n')
(work/'progress.json').write_text(json.dumps(dict(status='PASS', groups=len(reports), cases=result['cases']), indent=2)+'\n')
print('DONE', len(reports), 'groups', result['cases'], 'cases;', result['slower_mean_groups'], 'raw slower means; goal open', flush=True)
