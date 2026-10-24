"""Probe public ln entry, IEEE edges and representative normal controls."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
P = ROOT / '.build/m0-asin-scaled-bound-v164-20261023'
Q = ROOT / '.build/m0-float-fma-qualification-20261023'
sys.path.insert(0, str(Q))
sys.path.insert(0, str(Q / 'support'))
from native_eabi_m0_arm_self_test import Machine, SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle, bits
from oracles import equal

ROM = ROOT / 'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ELF = P / 'firmware/mk61s-picocalc-pico-h.elf'
REF = ROOT / '.build/m0-v138-execution-20261023/reference/reference.elf'
b = json.loads((W / 'candidate-build.json').read_text())
assert hashlib.sha256((W / 'candidate.elf').read_bytes()).hexdigest() == b['ELF_sha256']
assert hashlib.sha256((W / 'native_eabi_m0_log70.inc').read_bytes()).hexdigest() == b['source_include_sha256']
machines = {'resident': Machine(ELF, True, bootrom=ROM), 'Qfplib': Machine(REF, True)}
for label in ('parent', 'candidate'):
    m = Machine(ELF, True, bootrom=ROM)
    image = ElfImage(W / (('control' if label == 'parent' else label) + '.elf'))
    image.load(m.uc)
    m.elf.symbols[label + '_ln'] = image.symbols['mk61_m0_ln']
    machines[label] = m
old = [r for r in json.loads((P / 'slower-inputs.json').read_text())['rows'] if r['operation'] == 'ln']
jobs = {int(r['x'], 16): 'historical' for r in old}
for x in [0, 1, 2, 3, (1 << 51), (1 << 52) - 1, 1 << 52, (1 << 52) + 1,
          0x7ff0000000000000, 0x7ff0000000000001, 0x7ff8000000000000, 0x7fffffffffffffff]:
    for sign in (0, 1 << 63):
        jobs.setdefault(x | sign, 'IEEE')
for x in [1/1024, 1/2, 0.9, 0.99, 1., 1.001, 1.01, 1.1, 2., 4., 16., 100., 1e100]:
    for sign in (1, -1):
        jobs.setdefault(bits(x*sign), 'normal_control')
for r in json.loads((ROOT/'.build/m0-log-ratio-small-limb-20261024/remaining-slower.json').read_text())['rows']:
    jobs.setdefault(int(r['x'],16),'remaining_parent')
import random
rng=random.Random(0xC105E202)
for _ in range(512):
    jobs.setdefault(rng.randrange(0x3fffc00000000000,0x4000400000000001),'outside_family_near_two')
jobs.setdefault(0x400ffe7effffffbf,'new_guard_edge_speed_regression')
for row in json.loads((ROOT/'.build/m0-ln-endpoint-predicate-20261024/remaining-slower.json').read_text())['rows']:
    jobs.setdefault(int(row['x'],16),'previously_fixed_family')
controls=json.loads((ROOT/'.build/m0-ln-raw-cold-entry-20261024/qualification.json').read_text())['rows']
normal=[r for r in controls if r['SIO']=='READY' and r['group']=='near_uniform_random' and r['correct']['Qfplib'] and r['instructions']['candidate']<650]
for row in normal[::max(1,len(normal)//512)][:512]:
    jobs.setdefault(int(row['x'],16),'previously_fast_near_uniform')
trial=json.loads((ROOT/'.build/m0-ln-near-q77-products-20261024/qualification.json').read_text())
for row in trial['remaining_slower_correct_Qfplib']:
    raw=int(row['x'],16)
    for step in range(-8,9):jobs.setdefault(raw+step,'previous_Q77_speed_loss_neighbors')
for index in range(1,257):
    if index==128:continue
    negative=index<128
    n=128-index if negative else index-128
    den=8064+index
    grid=512 if negative else 1024
    for edge in (-grid,0,grid):
        delta=den*1024+edge
        for side in (-1,1):
            a=(n<<49)+side*delta
            raw=0x3ff0000000000000-(a>>9) if negative else 0x3ff0000000000000+(a>>10)
            jobs.setdefault(raw,'linear_precision_threshold')
for row in json.loads((ROOT/'.build/m0-ln-near-q77-linear-20261024/remaining-slower.json').read_text())['rows']:
    if row['SIO']=='READY':
        for step in range(-64,65):jobs.setdefault(int(row['x'],16)+step,'remaining_main_neighbors')
rng=random.Random(0x1A2B170)
for _ in range(1024):
    k=rng.choice((-1022,-512,-32,-31,-2,-1,1,2,31,32,512,1023))
    raw=((k+1023)<<52)+rng.randrange(1<<52)
    jobs.setdefault(raw,'main_exponent_controls')
for index in range(33):
    for word in (1021,1022,1023):
        bh=0x3ff00000+(index<<10)+word
        for low in (0,1,63,64,0x7fffffff,0xffffffbf,0xffffffc0,0xffffffc1,0xfffffffe,0xffffffff):
            jobs.setdefault((bh<<32)|low,'positive_endpoint_domain_and_boundaries')
rng=random.Random(0x51A170)
for _ in range(2048):
    bh=0x3ff00000+(rng.randrange(16,32)<<10)+rng.choice((1022,1023))
    jobs.setdefault((bh<<32)|rng.randrange(1<<32),'positive_endpoint_uniform_random')
states = {'READY': struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1),
          'DIRTY': struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)}
o = Oracle()
rows = []
for raw, group in jobs.items():
    expected = o.reference('ln', raw)
    for state_name, state in states.items():
        outputs, counts, correct = {}, {}, {}
        for label, m in machines.items():
            m.uc.mem_write(0xd0000060, state)
            name = 'mk61_m0_ln' if label == 'resident' else 'qfp_dln' if label == 'Qfplib' else label + '_ln'
            got, _, cost = m.call(name, raw, count=True)
            outputs[label] = f'{got:016X}'
            counts[label] = cost
            correct[label] = equal(got, expected, 64)
            if label != 'Qfplib':
                assert correct[label], (label, hex(raw), hex(got), hex(expected))
            after = bytes(m.uc.mem_read(0xd0000060, 28))
            if state_name == 'DIRTY':
                assert after == state
            else:
                assert not (struct.unpack('<7I', after)[6] & 2)
        assert outputs['candidate'] == outputs['parent'] == outputs['resident']
        rows.append(dict(x=f'{raw:016X}', group=group, SIO=state_name, expected=f'{expected:016X}',
                         outputs=outputs, instructions=counts, correct=correct))
report = dict(status='PASS_RAW_MAIN_LN_PROBE_NOT_QUALIFICATION', cases=len(rows), rows=rows,
              source_sha256=b['source_include_sha256'], candidate_ELF_sha256=b['ELF_sha256'],
              candidate_stack_bytes=SP-machines['candidate'].stack_lowest,
              parent_stack_bytes=SP-machines['parent'].stack_lowest,
              MPFR_version=o.version, hardware_accessed=False)
(W / 'probe.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
print(json.dumps([{k: r[k] for k in ('x', 'instructions')} for r in rows
                  if r['group'] == 'historical' and r['SIO'] == 'DIRTY'], indent=2))
