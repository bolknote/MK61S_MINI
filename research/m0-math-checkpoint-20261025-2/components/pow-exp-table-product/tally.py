"""Recount the old/new union, keeping every numerical Qfplib reference variant."""
from pathlib import Path
from collections import Counter
import gzip,json,hashlib
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
old=json.loads((W/'old-qualification.json').read_text())
new=json.loads((W/'new-qualification.json').read_text())
unit=json.loads((W/'unit-proof.json').read_text())
states={};overlap=0
def add(row,references,output,cost,parent):
    key=(row['x'],row['y'],row['SIO'])
    value=dict(candidate=output,candidate_instructions=cost,parent_C77_instructions=parent)
    record=states.setdefault(key,value|dict(references={}))
    assert all(record[k]==v for k,v in value.items()),key
    for name,ref in references.items():
        if name in record['references']:assert record['references'][name]==ref,(key,name)
        record['references'][name]=ref
with gzip.open(W/'old-records.jsonl.gz','rt') as f:
    for line in f:
        row=json.loads(line)
        refs={n:{k:r[k] for k in ['output','instructions','correct_Qfplib']} for n,r in row['references'].items()}
        add(row,refs,row['candidate'],row['candidate_instructions'],row['parent_C77_instructions'])
for row in new['rows']:
    if (row['x'],row['y'],row['SIO']) in states:overlap+=1
    refs={n:dict(output=row['outputs'][n],instructions=row['instructions'][n],correct_Qfplib=row['correct'][n])
          for n in ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']}
    add(row,refs,row['outputs']['candidate'],row['instructions']['candidate'],row['instructions']['parent'])

parent_losses=set();candidate_losses=set();new_losses=[];remaining=[];comparison=Counter();wrong=0
regressions=Counter();regression_scopes=Counter();state_variants=0
for key,row in states.items():
    pair=key[:2];cost=row['candidate_instructions'];parent=row['parent_C77_instructions']
    if cost>parent:
        regressions[cost-parent]+=1
        correct=[r['instructions'] for r in row['references'].values() if r['correct_Qfplib']]
        scope='wrong_Qfplib_only' if not correct else 'still_no_slower_than_all_correct_references' if cost<=min(correct) else 'already_slower_than_a_correct_reference'
        regression_scopes[scope]+=1
    for ref,r in row['references'].items():
        state_variants+=1
        if not r['correct_Qfplib']:
            wrong+=1;continue
        q=r['instructions'];direction='faster' if cost<q else 'equal' if cost==q else 'slower'
        comparison[direction]+=1
        if parent>q:parent_losses.add(pair)
        if cost>q:
            candidate_losses.add(pair)
            item=dict(x=key[0],y=key[1],SIO=key[2],reference=ref,candidate=cost,parent=parent,Qfplib=q,
                      candidate_output=row['candidate'],Qfplib_output=r['output'])
            remaining.append(item)
            if parent<=q:new_losses.append(item)

matrix=json.loads((ROOT/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json').read_text())['rows']
historical=[];counts={n:Counter() for n in ['parent','candidate']}
for row in matrix:
    if row['operation']!='pow':continue
    ref=('qfp_composed_pow_exact' if row['stream']=='composed_exact_exponents' else
         'qfp_composed_pow_integer' if row['stream'].startswith('composed_negative_') else 'qfp_composed_pow')
    records=[]
    for state in ['READY','DIRTY']:
        value=states[row['x'],row['y'],state];r=value['references'][ref]
        assert r['correct_Qfplib']
        records.append(dict(SIO=state,parent=value['parent_C77_instructions'],candidate=value['candidate_instructions'],Qfplib=r['instructions']))
    for n in counts:
        key='slower' if any(v[n]>v['Qfplib'] for v in records) else 'equal' if any(v[n]==v['Qfplib'] for v in records) else 'strict'
        counts[n][key]+=1
    historical.append(dict(x=row['x'],y=row['y'],stream=row['stream'],reference=ref,states=records))
assert len(historical)==153 and counts['parent']['slower']==48 and counts['candidate']['slower']==35
assert not new_losses
assert old['new_loss_state_variants']==[] and new['new_raw_loss_pairs']==0
total=old['fresh_candidate_ARM_calls']+new['fresh_public_ARM_calls']+unit['actual_ARM_calls']
assert total==314546
result=dict(status='RECOUNTED_SAME_OLD_CORPUS_AND_EXPANDED_REFERENCE_UNION',
    union_unique_pairs=len({key[:2] for key in states}),union_states=len(states),
    union_reference_state_variants=state_variants,new_control_states_already_in_old_corpus=overlap,
    parent_C77_raw_loss_pairs=len(parent_losses),candidate_raw_loss_pairs=len(candidate_losses),
    fixed_raw_pairs=len(parent_losses-candidate_losses),new_raw_loss_pairs=0,new_loss_state_variants=[],
    remaining_state_variants=len(remaining),wrong_Qfplib_state_variants_retained=wrong,
    correct_Qfplib_state_variant_comparison=dict(comparison),
    retained_parent_cost_increase_states=sum(regressions.values()),retained_increase_histogram=dict(regressions),
    retained_increase_scopes=dict(regression_scopes),original153={n:dict(v) for n,v in counts.items()},
    qualified_fresh_ARM_calls=total,fresh_public_ARM_calls=old['fresh_candidate_ARM_calls']+new['fresh_public_ARM_calls'],
    fresh_bare_ARM_calls=unit['actual_ARM_calls'],fresh_directed_MPFR_inputs=new['actual_directed_MPFR_inputs'],
    fresh_sNaN_policy_shortcuts=new['sNaN_policy_shortcuts'],pilot3096_calls_excluded=True,
    inherited_parent_R_C77_and_Qfplib_calls_not_fresh=True,
    expanded_observed_parent_and_candidate_stack_bytes=2284,goal_complete=False)
(W/'union-summary.json').write_text(json.dumps(result,indent=2)+'\n')
(W/'remaining-expanded.json').write_text(json.dumps(dict(rows=remaining),indent=2)+'\n')
(W/'original153.json').write_text(json.dumps(dict(rows=historical),indent=2)+'\n')
print(json.dumps(result,indent=2))
