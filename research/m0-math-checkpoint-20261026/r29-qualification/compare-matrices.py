"""Every output/reference unchanged; every non-exp own cost must be exact R28."""
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import gzip,hashlib,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-exp-directed-distance-r28-qualification-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(P/'FROZEN.json')=='0ba57f4e189ef444dc849d8dc42836f2a56ab8780282c36854d320317b42a70b'
assert not(W/'matrix-comparison.json').exists()
reports={}
for name in ['original507','broad']:
    totals=Counter();deltas=Counter();increases=[];newloss=[]
    with gzip.open(P/(name+'-records.jsonl.gz'),'rt')as old,gzip.open(W/(name+'-records.jsonl.gz'),'rt')as new:
        for i,(a,b)in enumerate(zip_longest(old,new)):
            assert a is not None and b is not None;a,b=json.loads(a),json.loads(b)
            for key in set(a)-{'outputs','instructions','correct'}:assert a[key]==b[key],(name,i,key)
            assert a['outputs']==b['outputs']and a['correct']==b['correct']
            for ref in a['instructions']:
                if ref not in ['candidate','zero-control']:assert a['instructions'][ref]==b['instructions'][ref]
            totals[b['operation']]+=1
            diff=b['instructions']['candidate']-a['instructions']['candidate'];deltas[diff]+=1
            if b['operation']!='exp':assert a['instructions']==b['instructions'],(name,i,b['operation'])
            if diff>0:increases.append(dict(index=i,operation=b['operation'],x=b['x'],y=b['y'],SIO=b['SIO'],old=a['instructions']['candidate'],new=b['instructions']['candidate'],delta=diff))
            for ref in a['instructions']:
                if ref in ['candidate','zero-control']or not b['correct'][ref]:continue
                if a['instructions']['candidate']<=a['instructions'][ref]and b['instructions']['candidate']>b['instructions'][ref]:newloss.append(dict(index=i,reference=ref,record=b))
    reports[name]=dict(state_rows=sum(totals.values()),operation_rows=dict(totals),all_outputs_and_correctness_exact_R28=True,
     all_reference_instruction_counts_exact_R28=True,every_nonexp_candidate_and_zero_control_instruction_count_exact_R28=True,
     candidate_instruction_delta_histogram=dict(deltas),parent_increase_rows=increases,new_correct_Qfplib_loss_rows=newloss,
     parent_records_sha256=sha(P/(name+'-records.jsonl.gz')),candidate_records_sha256=sha(W/(name+'-records.jsonl.gz')))
assert all(not r['new_correct_Qfplib_loss_rows']for r in reports.values())
out=dict(status='PASS_R29_PRIMARY_ALL_NONEXP_BITS_REFERENCES_AND_OWN_COSTS_EXACT_R28',parent_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),matrices=reports,
 no_new_ARM_or_MPFR_calls=True,does_not_complete_full_exp_qualification=True,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'matrix-comparison.json').write_text(json.dumps(out,indent=2)+'\n')
print('R29 primary comparison PASS',[(n,r['candidate_instruction_delta_histogram'],len(r['parent_increase_rows']))for n,r in reports.items()],flush=True)
