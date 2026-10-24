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
assert hashlib.sha256((W / 'native_eabi_m0_log70_center.inc').read_bytes()).hexdigest() == b['source_include_sha256']
machines = {'resident': Machine(ELF, True, bootrom=ROM), 'Qfplib': Machine(REF, True)}
for label in ('parent', 'candidate'):
    m = Machine(ELF, True, bootrom=ROM)
    image = ElfImage(W / (('control' if label == 'parent' else label) + '.elf'))
    image.load(m.uc)
    m.elf.symbols[label + '_ln'] = image.symbols['mk61_m0_ln']
    machines[label] = m
from collections import Counter
import random
import time
old = [r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='ln']
jobs = {int(r['x'],16):'historical' for r in old}
def add(raw, group):
    if 0<=raw<(1<<64):
        jobs.setdefault(raw,group)
for r in old:
    raw=int(r['x'],16)
    if 0<raw<0x7ff0000000000000:
        for delta in range(-128,129):
            add(raw+delta,'historical_neighbors')
for index in range(1024):
    center=0x3ff0000000000000+((2*index+1)<<41)
    for delta in (-1,0,1):
        add(center+delta,'dyadic_center')
for exponent in range(1,2047):
    power=exponent<<52
    for delta in (-1,0,1):
        add(power+delta,'every_exponent_boundary')
    add(power+(((exponent*73)%1024)*2+1)*(1<<41),'rotated_center_every_exponent')
for raw in (0,1,2,3,(1<<51),(1<<52)-1,1<<52,(1<<52)+1,
            0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7fffffffffffffff):
    for sign in (0,1<<63):
        add(raw|sign,'IEEE_edges')
for bit in range(52):
    for delta in (-1,0,1):
        for sign in (0,1<<63):
            add(((1<<bit)+delta)|sign,'subnormal_boundaries')
rng=random.Random(0x10770D17)
for _ in range(1024):
    add(rng.randrange(1,0x7ff0000000000000),'random_positive')
for _ in range(256):
    add(rng.randrange(1,1<<52),'random_subnormal')
    add(rng.randrange(1<<63,1<<64),'random_negative')
states = {'READY': struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1),
          'DIRTY': struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)}
o = Oracle()
rows = [];start=time.monotonic()
for raw, group in jobs.items():
    if len(rows)%2048==0: print('progress',len(rows),'/',2*len(jobs),flush=True)
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
        assert counts['parent']==counts['resident']
        if state_name=='READY': assert counts['candidate']==counts['parent']
        rows.append(dict(x=f'{raw:016X}', group=group, SIO=state_name, expected=f'{expected:016X}',
                         outputs=outputs, instructions=counts, correct=correct))
report = dict(status='PASS_PUBLIC_LN_EXACT_DIRTY_RATIO_FULLY_PROFILED_NOT_PRODUCTION', cases=len(rows), rows=rows,
              source_sha256=b['source_include_sha256'], candidate_ELF_sha256=b['ELF_sha256'],
              candidate_stack_bytes=SP-machines['candidate'].stack_lowest,
              parent_stack_bytes=SP-machines['parent'].stack_lowest,
              MPFR_version=o.version, hardware_accessed=False, unique_inputs=len(jobs),
              actual_ARM_calls=4*len(rows), all_cases_profiled=True,
              READY_parent_instruction_counts_identical=True,
              PCS_SP_bounded_writes_SIO_checked_every_call=True,
              elapsed_seconds=time.monotonic()-start)
groups=[]
for state in states:
    selected=[r for r in rows if r['SIO']==state]
    change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else
                   'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in selected)
    correct=[r for r in selected if r['correct']['Qfplib']]
    groups.append(dict(SIO=state, cases=len(selected), vs_parent=dict(change),
       parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in correct),
       candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in correct),
       newly_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib']>=r['instructions']['parent'] for r in correct),
       Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in selected)))
report['groups']=groups
report['remaining_slower_correct_Qfplib']=[r for r in rows if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
report['regressions_vs_parent']=[r for r in rows if r['instructions']['candidate']>r['instructions']['parent']]
(W / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('rows','remaining_slower_correct_Qfplib','regressions_vs_parent')}, indent=2))
print(json.dumps([{k: r[k] for k in ('x', 'instructions')} for r in rows
                  if r['group'] == 'historical' and r['SIO'] == 'DIRTY'], indent=2))
