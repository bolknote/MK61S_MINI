"""Measure actual public pow routes against the accepted parent and Qfplib."""
from collections import Counter
import json,random,sys
sys.dont_write_bytecode=True
from harness import *

machines={n:machine(n) for n in ('parent','control','candidate','Qfplib')}
traces={n:hook_products(m,n) for n,m in machines.items() if n!='Qfplib'}
roots,certificate=table();root_set=set(roots)
jobs=[]
for row in json.loads((P/'slower-inputs.json').read_text())['rows']:
    if row['operation']!='pow':continue
    ref=('qfp_composed_pow_exact' if row['stream']=='composed_exact_exponents' else
         'qfp_composed_pow_integer' if row['stream'].startswith('composed_negative_') else 'qfp_composed_pow')
    jobs.append((int(row['x'],16),int(row['y'],16),ref,'original153'))
for x in [0.5,0.75,1.0,1.25,1.5,2.0,3.0,5.0,10.0]:
    for exponent in [8,9,10,11,12,16,24,32,48]:
        for sign in [-1,1]:jobs.append((bits(x),bits(sign*2.0**-exponent),'qfp_composed_pow','small_y'))
previous=json.loads((C/'pow-loss-replay.json').read_text())
for row in previous['rows'][:128]:jobs.append((int(row['x'],16),int(row['y'],16),row['reference'],'prior_loss'))
jobs=list(dict.fromkeys(jobs));oracle=Oracle();rows=[]
for i,(x,y,reference,group) in enumerate(jobs):
    if i%32==0:print('public-probe',i,'/',len(jobs),flush=True)
    expected=oracle.reference('pow',x,y)
    for state_name,state in states.items():
        outputs,counts,correct,arguments={},{},{},{}
        for label,m in machines.items():
            m.uc.mem_write(0xd0000060,state)
            if label!='Qfplib':traces[label].clear()
            got,_,cost=m.call(reference if label=='Qfplib' else '_ZN12compact_math3powEdd',x,y,count=True)
            outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
            if label!='Qfplib':
                assert correct[label],(i,label,hex(x),hex(y),hex(got),hex(expected))
                arguments[label]=list(traces[label])
            state_after(m,state)
        assert outputs['parent']==outputs['control']==outputs['candidate'],(i,outputs)
        for call in arguments['candidate']:
            if call['kind']=='table':assert int(call['a'],16) in root_set and int(call['b'],16)<1<<54
        rows.append(dict(x=f'{x:016X}',y=f'{y:016X}',group=group,reference=reference,SIO=state_name,
                         expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,products=arguments))
loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
out=dict(status='PILOT_ONLY_NOT_FULL_QUALIFICATION',jobs=len(jobs),public_state_rows=len(rows),
    fresh_ARM_calls=4*len(rows),fresh_MPFR_oracle_evaluations=len(jobs),MPFR_version=oracle.version,
    table_certificate=certificate,candidate_wrong=0,
    parent_control_cost_deltas=dict(sorted(Counter(r['instructions']['control']-r['instructions']['parent'] for r in rows).items())),
    candidate_control_cost_deltas=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['control'] for r in rows).items())),
    raw_losses={n:len({(r['x'],r['y']) for r in rows if loss(r,n)}) for n in machines if n!='Qfplib'},
    new_raw_losses_vs_parent=len({(r['x'],r['y']) for r in rows if loss(r,'candidate') and not loss(r,'parent')}),
    stack={n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},rows=rows,hardware_accessed=False)
(W/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))
