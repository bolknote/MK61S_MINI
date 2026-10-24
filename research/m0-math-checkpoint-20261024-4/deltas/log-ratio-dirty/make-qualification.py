"""Expand the public probe into a boundary-rich, fully profiled corpus."""
from pathlib import Path

W = Path(__file__).resolve().parent
s = (W/'probe.py').read_text()
start = s.index("old = [r for r in json.loads")
end = s.index("states = {", start)
generator = '''from collections import Counter
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
'''
s = s[:start]+generator+s[end:]
s = s.replace('rows = []\nfor raw, group in jobs.items():',
              'rows = [];start=time.monotonic()\nfor raw, group in jobs.items():')
s = s.replace("assert outputs['candidate'] == outputs['parent'] == outputs['resident']",
              "assert outputs['candidate'] == outputs['parent'] == outputs['resident']\n        assert counts['parent']==counts['resident']\n        if state_name=='READY': assert counts['candidate']==counts['parent']")
anchor = "report = dict(status='PASS_PRIVATE_DIRTY_LOG_RATIO_PUBLIC_PROBE_NOT_QUALIFICATION'"
assert s.count(anchor) == 1
s = s.replace(anchor, "report = dict(status='PASS_PUBLIC_LN_EXACT_DIRTY_RATIO_FULLY_PROFILED_NOT_PRODUCTION'")
s = s.replace("MPFR_version=o.version, hardware_accessed=False)", '''MPFR_version=o.version, hardware_accessed=False, unique_inputs=len(jobs),
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
report['regressions_vs_parent']=[r for r in rows if r['instructions']['candidate']>r['instructions']['parent']]''')
s = s.replace("(W / 'probe.json')", "(W / 'qualification.json')")
s = s.replace("if k != 'rows'", "if k not in ('rows','remaining_slower_correct_Qfplib','regressions_vs_parent')")
s = s.replace("for raw, group in jobs.items():", "for raw, group in jobs.items():\n    if len(rows)%2048==0: print('progress',len(rows),'/',2*len(jobs),flush=True)")
(W/'qualify.py').write_text(s)
