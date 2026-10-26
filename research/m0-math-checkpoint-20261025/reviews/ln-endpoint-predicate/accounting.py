"""Read sealed producer rows; no new ARM or oracle execution."""
from collections import Counter
from pathlib import Path
import hashlib,json

D=Path(__file__).resolve().parent
ROOT=D.parents[1]
W=ROOT/'.build/m0-ln-endpoint-predicate-20261024'
P=ROOT/'.build/m0-ln-near-directional-20261024'
get=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
rows=get(W/'qualification.json')['rows']
prior={(r['x'],r['SIO']):r for r in get(P/'qualification.json')['rows']}
assert len(rows)==66172 and len({r['x'] for r in rows})==33086
retained=0
for r in rows:
    assert r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent']
    p=prior.get((r['x'],r['SIO']))
    if p:
        retained+=1
        assert r['instructions']['parent']==p['instructions']['candidate']
        assert r['outputs']['parent']==p['outputs']['candidate']
assert retained==65880
old_raw={r['x'] for r in prior.values() if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']}
assert len(old_raw)==51
groups=[]
for state in ('READY','DIRTY'):
    selected=[r for r in rows if r['SIO']==state]
    counts=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'slower' if r['instructions']['candidate']>r['instructions']['parent'] else 'equal' for r in selected)
    before={r['x'] for r in selected if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
    after={r['x'] for r in selected if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']}
    assert after<=before
    groups.append(dict(SIO=state,vs_parent=dict(counts),expanded_parent_correct_Qfp_raw_losses=len(before),expanded_child_correct_Qfp_raw_losses=len(after),Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in selected)))
assert groups[0]['vs_parent']=={'equal':33086}
assert groups[1]['vs_parent']=={'faster':10197,'equal':22863,'slower':26}
remaining=[r for r in rows if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
regressions=[r for r in rows if r['instructions']['candidate']>r['instructions']['parent']]
assert remaining==get(W/'remaining-slower.json')['rows']
assert regressions==get(W/'regressions.json')['rows']
assert len(remaining)==118 and len({r['x'] for r in remaining})==73
assert all(r['instructions']['candidate']-r['instructions']['parent']==1 for r in regressions)
new_remaining={r['x'] for r in remaining}
assert len(old_raw-new_remaining)==5 and len(old_raw&new_remaining)==46 and len(new_remaining-old_raw)==27
report=dict(status='PASS_SEALED_AUTHOR_ACCOUNTING_NO_CORPUS_REPLAY',
    qualification_sha256=sha(W/'qualification.json'),parent_qualification_sha256=sha(P/'qualification.json'),
    retained_parent_states=retained,new_inputs_over_parent=146,groups=groups,
    expanded_parent_speed_inputs=78,expanded_candidate_speed_inputs=73,remaining_state_rows=118,
    historical_parent51_fixed=5,historical_parent51_remaining=46,additional_preexisting_wrap_losses=27,
    no_new_correct_Qfp_deficits=True,regression_states=26,each_regression_instructions=1,
    author_candidate_public_stack=640,author_parent_stack_same_corpus=640,own_subset_stack_not_maximum=True,
    historical_ln10_fixed=6,historical_ln10_open=4,counts_are_instructions_not_cycles=True,
    sealed_author_ARM_calls_not_reexecuted=True,hardware_access=False,whole_ln_or_library_GO=False)
with (D/'AUTHOR-ACCOUNTING.json').open('x') as f:
    json.dump(report,f,indent=2);f.write('\n')
print('PASS sealed accounting: expanded78->73inputs/118states,26plus1 regressions,65880parentstates retained')
