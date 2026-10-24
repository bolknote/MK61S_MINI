"""Retain every parent input and add both-sided near-one geometry cells."""
from pathlib import Path

W = Path(__file__).resolve().parent
s = (W/'probe.py').read_text()
start = s.index('old = [r for r in json.loads')
end = s.index('states = {',start)
generator = '''from collections import Counter
import time
BASE=ROOT/'.build/m0-ln-enclosure-20261024'
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
for row in parent['remaining_slower_correct_Qfplib']:
    for delta in range(-32,33):
        add(int(row['x'],16)+delta,'remaining_loss_neighbors')
import random
rng=random.Random(0x10D17070)
for _ in range(8192):
    add(rng.randrange(0x3fef808000000001,0x3ff0400000000001),'near_uniform_random')
'''
s = s[:start]+generator+s[end:]
s = s.replace('rows = []\nfor raw, group in jobs.items():',
              "rows=[];start=time.monotonic();retained=0\nfor raw,group in jobs.items():\n    if len(rows)%2048==0: print('progress',len(rows),'/',2*len(jobs),flush=True)")
anchor = "assert outputs['candidate'] == outputs['parent'] == outputs['resident']"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor+"\n        saved=previous.get((f'{raw:016X}',state_name))\n        if saved:\n            assert counts['parent']==saved['instructions']['candidate']\n            assert outputs['parent']==saved['outputs']['candidate']\n            retained+=1")
s = s.replace("PASS_PRIVATE_NEAR_LN_ROUNDING_PROBE_NOT_QUALIFICATION",'PASS_NEAR_LN_ROUNDING_ALL_INPUTS_PROFILED_NOT_PRODUCTION')
s = s.replace("MPFR_version=o.version, hardware_accessed=False)", '''MPFR_version=o.version,hardware_accessed=False,unique_inputs=len(jobs),
              actual_ARM_calls=4*len(rows),all_cases_profiled=True,
              retained_parent_counts_checked=retained,elapsed_seconds=time.monotonic()-start,
              PCS_SP_bounded_writes_SIO_checked_every_call=True)
assert retained==len(parent['rows'])==39318
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
report['regressions_vs_parent']=[r for r in rows if r['instructions']['candidate']>r['instructions']['parent']]''')
s = s.replace("(W / 'probe.json')", "(W / 'qualification.json')")
s = s.replace("if k != 'rows'", "if k not in ('rows','remaining_slower_correct_Qfplib','regressions_vs_parent')")
(W/'qualify.py').write_text(s)
