"""Fresh public original153 benchmark for the exact square128 replacement."""
import json,sys
from collections import Counter
sys.dont_write_bytecode=True
from harness import *
machines={n:square_machine(n) for n in ['parent','candidate','Qfplib']}
traces={n:square_trace(m) for n,m in machines.items() if n!='Qfplib'}
jobs=json.loads((BASE/'original153.json').read_text())['rows'];oracle=Oracle();rows=[]
for i,row in enumerate(jobs):
    if i%32==0:print('square128-public',i,'/',len(jobs),flush=True)
    x,y=int(row['x'],16),int(row['y'],16);expected=oracle.reference('pow',x,y)
    for state_name,state in states.items():
        outputs,counts,correct,args={},{},{},{}
        for label,m in machines.items():
            if label!='Qfplib':traces[label].clear()
            m.uc.mem_write(0xd0000060,state)
            value,_,cost=m.call(row['reference'] if label=='Qfplib' else '_ZN12compact_math3powEdd',x,y,count=True)
            outputs[label]=f'{value:016X}';counts[label]=cost;correct[label]=equal(value,expected,64)
            state_after(m,state)
            if label!='Qfplib':assert correct[label];args[label]=list(traces[label])
        assert outputs['parent']==outputs['candidate'] and args['parent']==args['candidate']
        delta=sum(c['new_cost']-c['old_cost'] for c in args['candidate'])
        assert counts['candidate']==counts['parent']+delta
        assert counts['parent']==next(v['candidate'] for v in row['states'] if v['SIO']==state_name)
        rows.append(dict(x=row['x'],y=row['y'],stream=row['stream'],reference=row['reference'],SIO=state_name,
                         expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct,square_calls=args['candidate']))
loss=lambda r,n:r['correct']['Qfplib'] and r['instructions'][n]>r['instructions']['Qfplib']
old={(r['x'],r['y']) for r in rows if loss(r,'parent')};new={(r['x'],r['y']) for r in rows if loss(r,'candidate')}
out=dict(status='PILOT_PUBLIC153_EXACT_SQUARE128',candidate_ELF_sha256=sha(HERE/'candidate.elf'),
    fresh_ARM_calls=3*len(rows),oracle_evaluations=len(jobs),candidate_wrong=0,parent_remaining=len(old),candidate_remaining=len(new),
    fixed_pairs=sorted(old-new),new_raw_losses=len(new-old),cost_delta_histogram=dict(Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in rows)),
    stacks={n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},rows=rows,hardware_accessed=False)
(HERE/'probe.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))
