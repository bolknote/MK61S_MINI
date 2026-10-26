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
import time
BASE=ROOT/'.build/m0-ln-near-directional-20261024'
parent=json.loads((BASE/'qualification.json').read_text())
previous={(r['x'],r['SIO']):r for r in parent['rows']}
jobs={int(r['x'],16):r['group'] for r in parent['rows'] if r['SIO']=='READY'}
def add(raw,group):
    if 0<=raw<(1<<64):
        jobs.setdefault(raw,group)
for n in range(129):
    for sign in (-1,1):
        for halfstep in (0,0.5):
            center=bits(1+sign*(n+halfstep)/8192)
            for delta in range(-8,9):
                add(center+delta,'near_one_cells_and_half_cells')
for raw in (0x3fef800000000000,0x3fef808000000000,0x3ff0400000000000):
    for delta in range(-32,33):
        add(raw+delta,'near_domain_boundary')
for row in []: # Already retained every near neighbor from the parent.
    for delta in range(-32,33):
        add(int(row['x'],16)+delta,'remaining_loss_neighbors')
import random
rng=random.Random(0x10D17070)
for _ in range(8192):
    add(rng.randrange(0x3fef808000000001,0x3ff0400000000001),'near_uniform_random')
for index in (0,511,1023):
    center=0x4000000000000000+(index<<42)+(1<<41)
    for high in (0,1,255,510,511,512):
        for low in (-2,-1,0,1,2):
            delta=(high<<32)+low
            if 0<=delta<=(1<<41):
                for side in (-1,1):
                    raw=center+side*delta
                    if 0<=((raw&((1<<52)-1))-(index<<42))<(1<<42):
                        add(raw,'general_quotient_low_word_wrap_controls')
states = {'READY': struct.pack('<7I', 0, 0, 0, 0, 0, 0, 1),
          'DIRTY': struct.pack('<7I', 17, 3, 17, 3, 5, 2, 3)}
o = Oracle()
rows=[];start=time.monotonic();retained=0
for raw,group in jobs.items():
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
        saved=previous.get((f'{raw:016X}',state_name))
        if saved:
            assert counts['parent']==saved['instructions']['candidate']
            assert outputs['parent']==saved['outputs']['candidate']
            retained+=1
        rows.append(dict(x=f'{raw:016X}', group=group, SIO=state_name, expected=f'{expected:016X}',
                         outputs=outputs, instructions=counts, correct=correct))
report = dict(status='PASS_LOG_RATIO_ENDPOINT_PREDICATE_ALL_PROFILED_NOT_PRODUCTION', cases=len(rows), rows=rows,
              source_sha256=b['source_include_sha256'], candidate_ELF_sha256=b['ELF_sha256'],
              candidate_stack_bytes=SP-machines['candidate'].stack_lowest,
              parent_stack_bytes=SP-machines['parent'].stack_lowest,
              MPFR_version=o.version,hardware_accessed=False,unique_inputs=len(jobs),
              actual_ARM_calls=4*len(rows),all_cases_profiled=True,
              retained_parent_counts_checked=retained,elapsed_seconds=time.monotonic()-start,
              PCS_SP_bounded_writes_SIO_checked_every_call=True)
assert retained==len(parent['rows'])==65880
groups=[]
for state in states:
    selected=[r for r in rows if r['SIO']==state]
    correct=[r for r in selected if r['correct']['Qfplib']]
    change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else
                   'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in selected)
    groups.append(dict(SIO=state,cases=len(selected),vs_parent=dict(change),
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
