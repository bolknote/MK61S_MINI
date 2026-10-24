"""Bind every previous R input, state and reference variant without filtering."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
R=ROOT/'.build/m0-pow-rsqrt-asm-20261024'
C=ROOT/'.build/m0-exp-directed-product-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
states={};variants=Counter();sources={}
for name in ('qualification.json','targeted.json','probe.json'):
    path=R/name;sources[str(path.relative_to(ROOT))]=sha(path)
    for row in json.loads(path.read_text())['rows']:
        key=(row['x'],row['y'],row['SIO'])
        value=dict(x=row['x'],y=row['y'],SIO=row['SIO'],expected=row['expected'],
                   parent_R_output=row['outputs']['candidate'],parent_R_cost=row['instructions']['candidate'])
        existing=states.setdefault(key,value|dict(references={}))
        assert all(existing[k]==v for k,v in value.items()),key
        reference=row.get('reference','qfp_composed_pow_exact')
        record=dict(reference=reference,output=row['outputs']['Qfplib'],instructions=row['instructions']['Qfplib'],
                    correct_Qfplib=row['correct']['Qfplib'])
        if reference in existing['references']:assert existing['references'][reference]==record,key
        existing['references'][reference]=record
parent=C/'pow-loss-replay.json';sources[str(parent.relative_to(ROOT))]=sha(parent)
for row in json.loads(parent.read_text())['rows']:
    key=(row['x'],row['y'],row['SIO']);value=row['fresh_candidate']
    assert key in states and value['candidate']==states[key]['parent_R_output']
    if 'known_C77_cost' in states[key]:assert states[key]['known_C77_cost']==value['candidate_instructions']
    states[key]['known_C77_cost']=value['candidate_instructions']
    states[key]['known_C77_logical_product_calls']=value['product_calls']
assert len(states)==223824 and len({key[:2] for key in states})==111912
assert sum(len(r['references']) for r in states.values())==223976
data=b''.join((json.dumps(r,separators=(',',':'))+'\n').encode() for r in states.values())
path=W/'old-corpus.jsonl.gz';path.write_bytes(gzip.compress(data,compresslevel=6,mtime=0))
out=dict(status='ALL_OLD_111912_PAIRS_BOUND_NO_REFERENCE_FILTER',unique_pairs=111912,
         state_jobs=len(states),reference_state_variants=223976,
         known_fresh_C77_state_costs=sum('known_C77_cost' in r for r in states.values()),
         corpus_sha256=sha(path),sources=sources,fresh_ARM_or_MPFR_calls=0)
(W/'corpus-binding.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
